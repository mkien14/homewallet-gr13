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
                                  -> 201 (gửi lại cùng khóa: 200 và trả bản ghi cũ)
GET  /api/transactions?period=2026-10&member_id=&category_id=&limit=50&cursor=
PATCH|DELETE /api/transactions/{id}   (người tạo hoặc Chủ hộ, BR4)
GET  /api/dashboard?period=2026-10
  -> {"period":"2026-10","total":0,"by_category":[{"category_id":1,"name":"...","amount":0}],
      "by_member":[{"user_id":1,"display_name":"...","amount":0}],"by_week":[{"week_start":"2026-10-05","amount":0}]}
Lỗi: {"error":{"code","message","request_id"}}; hộ khác luôn trả 404.
