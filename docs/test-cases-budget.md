# Ca kiểm tra ngân sách mẫu (#25)

Các ca dưới đây là dữ liệu và kỳ vọng dùng cho phần 0,25 của #25. Đơn vị tiền là
VND; `period` dùng định dạng `YYYY-MM`. Tên danh mục phải được ánh xạ sang
`category_id` trước khi gọi API. Kỳ vọng về status code là đề xuất cho contract
validation, cần giữ nhất quán khi endpoint ngân sách được triển khai.

| ID | Dữ liệu chính | Kỳ vọng | Nhóm |
| --- | --- | --- | --- |
| BUD-01 | `period=2026-10`, `income_estimate=20000000`, `savings_goal=2000000`; Ăn uống `5000000`, Đi lại `2000000`, Nhà ở `11000000` | Tạo thành công; tổng dòng `18000000` không vượt phần thu nhập sau tiết kiệm; budget ở trạng thái dự kiến theo contract | Hợp lệ |
| BUD-02 | `period=2026-11`, `income_estimate=15000000`, `savings_goal=0`; Ăn uống `4000000`, Nhà ở `7000000` | Tạo thành công; tổng dòng `11000000` | Hợp lệ |
| BUD-03 | `period=2026-12`, `income_estimate=10000000`, `savings_goal=1000000`; các dòng cộng lại `9000000` | Tạo thành công ở đúng ngưỡng `income_estimate - savings_goal` | Hợp lệ biên |
| BUD-04 | `period=2026-10`, `income_estimate=10000000`, `savings_goal=1000000`; các dòng cộng lại `10000001` | Từ chối `422 VALIDATION`; không tạo budget hoặc dữ liệu dở dang | Vượt thu nhập |
| BUD-05 | `period=2026-10`, `income_estimate=5000000`, `savings_goal=0`; các dòng cộng lại `5000001` | Từ chối `422 VALIDATION` vì tổng ngân sách lớn hơn thu nhập | Vượt thu nhập |
| BUD-06 | `income_estimate=-1`, `savings_goal=0`, một dòng `Ăn uống=100000` | Từ chối `422 VALIDATION`; không ghi số tiền âm | Số âm |
| BUD-07 | `income_estimate=10000000`, `savings_goal=-1`, một dòng `Ăn uống=100000` | Từ chối `422 VALIDATION`; mục tiêu tiết kiệm không được âm | Số âm |
| BUD-08 | `income_estimate=10000000`, `savings_goal=0`, một dòng `Ăn uống=-100000` | Từ chối `422 VALIDATION`; amount của budget line không được âm | Số âm |
| BUD-09 | `income_estimate=10000000`, `savings_goal=0`, dòng `Ăn uống=100000`, `Danh mục không tồn tại=200000` | Từ chối `422 VALIDATION` (hoặc mã lỗi danh mục theo contract); không tự tạo danh mục lạ | Danh mục lạ |
| BUD-10 | `period=2026-10` lần hai cho cùng household, dữ liệu hợp lệ | Từ chối `409 CONFLICT` hoặc cập nhật theo contract đã chốt; không tạo hai budget trùng kỳ | Trùng kỳ |

## Quy tắc kiểm tra chung

- `period` phải đúng `YYYY-MM` và là kỳ hợp lệ.
- `income_estimate`, `savings_goal` và mọi `budget_lines.amount` phải là số
  nguyên không âm.
- Tổng các dòng không được vượt `income_estimate - savings_goal`.
- Tất cả danh mục phải tồn tại và thuộc phạm vi household hoặc là danh mục hệ
  thống; không chấp nhận tên tùy ý từ client.
- Với mọi ca bị từ chối, xác nhận response có mã lỗi rõ ràng và database không
  tạo bản ghi một phần.
