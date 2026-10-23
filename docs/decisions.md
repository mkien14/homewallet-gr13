# Quyết định kỹ thuật

Các quyết định dưới đây là baseline của HomeWallet cho giai đoạn hiện tại. Khi thay
đổi, cần ghi ngày, lý do và ảnh hưởng trước khi cập nhật implementation hoặc hạ tầng.

## DEC-001: MySQL 8.4

- **Trạng thái:** Đã chốt
- **Quyết định:** Dùng MySQL 8.4 làm cơ sở dữ liệu quan hệ chính.
- **Lý do:** Phù hợp với schema SQL hiện có, RDS/AWS, giao dịch và ràng buộc
  quan hệ của household, receipt, transaction và budget.
- **Ảnh hưởng:** Migration và kiểm thử phải tương thích MySQL 8.4; không thêm
  cú pháp hoặc kiểu dữ liệu chỉ có ở hệ quản trị khác.

## DEC-002: Upload bằng presigned POST

- **Trạng thái:** Đã chốt
- **Quyết định:** API cấp presigned POST; trình duyệt tải trực tiếp lên S3 thay
  vì chuyển file qua backend.
- **Lý do:** Giảm tải cho API, giữ quyền upload ngắn hạn và giới hạn
  `Content-Type`/kích thước bằng policy của S3.
- **Ảnh hưởng:** API lưu receipt ở trạng thái `UPLOADING`; client phải gửi
  multipart POST tới S3 bằng URL và fields được cấp.

## DEC-003: Gemini là đường chính cho OCR

- **Trạng thái:** Đã chốt
- **Quyết định:** Gemini là OCR/AI path chính của sản phẩm.
- **Lý do:** Đây là đường tích hợp chính cần được tối ưu và đánh giá trước; các
  engine khác chỉ là phương án dự phòng hoặc dùng cho benchmark.
- **Ảnh hưởng:** Job xử lý receipt và bộ đánh giá phải ưu tiên Gemini, đồng thời
  ghi nhận lỗi và kết quả để có thể retry/đối chiếu.

## DEC-004: Không dùng custom error response của CloudFront

- **Trạng thái:** Đã chốt
- **Quyết định:** Không cấu hình custom error response của CloudFront cho API.
- **Lý do:** Giữ nguyên status code và payload lỗi do backend kiểm soát, tránh
  biến lỗi API thành response chung của CDN.
- **Ảnh hưởng:** Client và kiểm thử phải dựa trên contract lỗi của backend; các
  route API lỗi không được phụ thuộc vào trang lỗi HTML của CloudFront.
