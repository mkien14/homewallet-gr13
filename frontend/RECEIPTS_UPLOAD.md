# Tải ảnh hóa đơn trực tiếp lên S3 bằng presigned POST

Module này thực hiện luồng 08 của HomeWallet: trình duyệt nhận URL và các trường đã được API ký, rồi gửi ảnh trực tiếp tới S3 qua HTTPS. Module dùng API có sẵn của trình duyệt, không phụ thuộc React, Cognito, AWS SDK hay biến môi trường.

## Sử dụng

```js
import { uploadToS3 } from './src/receipts/s3-upload.mjs';

// Phản hồi do backend cấp sau khi kiểm tra quyền truy cập hộ gia đình.
const { receipt_id, upload } = apiResponse;
const controller = new AbortController();

try {
  await uploadToS3({
    url: upload.url,
    fields: upload.fields,
    file: preparedImage,
    signal: controller.signal,
  });
  // Chỉ ghi nhận đã tải ảnh. OCR và xác nhận giao dịch là bước tiếp theo.
  showUploadedReceipt(receipt_id);
} catch (error) {
  // Giữ receipt_id, file và upload để có thể tiếp tục cùng hóa đơn.
  showUploadError(error.message);
}
```

Các tên `apiResponse`, `preparedImage`, `showUploadedReceipt` và `showUploadError` minh họa cách ứng dụng gọi module, không phải API được định nghĩa trong PR này. Bên gọi chuẩn bị ảnh JPEG/PNG/WebP không rỗng, tối đa 2 MiB (2.097.152 byte). Module không nén ảnh và không tự gọi API tạo hóa đơn.

Phần thông tin S3 tối thiểu có dạng:

```json
{
  "receipt_id": "receipt-123",
  "upload": {
    "url": "https://homewallet-receipts.s3.ap-southeast-1.amazonaws.com/",
    "fields": {
      "key": "households/7/receipts/receipt-123.jpg",
      "Content-Type": "image/jpeg",
      "policy": "POLICY_FROM_BACKEND",
      "x-amz-algorithm": "AWS4-HMAC-SHA256",
      "x-amz-credential": "SIGNING_SCOPE_FROM_BACKEND",
      "x-amz-date": "DATE_FROM_BACKEND",
      "x-amz-signature": "SIGNATURE_FROM_BACKEND"
    }
  }
}
```

Các giá trị trên là ví dụ cấu trúc, không phải chữ ký dùng được. Module giữ nguyên mọi trường API cung cấp, gồm cả `x-amz-security-token` nếu có; thêm chúng vào `FormData` trước và thêm trường `file` cuối. Trình duyệt tự tạo multipart boundary. Request không có Bearer JWT, cookie hoặc header `Content-Type` tự đặt; redirect bị chặn. Quy tắc file cuối được nêu trong [S3 POST Object](https://docs.aws.amazon.com/AmazonS3/latest/API/RESTObjectPOST.html).

URL phải là HTTPS của S3 bucket virtual-host endpoint tiêu chuẩn, tại đường dẫn gốc, không có query, fragment, cổng riêng hoặc thông tin đăng nhập. Hỗ trợ endpoint global, regional và legacy regional; partition China phải khớp region. Tên bucket chứa dấu chấm không được hỗ trợ để tránh vấn đề chứng chỉ HTTPS wildcard. Access point, S3 website, S3-compatible storage hoặc CDN upload URL không thuộc hợp đồng module này.

## Kết quả và thử lại

- Promise chỉ hoàn tất thành công khi S3 trả HTTP thành công; giá trị trả về là `{ status }`. Response `204` không cần body JSON.
- `PresignedPostUploadError` cung cấp `code`, `status` và thông báo kiểm soát cho URL/fields/file không hợp lệ, hủy, mất mạng hoặc lỗi HTTP. Nội dung lỗi thô của S3 không được đưa ra giao diện.
- `onProgress` là callback tùy chọn với mốc `0` trước khi gửi và `100` khi thành công; đây là trạng thái bắt đầu/hoàn thành, không phải số phần trăm byte đã truyền.
- Module không tự retry, không tạo receipt mới và không thay đổi signed fields. Bên gọi giữ receipt ID, cùng file và plan khi thử lại. Nếu S3 đã nhận ảnh nhưng phản hồi bị mất, thử lại cùng key có thể phát sinh một phiên bản object/sự kiện mới; worker cần xử lý idempotent.
- HTTP `403` có thể do chữ ký hết hạn, policy hoặc quyền. Backend cần cấp lại chữ ký cho cùng receipt khi cần; không tạo receipt khác để thay thế một lần tải lỗi.

## Điều kiện tích hợp

Backend kiểm tra JWT và membership, quản lý receipt/key, cấp presigned POST có thời hạn với policy ràng buộc loại ảnh, dung lượng và prefix. Chi cấu hình bucket receipts private, quyền ký, mã hóa và CORS POST cho đúng origin frontend. Module trình duyệt không quyết định hoặc chứng minh bucket đang private.

Phần đăng nhập, hộ gia đình, nén ảnh, API cấp chữ ký, giao diện và hạ tầng CloudFront/S3 được triển khai riêng. PR này chỉ thêm module tải S3, kiểm thử của module và tài liệu này. Chưa xác nhận upload đầu cuối trên AWS thật.

## Chạy kiểm thử độc lập

Trong thư mục gốc repository, dùng Node.js 22 trở lên:

```powershell
node --test frontend/tests/s3-upload.test.mjs
```

Không cần cài npm package hoặc AWS credentials. Fetch trong kiểm thử được giả lập để kiểm tra FormData, giới hạn URL/file, cách xử lý lỗi, hủy và dữ liệu ký mà không gửi ảnh tới AWS.
