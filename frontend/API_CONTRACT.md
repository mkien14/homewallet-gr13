# Hợp đồng API cho frontend HomeWallet

Đây là hợp đồng tích hợp đề xuất cho phần frontend của Thức. Backend hiện chỉ có health/ping; các endpoint nghiệp vụ dưới đây cần Kiên triển khai và thống nhất trước khi kiểm thử với hệ thống thật. Frontend hiển thị lỗi khi API thiếu, không tạo dữ liệu giả để báo thành công.

## Quy ước chung

- Cùng origin với website: `VITE_API_BASE_URL=/api`. CloudFront chuyển nguyên đường dẫn `/api/*` tới ALB, không bỏ tiền tố `/api`.
- Mọi endpoint nghiệp vụ nhận `Authorization: Bearer <access_token>` của Cognito. ID token dành cho thông tin người dùng; backend phải xác minh chữ ký JWKS, issuer, `token_use=access`, app client và hạn token, rồi kiểm tra quyền hộ gia đình.
- Body JSON dùng `Content-Type: application/json`. ID là chuỗi; tiền tệ là mã ISO 4217 (ví dụ `VND`), vai trò là `OWNER` hoặc `MEMBER` (frontend cũng chuẩn hóa chữ thường từ backend).
- Không tin `household_id` do frontend gửi: backend phải đối chiếu tài khoản từ JWT với bảng thành viên.
- Trả HTTP status đúng; không trả HTML hoặc HTTP 200 cho lỗi. Lỗi khuyến nghị:

```json
{
  "error": {
    "code": "HOUSEHOLD_ACCESS_DENIED",
    "message": "Bạn không có quyền truy cập hộ gia đình này."
  },
  "request_id": "trace-id-if-available"
}
```

| Status | Nghĩa và xử lý frontend |
| --- | --- |
| `400` / `422` | Hiển thị thông tin đầu vào không hợp lệ; giữ nội dung biểu mẫu. |
| `401` | Phiên đăng nhập không còn hợp lệ; yêu cầu đăng nhập lại. |
| `403` | Không đủ quyền; không giả định thành viên chỉ dựa vào lựa chọn trên UI. |
| `404` | Không tìm thấy hộ hoặc endpoint; hiển thị lỗi tích hợp. |
| `409` | Đã tham gia hộ hoặc dữ liệu trùng; giữ biểu mẫu và thông báo. |
| `413` | Kích thước ảnh vượt chính sách upload. |
| `429` | Giữ biểu mẫu, đợi rồi thao tác lại có chủ đích; không tự lặp POST tạo dữ liệu. |
| `408` / `5xx` | Với GET có thể tải lại; với POST tạo receipt đã gửi, coi kết quả tạo là chưa xác định và đối soát backend trước khi tạo lại. |

## Hộ gia đình

`GET /api/households` trả `200` và danh sách hộ người dùng có quyền truy cập:

```json
{
  "households": [
    {
      "id": "household-123",
      "name": "Gia đình Nguyễn",
      "role": "OWNER",
      "currency": "VND",
      "invite_code": "ABC12345"
    }
  ]
}
```

Danh sách rỗng hợp lệ là `{"households": []}`. `invite_code` là trường tùy chọn, chỉ trả khi quyền cho phép; backend quyết định việc cấp, hết hạn và đổi mã.

`POST /api/households` nhận `{"name": "Gia đình Nguyễn"}`. Backend gán người tạo làm Owner và tiền tệ mặc định `VND`; trả `201` với `{"household": {...}}` theo cấu trúc trên. Frontend giới hạn tên 1–100 ký tự sau khi bỏ khoảng trắng hai đầu; backend áp dụng cùng quy tắc.

`POST /api/households/join` nhận `{"invite_code": "ABC12345"}`. Backend xác minh mã và thêm người dùng làm Member; trả `200` hoặc `201` với `{"household": {...}}`. Mã sai/hết hạn trả `400` hoặc `404`, đã tham gia trả `409`. Frontend không tự tăng quyền hoặc tự tạo thành viên.

## Tạo hóa đơn và cấp presigned POST

`POST /api/receipts` nhận metadata **của file đã nén**, không phải file gốc:

```json
{
  "household_id": "household-123",
  "filename": "hoa-don.jpg",
  "content_type": "image/jpeg",
  "size_bytes": 182400
}
```

Backend kiểm tra thành viên, định dạng và kích thước; tạo bản ghi hóa đơn đang chờ upload; tạo key trong prefix của hộ; ký POST cho bucket receipts private. Policy phải ràng buộc key, `Content-Type=image/jpeg`, giới hạn `content-length-range` tối đa `2097152` byte và thời hạn ngắn. Khuyến nghị 5 phút; không gửi AWS credentials dài hạn. Chỉ backend có quyền ký. Phản hồi `201`:

```json
{
  "receipt_id": "receipt-456",
  "upload": {
    "url": "https://YOUR_PRIVATE_RECEIPTS_BUCKET.s3.ap-southeast-1.amazonaws.com/",
    "fields": {
      "key": "households/household-123/receipts/receipt-456.jpg",
      "Content-Type": "image/jpeg",
      "policy": "BASE64_POLICY_FROM_BACKEND",
      "x-amz-algorithm": "AWS4-HMAC-SHA256",
      "x-amz-credential": "TEMPORARY_SIGNING_CREDENTIAL_SCOPE",
      "x-amz-date": "20261016T000000Z",
      "x-amz-signature": "SIGNATURE_FROM_BACKEND"
    }
  }
}
```

Đây là ví dụ hình dạng dữ liệu, không phải chữ ký dùng được. Giữ nguyên mọi trường do backend trả, kể cả `x-amz-security-token` khi có; không tự tạo hay sửa chữ ký. `upload.url` phải là HTTPS của endpoint S3 hợp lệ.

Frontend ghép `FormData`: tất cả `upload.fields` trước, trường `file` cuối; POST trực tiếp tới `upload.url` với `credentials: "omit"`. Không gửi Bearer JWT, cookie, `Authorization` hay tự đặt multipart `Content-Type` tới S3. Trình duyệt tự đặt boundary. S3 nhận thành công bằng HTTP `200`, `201` hoặc `204`; frontend không yêu cầu JSON và không dùng `no-cors`. Quy tắc trường file cuối được mô tả trong [S3 POST Object](https://docs.aws.amazon.com/AmazonS3/latest/developerguide/RESTObjectPOST.html).

Giao diện chỉ báo “đã tải ảnh” sau khi S3 trả thành công. Việc OCR hoàn tất, lưu bản nháp hay xác nhận giao dịch cần backend/worker ở phần khác; upload thành công chưa có nghĩa OCR hoàn tất.

### Không rõ kết quả POST tạo hóa đơn

Sau khi `POST /api/receipts` đã được gửi, mất mạng, hủy request, HTTP `408`/`5xx`, response thành công không đọc được JSON hoặc không có `receipt_id` đều có thể xảy ra **sau khi backend đã tạo bản ghi**. API client trả `ReceiptUploadError` với `code: "RECEIPT_CREATION_UNKNOWN"`, `creationUncertain: true`, không tự tạo receipt khác. UI giữ ảnh và khóa nút gửi lại trong lượt tải hiện tại, yêu cầu kiểm tra trạng thái trên máy chủ. Lỗi xác thực/validation hoặc hủy trước khi request được gửi không thuộc trường hợp này.

Nếu response có `receipt_id` nhưng upload plan không hợp lệ, client giữ ID và khóa tạo lại để backend xử lý cùng hóa đơn. Với cả hai trường hợp, Kiên cần hỗ trợ đối soát receipt pending và idempotency cho POST tạo hóa đơn để có thể khôi phục an toàn. Frontend chưa có endpoint đối soát, không giả lập việc khôi phục.

Chọn lại ảnh hoặc tải lại trang bắt đầu lượt giao diện mới và không giữ khóa cũ; vì vậy frontend không bảo đảm chống trùng qua các lượt/trang. Người dùng cần đối soát backend **trước khi chủ động bắt đầu lại** với cùng hóa đơn. Không dùng retry tự động cho POST tạo receipt khi kết quả chưa xác định.

### Thử lại khi S3 lỗi

API client giữ `receipt_id` và upload plan nếu bước POST S3 lỗi. Nút thử lại tái sử dụng plan và file đã nén qua `resumeReceiptUpload`, không gọi POST tạo hóa đơn mới. Request đã tới S3 nhưng mất phản hồi vẫn có thể ghi cùng key, nên không sinh bản ghi trùng.

Nếu chữ ký hết hạn, thử lại cùng plan vẫn lỗi; người dùng cần liên hệ xử lý hoặc cấp lại chữ ký cho cùng hóa đơn theo thông báo của UI. Backend nên bổ sung endpoint cấp lại chữ ký cho **cùng** `receipt_id` trước khi đưa vào vận hành và dọn bản ghi pending bị bỏ dở. Frontend hiện không tự suy đoán hoặc gọi endpoint chưa có, không tự tạo hóa đơn mới khi chữ ký hết hạn.

## Chính sách ảnh và S3 CORS

Frontend nhận JPEG, PNG hoặc WebP tối đa 15 MiB (`15728640` byte), tối đa 40 megapixel sau giải mã; chuyển JPEG, cạnh dài tối đa 2000 px, đầu ra tối đa 2 MiB (`2097152` byte). Ảnh được mã hóa lại để bỏ metadata EXIF/GPS. Không gửi PDF/SVG/HEIC trong phiên bản này. Kiểm tra frontend hỗ trợ trải nghiệm; backend và policy S3 vẫn phải thực thi giới hạn.

Chi cấu hình CORS cho bucket receipts theo origin website thực tế; ví dụ cho môi trường dev và một distribution:

```json
[
  {
    "AllowedOrigins": [
      "http://localhost:5173",
      "https://REPLACE_DISTRIBUTION.cloudfront.net"
    ],
    "AllowedMethods": ["POST"],
    "AllowedHeaders": ["Content-Type"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 300
  }
]
```

Thay placeholder bằng origin thật, không có đường dẫn hay dấu `/` cuối. Bổ sung header cụ thể nếu hợp đồng upload đổi. Không thêm `OPTIONS` vào `AllowedMethods`: S3 tự xử lý preflight dựa trên phương thức POST. CORS không thay thế bucket policy hoặc presigned policy và không làm bucket public. Xem [cấu hình CORS của S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/ManageCorsUsing.html).
