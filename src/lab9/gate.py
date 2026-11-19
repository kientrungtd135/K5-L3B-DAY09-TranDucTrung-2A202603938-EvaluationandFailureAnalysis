"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def _check_ratchet(spec: dict, base_spec: dict) -> list[str]:
    problems: list[str] = []
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return problems

    cur_metrics = {m["id"]: m for m in spec.get("metrics", [])}
    for bm in base_spec.get("metrics", []):
        mid = bm["id"]
        if mid not in cur_metrics:
            problems.append(f"ratchet: metric '{mid}' disappeared from spec")
            continue
        cm = cur_metrics[mid]
        if bm.get("blocking") and not cm.get("blocking"):
            problems.append(f"ratchet: metric '{mid}' downgraded from blocking to non-blocking")
        bth, cth = bm.get("threshold", {}), cm.get("threshold", {})
        if "max" in bth and ("max" not in cth or cth["max"] > bth["max"]):
            problems.append(f"ratchet: metric '{mid}' max threshold loosened ({bth.get('max')} -> {cth.get('max')})")
        if "min" in bth and ("min" not in cth or cth["min"] < bth["min"]):
            problems.append(f"ratchet: metric '{mid}' min threshold loosened ({bth.get('min')} -> {cth.get('min')})")
        if "max_increase" in bth and ("max_increase" not in cth or cth["max_increase"] > bth["max_increase"]):
            problems.append(f"ratchet: metric '{mid}' max_increase loosened ({bth.get('max_increase')} -> {cth.get('max_increase')})")
        if bth.get("no_significant_drop") and not cth.get("no_significant_drop"):
            problems.append(f"ratchet: metric '{mid}' dropped no_significant_drop")

    cur_slices = {(s["name"], s["metric"]): s for s in spec.get("slices", [])}
    for bs in base_spec.get("slices", []):
        key = (bs["name"], bs["metric"])
        if key not in cur_slices:
            problems.append(f"ratchet: slice '{key[0]}/{key[1]}' disappeared from spec")
            continue
        cs = cur_slices[key]
        if bs.get("blocking") and not cs.get("blocking"):
            problems.append(f"ratchet: slice '{key[0]}/{key[1]}' downgraded from blocking to non-blocking")
        if "min" in bs and ("min" not in cs or cs["min"] < bs["min"]):
            problems.append(f"ratchet: slice '{key[0]}/{key[1]}' min loosened ({bs.get('min')} -> {cs.get('min')})")
        if bs.get("no_significant_drop") and not cs.get("no_significant_drop"):
            problems.append(f"ratchet: slice '{key[0]}/{key[1]}' dropped no_significant_drop")
    return problems


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted."""
    problems: list[str] = []

    for mid, val in pr.get("metrics", {}).items():
        if isinstance(val, (int, float)) and not math.isfinite(val):
            problems.append(f"non-finite metric '{mid}': {val}")

    pr_rows = pr.get("rows", [])
    base_rows = base.get("rows", [])
    manifest = pr.get("manifest", {})
    n_items = manifest.get("items")
    seeds = manifest.get("seeds")
    if isinstance(n_items, int) and isinstance(seeds, list):
        expected_len = n_items * len(seeds)
        if len(pr_rows) != expected_len:
            problems.append(f"row count mismatch: got {len(pr_rows)}, expected {expected_len}")

    pr_pairs = [(r.get("item_id"), r.get("seed")) for r in pr_rows]
    base_pairs = [(r.get("item_id"), r.get("seed")) for r in base_rows]
    if len(set(pr_pairs)) != len(pr_pairs):
        problems.append("duplicate (item_id, seed) rows in PR report")
    if set(pr_pairs) != set(base_pairs):
        problems.append("PR (item_id, seed) set differs from baseline")

    if pr.get("evaluator_failures"):
        problems.append(f"non-empty evaluator_failures ({len(pr['evaluator_failures'])})")

    graded_ids = [
        m["id"] for m in spec.get("metrics", [])
        if m.get("level") in ("step", "trajectory", "outcome")
        and not m["id"].startswith("pass_")
        and m["id"] != "pass_rate"
    ]
    for r in pr_rows:
        scores = r.get("scores", r)
        for gid in graded_ids:
            if gid in scores and scores[gid] is None:
                problems.append(f"missing/None score for '{gid}' on {r.get('item_id')}@{r.get('seed')}")
                break

    base_slices_by_item: dict[str, tuple[str, ...]] = {}
    for r in base_rows:
        iid = r.get("item_id")
        if iid is not None and iid not in base_slices_by_item:
            base_slices_by_item[iid] = tuple(sorted(r.get("slices", [])))
    for r in pr_rows:
        iid = r.get("item_id")
        if iid in base_slices_by_item:
            cur_s = tuple(sorted(r.get("slices", [])))
            if cur_s != base_slices_by_item[iid]:
                problems.append(f"slice tags modified for '{iid}': {list(base_slices_by_item[iid])} -> {list(cur_s)}")
                break

    if base_spec is not None:
        problems.extend(_check_ratchet(spec, base_spec))

    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): evaluate slice-level floors and paired bootstrap regressions."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})

    for sl in spec.get("slices", []):
        sname = sl["name"]
        mid = sl["metric"]
        a = per_item(pr, mid, slice_name=sname)
        b = per_item(base, mid, slice_name=sname)
        val = (sum(a.values()) / len(a)) if a else None
        verdict = "ok"
        note = ""
        th = {k: sl[k] for k in ("min", "no_significant_drop") if k in sl}

        if val is None:
            verdict = "missing"
        elif "min" in sl and val < sl["min"]:
            verdict = "fail"

        if sl.get("no_significant_drop") and val is not None:
            keys = sorted(set(a) & set(b))
            if keys:
                d, lo, hi = stats.paired_bootstrap(
                    [a[k] for k in keys],
                    [b[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000),
                    rng=bs.get("rng", 2027),
                )
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"

        sid = f"slice:{sname}/{mid}"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        val_str = f"{val:.4f}" if isinstance(val, float) else str(val)
        lines.append(f"  {sid:<22} {val_str:<8} {json.dumps(th):<40} {note:<28} {label}")

    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
