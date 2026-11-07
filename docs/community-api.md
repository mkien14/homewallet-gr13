# D2 / #29 — Community và quyền moderation

Ngày cập nhật: 2026-11-07. Trạng thái: contract triển khai, **chờ Kiên và Thức xác nhận**.
Bản hướng dẫn tuần 10 được cung cấp không chứa “mục 2” được D2 tham chiếu;
cần đối chiếu mục đó trước khi chốt. Tài liệu này mô tả implementation hiện tại.

## Phạm vi và quyền

- Nội dung gồm mẹo tiết kiệm (`tip`) và mẫu ngân sách dạng văn bản (`budget_template`).
- Community dùng chung giữa các user đã đăng nhập; không lấy nội dung từ giao dịch hộ.
  Không yêu cầu user đã tham gia household. “Member” trong contract này là user
  đăng nhập không có group admin; cần Kiên/Thức xác nhận cách hiểu này.
- Mọi endpoint yêu cầu `Authorization: Bearer <access token>`. Backend verify
  RS256/JWKS, hạn token, issuer, `token_use=access`, client_id trước khi đọc quyền.
- Admin phải có phần tử chính xác `homewallet-dev-admins` trong mảng `cognito:groups`.
  Household owner, `role=admin`, custom attribute, body, query và localStorage không cấp quyền.
- Chi review Terraform group; Kiên apply và thêm duy nhất user dev được chọn.
  API không có thao tác tự cấp quyền; `PATCH /api/me` chỉ nhận `preferred_locale`.
- Nút đổi vai trò ở mock chỉ dùng dữ liệu trình duyệt; backend không có route
  `/api/mock/community/admin`. Không dùng mock làm bằng chứng authorization.
- Không làm comment, chat, khóa user, category CRUD hay nhập nội dung từ giao dịch hộ.

AWS mô tả group claim và xác minh JWT tại:
[group membership](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-user-groups.html),
[JWT verification](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-verifying-a-jwt.html).

## Schema bài viết

```json
{
  "id": 12,
  "type": "tip",
  "title": "Tắt thiết bị khi không sử dụng",
  "body": "Nội dung chia sẻ do người dùng nhập.",
  "status": "PENDING",
  "author": "Thành viên demo",
  "updated_at": "2026-11-07T03:00:00"
}
```

`id` là số nguyên. `author` là display_name đã trim, hoặc `null` để UI hiển thị
“Thành viên”; không fallback sang email. Response không trả author_id, cognito_sub,
email hay household_id. `updated_at` lấy từ DATETIME của DB; môi trường triển khai
phải dùng UTC (UI đang diễn giải timestamp này theo UTC).

## Endpoint

### GET /api/community/posts

Quyền: mọi user đăng nhập. `200 {"items": [post, ...]}`.

Luôn chỉ trả `APPROVED`. Mọi query `status`, kể cả `PENDING`, `HIDDEN`, `ALL`, bị
bỏ qua ở endpoint này. Không có endpoint member đọc riêng bài theo ID hoặc hàng chờ.
Response tạo bài vẫn trả bài `PENDING` vừa tạo cho chính người gửi.

### POST /api/community/posts

Body bắt buộc có **đúng** ba trường:

```json
{"type":"tip","title":"Tắt thiết bị","body":"Tắt khi không sử dụng."}
```

- `type`: chuỗi `tip` hoặc `budget_template`, phân biệt hoa thường.
- `title`: chuỗi, trim rồi dài 1–120 ký tự.
- `body`: chuỗi, trim rồi dài 1–3000 ký tự; là plain text, không render HTML.
- Thiếu trường, thêm trường hoặc sai kiểu/giá trị: `422 VALIDATION`.
  Không nhận `status`, `author_id`, `household_id`, `role` hay group từ client.
- Backend lấy author từ user đã xác thực, luôn đặt `PENDING`, kể cả người gửi là admin.
- Thành công: `201 {"post": post}`. Không có idempotency key; gửi lại có thể tạo bài mới.

### GET /api/admin/community/posts?status=PENDING

Quyền: admin. `200 {"items": [post, ...]}`.

- Không truyền `status`: trả tất cả ba trạng thái.
- Có truyền: uppercase trước khi kiểm tra, chỉ nhận `PENDING`, `APPROVED`, `HIDDEN`.
  Chuỗi rỗng/giá trị khác: `422 VALIDATION`.
- Cả hai API danh sách sắp xếp `updated_at DESC, id DESC`.
- Hiện chưa có pagination; không diễn giải `limit`/`cursor` là chức năng đã hỗ trợ.

### PATCH /api/admin/community/posts/{id}

Quyền: admin. Body không rỗng; chỉ nhận một hoặc nhiều trường `title`, `body`, `status`.
Title/body theo validation POST. Status phân biệt hoa thường, chỉ nhận ba giá trị trên.
Không cho đổi type hoặc tác giả. Thành công: `200 {"post": post}`.

| Thao tác | Body ví dụ | Hành vi |
| --- | --- | --- |
| Duyệt / khôi phục hiển thị | `{"status":"APPROVED"}` | Bài xuất hiện trong feed |
| Sửa nội dung | `{"title":"Tiêu đề mới","body":"Nội dung mới"}` | Giữ nguyên status |
| Ẩn | `{"status":"HIDDEN"}` | Bài biến mất khỏi feed |
| Đưa lại chờ duyệt | `{"status":"PENDING"}` | Không xuất hiện trong feed |

Cho phép chuyển từ bất kỳ status hiện tại sang bất kỳ status hợp lệ nào, kể cả
gửi lại cùng status. Mỗi PATCH thành công tạo một audit event; không cam kết
deduplicate audit khi retry. Bài không tồn tại trả `404 NOT_FOUND` cho admin;
member luôn bị `403` trước khi tra cứu ID. Không có DELETE trong phạm vi D2.

## Audit và transaction

Tạo bài ghi `COMMUNITY_POST_CREATED`; mọi PATCH ghi `COMMUNITY_POST_UPDATED`.
Action hiện chưa phân biệt riêng approve/edit/hide; Kiên/Thức cần xác nhận semantics này.
Không lưu before/after body để phân biệt thao tác.

Audit chỉ có `id`, `actor_id`, `action`, `entity='community_post'`, `entity_id`, `at`.
Không lưu title/body, token, email, household_id hoặc dữ liệu hộ. `at` do DB đặt.
Read, validation failure, forbidden và not-found không ghi audit community.

Ghi bài và audit cùng transaction. PATCH khóa bài bằng `SELECT ... FOR UPDATE`.
Nếu ghi audit lỗi, rollback cả thay đổi bài. Việc tạo/cập nhật hồ sơ user trong
middleware auth là transaction riêng, không nằm trong cam kết rollback bài/audit.

## Lỗi chung

```json
{"error":{"code":"FORBIDDEN","message":"...","request_id":"..."}}
```

`X-Request-Id` ở response trùng request_id trong lỗi.

| HTTP | Trường hợp |
| --- | --- |
| 400 BAD_REQUEST | Request ghi không phải JSON object |
| 401 UNAUTHENTICATED / INVALID_TOKEN / TOKEN_EXPIRED | Thiếu token hoặc token không hợp lệ |
| 403 FORBIDDEN | User đã xác thực không có group admin gọi admin API |
| 404 NOT_FOUND | Admin cập nhật ID không tồn tại; route không tồn tại |
| 422 VALIDATION | Sai field/giá trị/filter |
| 500 INTERNAL | Lỗi ghi DB/audit; bài/audit được rollback khi đang trong transaction |

Lỗi cấu hình/JWKS/profile vẫn theo middleware auth chung (500/503/502).

## Xác nhận cần có trước khi đóng D2

| Người | Nội dung | Trạng thái |
| --- | --- | --- |
| Kiên | Đối chiếu mục 2; quyền user chưa có household; chuyển trạng thái; audit action | Chờ xác nhận |
| Thức | Schema response, `author=null`, filter, lỗi, UI với token mới và API thật | Chờ xác nhận |
| Chi | Resource group và plan Terraform | Chờ review |

Ma trận và cách chạy: [test-cases-community.md](test-cases-community.md).
