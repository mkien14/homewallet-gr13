Community/admin (#29, D2): xem [contract community](community-api.md) và
[ma trận nghiệm thu](test-cases-community.md). Contract đang chờ Kiên/Thức xác nhận.

Trạng thái hóa đơn: UPLOADING, UPLOADED, PROCESSING, DRAFT_READY, NEEDS_REVIEW, CONFIRMED, FAILED
Mã cảnh báo (warnings): DUPLICATE_FILE, POSSIBLE_DUPLICATE, TOTAL_MISMATCH, DATE_MISSING, NOT_A_RECEIPT

GET /api/receipts?status=&limit=50&cursor=
  -> {"items":[{"id":12,"status":"DRAFT_READY","merchant":"Highlands Coffee",
       "total_amount":147000,"occurred_on":"2026-10-12","created_at":"...","warnings":[]}],
      "next_cursor":null}
  Pagination sorts receipts by descending id; pass next_cursor as cursor for the next page.

GET /api/receipts/{id}
  -> {"id":12,"status":"DRAFT_READY","error_code":null,"warnings":["TOTAL_MISMATCH"],
      "image_url":"<presigned GET, 5 phút>","created_at":"...","processed_at":"...",
      "draft":{"transaction_id":7,"merchant":"...","occurred_on":"2026-10-12","total_amount":147000,
               "category_id":2,"items":[{"description":"...","quantity":1,"amount":59000,"category_id":2}]}}

POST /api/receipts/{id}/confirm   body như "draft" (đã sửa)  -> 200 {"transaction":{...}}; 409 nếu đã xác nhận; 422 nếu sai
GET  /api/categories              -> {"categories":[{"id":1,"name":"Ăn uống","icon":"utensils","is_fixed":false}]}
POST /api/transactions            header Idempotency-Key; body {"occurred_on","total_amount","category_id","note"}
                                  -> 201 {"transaction":{...}} (gửi lại cùng khóa: 200 và trả bản ghi cũ)
                                  Giao dịch nhập tay được tạo ở trạng thái CONFIRMED.
GET  /api/transactions?period=2026-10&member_id=&category_id=&limit=50&cursor=
                                  -> {"items":[...],"next_cursor":null}; sắp xếp id giảm dần,
                                  cursor là id cuối cùng của trang trước; limit tối đa 100.
PATCH|DELETE /api/transactions/{id}   (người tạo hoặc Chủ hộ, BR4); PATCH nhận các trường
                                      occurred_on, total_amount, category_id, note.
GET  /api/dashboard?period=2026-10
  -> {"period":"2026-10","total":0,"by_category":[{"category_id":1,"name":"...","amount":0}],
      "by_member":[{"user_id":1,"display_name":"...","amount":0}],"by_week":[{"week_start":"2026-10-05","amount":0}]}
  period is required (YYYY-MM); totals include CONFIRMED transactions only.

Ngân sách: period trong path phải có dạng YYYY-MM. household_id luôn được xác định
từ người dùng đã xác thực và membership hiện tại; client không gửi household_id.
Member và Owner được xem ngân sách; chỉ Owner được lưu ngân sách hoặc yêu cầu gợi ý.

GET /api/budgets/{period}
  -> {"budget":{"period":"2026-10","income_estimate":20000000,"savings_goal":2000000,
      "source":"MANUAL","status":"ACTIVE","allocations":[
        {"category_id":1,"name":"Ăn uống","amount":5000000}]}}
  Nếu hộ chưa có ngân sách cho kỳ này: 200 {"budget":null}.
  allocations chỉ gồm các dòng đã lưu; tên danh mục được trả để hiển thị.

PUT /api/budgets/{period}
  body: {"income_estimate":20000000,"savings_goal":2000000,
         "allocations":[{"category_id":1,"amount":5000000},
                        {"category_id":3,"amount":2000000}]}
  -> 201 {"budget":{"period":"2026-10","income_estimate":20000000,"savings_goal":2000000,
      "source":"MANUAL","status":"ACTIVE","allocations":[...]}} khi tạo mới;
     200 với cùng schema khi thay thế ngân sách đã có.
  PUT là thay thế toàn bộ ngân sách của kỳ: dòng phân bổ không có trong body sẽ bị xóa.
  Gửi lại cùng body cho cùng kỳ là idempotent. Kỳ đã có được cập nhật, không trả 409.
  Server đặt source=MANUAL và status=ACTIVE; client không được truyền hai trường này.
  Lưu budget và toàn bộ budget_lines trong cùng transaction; nếu có lỗi thì rollback tất cả.

POST /api/budgets/{period}/suggest
  body: {"income_estimate":20000000,"savings_goal":2000000}
  -> 200 {"suggestion":{"period":"2026-10","income_estimate":20000000,
      "savings_goal":2000000,"source":"RULE","status":"DRAFT",
      "allocations":[{"category_id":1,"name":"Ăn uống","amount":5000000}]}}
  Gợi ý theo luật lấy mức chi CONFIRMED trung bình của từng danh mục trong ba tháng lịch
  hoàn chỉnh ngay trước period đích (hệ số 1,0); nếu tổng vượt phần thu nhập còn lại sau
  tiết kiệm, các khoản được co tỷ lệ để tổng không vượt giới hạn.
  Gợi ý không được ghi vào budgets/budget_lines; người dùng xem/chỉnh sửa rồi gọi PUT riêng.
  Server phải kiểm chứng gợi ý bằng quy tắc ngân sách trước khi trả về. Nếu LLM lỗi hoặc
  trả dữ liệu không hợp lệ, dùng gợi ý theo luật và trả source=RULE; nếu dùng LLM hợp lệ,
  trả source=LLM. Cả hai trường hợp đều trả status=DRAFT.
  Gemini chỉ nhận income_estimate, savings_goal, danh mục được phép và tổng CONFIRMED theo
  danh mục/tháng trong ba kỳ trước; không gửi household_id, user identity hoặc giao dịch thô.
  Đầu ra phải là JSON {"allocations":[{"category_id":1,"amount":1000000}]}; category lạ,
  amount không nguyên/âm/trùng hoặc tổng vượt thu nhập khả dụng làm toàn bộ gợi ý chuyển
  sang fallback RULE.

Quy tắc ngân sách và lỗi:
  - income_estimate, savings_goal và allocations[].amount là số nguyên VND không âm;
    boolean, số thập phân và chuỗi số không hợp lệ.
  - Tổng allocations[].amount + savings_goal không được vượt income_estimate.
  - category_id phải là số nguyên dương, không lặp trong request, và phải trỏ tới danh mục
    hệ thống (household_id IS NULL) hoặc danh mục thuộc đúng household. Không tự tạo danh mục.
  - period sai định dạng, thiếu trường, kiểu dữ liệu sai, số âm, danh mục không hợp lệ hoặc
    tổng vượt giới hạn: 422 VALIDATION.
  - Chưa đăng nhập: 401; Member gọi PUT hoặc suggest: 403; không có household/không tìm thấy
    dữ liệu trong phạm vi household: 404 NOT_FOUND.
  - Lỗi dùng chung theo envelope {"error":{"code","message","request_id"}}. BUD-01…10
    trong docs/test-cases-budget.md là các ca chấp nhận; riêng BUD-10 áp dụng semantics PUT
    cập nhật kỳ đã tồn tại như mô tả trên.

Hóa đơn định kỳ: household_id lấy từ membership; mọi thao tác chỉ truy vấn trong hộ hiện tại.
Member và Owner được xem; chỉ Owner được tạo, sửa hoặc xóa. Hóa đơn tạm dừng vẫn xuất hiện
trong danh sách với active=false nhưng không được job nhắc hạn xử lý.

GET /api/recurring-bills
  -> {"items":[{"id":4,"name":"Internet","category_id":4,"due_day":15,
      "expected_amount":450000,"remind_days_before":3,"active":true}]}
  Bao gồm cả hóa đơn active và tạm dừng; sắp xếp theo due_day rồi id.

POST /api/recurring-bills
  body: {"name":"Internet","category_id":4,"due_day":15,
         "expected_amount":450000,"remind_days_before":3,"active":true}
  Bắt buộc name và due_day; category_id/expected_amount có thể null; mặc định
  remind_days_before=3, active=true. -> 201 {"bill":{...}}.

PATCH /api/recurring-bills/{id}
  Nhận một hoặc nhiều trường trong body POST để cập nhật một phần; -> 200 {"bill":{...}}.
DELETE /api/recurring-bills/{id} -> 204.
  name phải dài 1–100 ký tự; due_day từ 1–31; expected_amount là số nguyên không âm hoặc null;
  remind_days_before từ 0–30; active là boolean; category_id phải là danh mục hệ thống hoặc
  thuộc hộ hiện tại. Trường không hỗ trợ/sai kiểu/sai giá trị trả 422 VALIDATION; không có
  household hoặc không tìm thấy bill trong hộ trả 404; Member ghi dữ liệu trả 403.

Lỗi: {"error":{"code","message","request_id"}}; hộ khác luôn trả 404.
