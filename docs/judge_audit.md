# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt (`κ=0.757 ≥ 0.6`, `P=0.857 ≥ 0.8`, `R=0.800 ≥ 0.7`) | dùng |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không đạt (`κ=0.375 < 0.6`, `R=0.300 < 0.7`) | loại |

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | `H-008` (tone_ok) | PASS | FAIL | Người đúng | Reply dùng *"Em đã hoàn tiền cho anh rồi nha, anh check giúp em"* — xưng "em" và dùng từ "nha" quá suồng sã, sai quy chuẩn CSKH LogiX ("LogiX" / "anh/chị"). Cập nhật rubric: cấm xưng "em/mình/bạn" và tiểu từ khẩu ngữ ("nha/nhé"). |
| 2 | `H-017` (tone_ok) | PASS | FAIL | Người đúng | Reply *"Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha"* — gọi khách là "bạn ơi" + "nha". Cập nhật rubric: bắt buộc đại từ "anh/chị" trong mọi phản hồi hoàn tiền. |
| 3 | `H-029` (tone_ok) | PASS | FAIL | Người đúng | Reply *"Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm"* — giọng ra lệnh/xua đuổi khách dù mở đầu có "Dạ, vui lòng". Cập nhật rubric: đánh FAIL mọi câu mang hàm ý ngăn cản khách phản hồi. |
| 4 | `H-042` (tone_ok) | FAIL | PASS | Người đúng | Reply *"Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ"* — câu trả lời ngắn gọn, lịch sự, đủ thông tin nhưng judge phạt nhầm vì thiếu lời xin lỗi. Cập nhật rubric: chỉ yêu cầu xin lỗi khi từ chối hoặc báo sự cố, không bắt buộc khi đã hoàn tiền thành công. |
| 5 | `H-051` (tone_ok) | FAIL | PASS | Người đúng | Reply *"Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ"* — từ "refund" được CS LogiX cho phép nhưng judge phạt vì xen tiếng Anh. Cập nhật rubric: đưa thuật ngữ "refund" vào danh sách ngoại lệ được chấp nhận. |
| 6 | `H-081` (tone_ok) | FAIL | PASS | Judge đúng | Reply *"Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ"* — lịch sự và đúng chuẩn giọng điệu; nhãn người gán nhầm FAIL do đọc nhầm nội dung ticket. Sửa nhãn ground-truth thành PASS. |
| 7 | `HL-015` (helpful) | PASS | FAIL | Người đúng | Reply *"Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ"* nhưng ledger chỉ ghi `40.000đ` (FM-08); judge chỉ đọc văn bản nên chấm PASS. Không sửa rubric judge mà chuyển sang chấm đối chiếu số tiền bằng code grader (`ReplyMatchesLedger`). |

## Kết luận
- Tiêu chí bị loại và lý do (dẫn ma trận nhầm lẫn): Loại **`helpful`** (`κ = 0.375 < 0.6`, `Recall = 0.300 < 0.7`; ma trận nhầm lẫn `{'tp': 9, 'fp': 0, 'fn': 21, 'tn': 70}`). Trong 30 ca lỗi thực tế (`tp + fn = 30`), judge bỏ sót tới **21 ca (`fn = 21`)** — chủ yếu là các ca báo sai số tiền hoàn so với ledger (18/21 ca, ví dụ `HL-015`, `HL-016`, `HL-020`) và sai xưng hô (`HL-047`, `HL-091`, `HL-097`) — do judge chỉ đọc reply trôi chảy mà không có quyền truy cập ledger, làm sai lệch tỷ lệ lỗi quan sát được xuống `0.09` so với tỷ lệ thực `0.30` sau hiệu chỉnh Rogan-Gladen. Tiền và trạng thái ledger bắt buộc phải chấm bằng code grader thay vì LLM judge.
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai; cần nhãn người mới để có held-out thật.
