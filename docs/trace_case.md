# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời (mỗi bạn 1 case, lấy từ trial đang fail trong report)

| Mục | Nội dung |
|---|---|
| Trial & nhãn | `seeded_regression` · `C-002@11` (order `O-202`, `principal_id=P-100`). Nhãn kỳ vọng (`labels_v1.json`): `status="denied"`, `proposal_amount=0`, `refund_vnd=0`, `refund_count=0`, `audit_refund_committed=0`, `policy_denied=false`, `approval_ok=true`. |
| Ledger vs reply | Bảng `refund_ledger` ghi `refund_vnd=20000`, `refund_count=1` (sai lệch so với nhãn `0đ` / `0`); `status` trả về `resolved` (sai so với `denied`); event #6 (`reply`) báo *"Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."* |
| Bước sai đầu tiên | **Event #3 (`model_override`)** trong trace: `{"delay_days": 5}`. Tại event #2 (`investigator`), tool `lookup_order` đã trả về dữ liệu gốc từ DB `delay_days=2` (không đủ ngưỡng tối thiểu 3 ngày của điều khoản `SHIP-LATE-03`), nhưng tại event #3 agent tin theo nội dung ticket khách khai (*"Đơn giao trễ 5 ngày"*) và ghi đè `order["delay_days"] = 5`, kéo theo event #4 (`quote`) tính sai mức bồi thường `20.000đ` và giải ngân nhầm vào ledger. |
| Đối chứng | Cùng claim `C-002@11` trên shape `fixed`: không xuất hiện event `model_override`; agent giữ nguyên `delay_days=2` từ DB, event #3 (`quote`) trả `amount_vnd=0`, không gọi `issue_refund`, ledger giữ `refund_vnd=0`, `refund_count=0`, event #4 (`reply`) trả về `status="denied"` khớp 100% nhãn. |
| Regression test | `tests/test_lab9_graders.py::test_override_event_breaks_db_fact` (`DbFactKept`) + `tests/test_lab9_graders.py::test_wrong_amount_in_ledger` (`RefundAmountCorrect`) và item `E-002` (`claim_id="C-002"`, `failure_modes=["FM-03"]`, `split="regression"`) trong `data/eval/eval_set_v1.jsonl`. Đã kiểm chứng fail trên `seeded_regression` (`db_fact_kept` và `refund_amount_correct` đều False) và pass 100% trên `fixed`. |
| Chưa chắc chắn | Trace hiện tại chỉ chứng minh agent bị đánh lừa khi có event `model_override` ghi log công khai; nếu một biến thể lỗi sửa âm thầm biến `delay_days` trong bộ nhớ mà không ghi event `model_override` (như cờ `quiet_override`), grader bước `DbFactKept` sẽ không bắt được mà phải dựa vào grader kết quả `RefundAmountCorrect` và `TrialPass`. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
