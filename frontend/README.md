# HomeWallet frontend — phần của Thức

Ứng dụng React cho đăng nhập Cognito, tạo/tham gia/chọn hộ gia đình và tải ảnh hóa đơn có nén trên trình duyệt. Build tĩnh ở `dist/` để Chi đưa lên S3 private qua CloudFront. PR này chuẩn bị frontend và hướng dẫn tích hợp; chưa tạo tài nguyên AWS, chưa triển khai website và chưa bổ sung backend của Kiên.

## Chạy trên máy

Dùng Node.js theo yêu cầu `engines` trong `package.json`, cùng npm. Trong PowerShell:

```powershell
Set-Location D:\Cloud\homewallet\frontend
Copy-Item .env.example .env.local
npm ci
npm run dev
```

Điền cấu hình Cognito thật trong `.env.local`, mở `http://localhost:5173`. Frontend vẫn hiển thị trạng thái thiếu cấu hình nếu chưa điền; đăng nhập cần Cognito đã được Chi cấp. Vite chuyển `/api/*` tới `VITE_DEV_API_TARGET` trong môi trường dev; Flask cần chạy tại địa chỉ đó. Backend hiện chưa có endpoint hộ gia đình và presigned upload, vì vậy các thao tác đó sẽ báo lỗi cho tới khi tích hợp [API_CONTRACT.md](./API_CONTRACT.md).

```powershell
npm test
npm run build
npm run preview
```

`npm test` chạy kiểm thử frontend và routing CloudFront. `npm run build` tạo `dist/`. Nếu dùng preview để kiểm thử đăng nhập, phải đặt redirect/logout URL đúng cổng preview và thêm chúng vào Cognito; không trộn phiên OAuth localhost:5173 với cổng khác. Dev proxy chỉ phục vụ `npm run dev`; preview cần API cùng origin qua CDN hoặc reverse proxy riêng.

## Cấu hình công khai

| Biến | Giá trị / ý nghĩa |
| --- | --- |
| `VITE_COGNITO_AUTHORITY` | Issuer User Pool, ví dụ `https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_EXAMPLE`; không phải Hosted UI domain. |
| `VITE_COGNITO_DOMAIN` | Origin HTTPS của Cognito managed login/Hosted UI, ví dụ `https://example.auth.ap-southeast-1.amazoncognito.com`. |
| `VITE_COGNITO_CLIENT_ID` | App client công khai, **không có client secret**. |
| `VITE_COGNITO_REDIRECT_URI` | Local: `http://localhost:5173/auth/callback`; production: `https://YOUR_DISTRIBUTION.cloudfront.net/auth/callback`. |
| `VITE_COGNITO_LOGOUT_URI` | Local: `http://localhost:5173/`; production: `https://YOUR_DISTRIBUTION.cloudfront.net/`. |
| `VITE_API_BASE_URL` | `/api` để trình duyệt gọi cùng origin qua CloudFront. |
| `VITE_DEV_API_TARGET` | Chỉ cho Vite dev proxy, mặc định `http://127.0.0.1:5000`. |

Mọi `VITE_*` được đưa vào JavaScript công khai khi build. Không đặt AWS access key, Cognito client secret hay database password trong frontend. Cấu hình production cần được điền **trước** `npm run build`; thay file `.env` sau khi upload `dist/` không đổi cấu hình đã build.

## Đăng nhập và callback PKCE

Chi tạo Cognito User Pool domain và public app client, bật Authorization Code grant và scopes `openid email profile`; frontend gửi PKCE `S256` trong yêu cầu đăng nhập. Cho phép chính xác các callback và sign-out URL local/CloudFront trong bảng trên; scheme, domain, port, path và dấu `/` phải khớp.

Trình duyệt chuyển tới Cognito, nhận `code` và `state` tại `/auth/callback`, rồi đổi code bằng verifier của lần đăng nhập đó. Phiên được lưu trong `sessionStorage` của tab; API nhận **access token** trong Bearer header. Access token gần hết hạn được làm mới khi đọc phiên bằng refresh token nếu còn hợp lệ; khi không thể làm mới, người dùng đăng nhập lại. Không sao chép callback qua tab khác hoặc mở lại URL có code đã dùng. Xem [PKCE với Cognito](https://docs.aws.amazon.com/cognito/latest/developerguide/using-pkce-in-authorization-code.html) và [authorization endpoint](https://docs.aws.amazon.com/cognito/latest/developerguide/authorization-endpoint.html).

## Bàn giao CloudFront/S3/ALB cho Chi

Các luồng 01–08 được frontend hỗ trợ như sau:

| Luồng | Cách tích hợp |
| --- | --- |
| 01 Trình duyệt → CloudFront | Website dùng HTTPS 443; redirect HTTP sang HTTPS ở CDN. |
| 02 CloudFront → S3 frontend | React `dist/` từ S3 REST origin private bằng HTTPS và OAC. |
| 03 Trình duyệt ↔ Cognito | Authorization Code + PKCE; callback `/auth/callback`. |
| 04 Trình duyệt → CDN → ALB | `fetch('/api/...')`, Bearer access JWT; API không cache. |
| 05 ALB → Flask/ECS | Hạ tầng Chi quản lý; không sửa backend hay Terraform trong phần frontend. |
| 06–07 Cấp upload | POST metadata ảnh đã nén tới `/api/receipts`, nhận `receipt_id` và presigned POST. |
| 08 Trình duyệt → S3 receipts | FormData trực tiếp bằng chữ ký của backend; không gửi JWT/cookie tới S3. |

### Origin và behavior

1. S3 frontend dùng **REST endpoint**, bật Block Public Access; OAC ký request và bucket policy chỉ cho distribution đọc. Chọn OAC “Sign requests / always” để CDN → S3 dùng HTTPS. S3 website endpoint không hỗ trợ yêu cầu này. Xem [HTTPS giữa CloudFront và S3](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-https-cloudfront-to-s3-origin.html).
2. Default behavior → S3; chỉ `GET, HEAD` (thêm `OPTIONS` nếu cấu hình thực tế cần); Viewer protocol policy `Redirect HTTP to HTTPS`; bật nén. Đặt default root object `index.html`.
3. Behavior `/api/*` và `/api` đứng trước default, origin ALB, cho phép `GET, HEAD, OPTIONS, POST, PUT, PATCH, DELETE`; chuyển nguyên path/query/body. Dùng `CachingDisabled` (TTL 0) và origin request policy `AllViewerExceptHostHeader` hoặc policy tương đương thực sự chuyển `Authorization`, `Content-Type`, `Accept`, query strings và các header CORS cần thiết; không cache OPTIONS. `AllViewerExceptHostHeader` đặt Host theo origin. Xem [managed origin policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-origin-request-policies.html) và [forward Authorization](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/add-origin-custom-headers.html).
4. Chi phải bổ sung listener 443, chứng chỉ ACM hợp lệ theo DNS origin và security group trước khi chọn CDN → ALB `HTTPS Only`. `infra/modules/compute/alb.tf` hiện chỉ có listener **HTTP 80**. ALB → ECS dùng HTTP nội bộ theo target group hiện có. Frontend không tự thay đổi các tài nguyên này.
5. Custom domain của CloudFront dùng chứng chỉ ACM phù hợp ở `us-east-1`; callback Cognito phải dùng đúng domain người dùng mở. Hạn chế origin ALB theo thiết kế hạ tầng; backend vẫn kiểm tra JWT cho mọi API nghiệp vụ.

### Reload SPA và cache

Gắn [cloudfront-viewer-request.js](./deploy/cloudfront-viewer-request.js) ở viewer-request của **frontend S3 behaviors**. Function chỉ rewrite `GET/HEAD` cho `/`, `/households`, `/upload`, `/auth/callback` (và dấu `/` cuối) thành `/index.html`, giữ query OAuth nguyên vẹn. Khi thêm route React mới, cập nhật allowlist và test. Thay URI không đổi behavior/origin đã chọn; xem [CloudFront event structure](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/functions-event-structure.html).

Không thiết lập lỗi 403/404 toàn distribution thành `index.html`: lỗi API và asset thiếu phải giữ nguyên. Tạo behavior `/auth/callback*` → S3 với cache disabled, vẫn gắn function; chọn policy không đưa query code/state tới S3 hoặc cache key vì JavaScript đọc chúng trực tiếp từ URL trình duyệt. Đồng thời trả `Cache-Control: no-store` cho callback bằng response headers policy nếu cần tránh lưu ở trình duyệt.

Upload `dist/index.html` với `Cache-Control: no-cache, max-age=0, must-revalidate`; policy cache của các trang HTML cần minimum/default TTL 0 và tôn trọng header. File hash trong `dist/assets/` dùng `public, max-age=31536000, immutable`. Phân phối bản build đồng bộ, giữ assets cũ trong thời gian client còn mở trang và invalidate các đường dẫn HTML khi phát hành. Không cache response API cá nhân; thay đổi response headers policy không tự thay đổi cache tại edge.

### Bucket receipts

Bucket receipts tách khỏi bucket frontend, private. Cấu hình CORS POST cho origin local và domain CloudFront chính xác theo [API_CONTRACT.md](./API_CONTRACT.md). Backend giới hạn content type/kích thước/key/hạn chữ ký. Frontend chỉ dùng presigned POST, không cần AWS SDK hay AWS keys.

## Luồng người dùng

- Đăng nhập → chọn/tạo/tham gia hộ → mở trang tải hóa đơn. Vai trò Owner/Member lấy từ API; không suy đoán từ UI.
- Chọn JPEG/PNG/WebP ≤15 MiB và ≤40 megapixel → kiểm tra và nén JPEG ≤2 MiB (**2097152 byte**), cạnh dài ≤2000 px → xem ảnh/kích thước → yêu cầu cấp upload → POST S3. Đây là giới hạn MiB nhị phân của file JPEG thực tế, dùng cùng giá trị trong metadata API và policy S3.
- Khi truyền S3 chỉ hiển thị đang tải; `fetch` không cung cấp phần trăm upload chính xác. Chỉ báo thành công sau response S3 thành công; chưa khẳng định OCR hoặc ghi nhận giao dịch hoàn tất.
- Khi S3 lỗi, có thể thử lại cùng plan/file để tránh tạo receipt trùng. Chữ ký hết hạn cần backend cấp lại cho cùng receipt; xem hợp đồng API và giới hạn hiện tại.
- Nếu POST tạo receipt đã gửi nhưng mất phản hồi, bị hủy, trả `408`/`5xx` hoặc dữ liệu không có ID dùng được, client đánh dấu `creationUncertain`; UI khóa gửi lại trong lượt hiện tại vì backend có thể đã tạo hóa đơn. Cần Kiên đối soát pending receipt/idempotency trước khi tạo lại, không thử lại POST một cách máy móc. Chọn lại ảnh hoặc reload mất khóa của lượt cũ; frontend chưa bảo đảm chống trùng qua các lượt. Chi tiết ở [hợp đồng API](./API_CONTRACT.md#không-rõ-kết-quả-post-tạo-hóa-đơn).

## Checklist tích hợp thật

Các kiểm thử tự động trong repo không thay thế các bước dưới đây. Chỉ đánh dấu hoàn thành sau khi Chi/Kiên cung cấp AWS và API hoạt động.

- [ ] Đăng nhập từ localhost và domain CDN; callback đúng `/auth/callback`; request authorize có `response_type=code`, `code_challenge_method=S256`, state và nonce; token request có verifier, không có client secret.
- [ ] Từ chối callback thiếu/sai state, callback đã dùng, code hết hạn, provider báo lỗi; URL không còn code/state sau xử lý; không gửi API khi chưa đăng nhập.
- [ ] Đăng xuất về URL whitelist; phiên hết hạn/401 cho đăng nhập lại; reload giữ phiên cùng tab, không lưu token trong localStorage hoặc log.
- [ ] Hộ rỗng, tạo hộ, mã mời sai/hết hạn/trùng, member/owner, lỗi 403/5xx; API luôn kiểm tra quyền thực tế.
- [ ] Chọn JPEG/PNG/WebP nhỏ và ảnh 15 MiB, loại file sai, ảnh hỏng, ảnh quá lớn; ảnh xem trước đúng chiều, đầu ra JPEG đạt giới hạn và thông tin API khớp file đã nén.
- [ ] S3 trả 204/201 thành công, hết hạn chữ ký, mạng mất, CORS sai; lần thử lại không tự tạo receipt mới và UI không báo thành công trước response.
- [ ] Mất phản hồi/hủy sau POST tạo receipt, HTTP 408/5xx, JSON lỗi hoặc thiếu ID: hiện thông báo cần đối soát, khóa gửi lại trong lượt hiện tại, không phát sinh POST tạo mới; kiểm tra backend idempotency/đối soát trước khi bắt đầu lại.
- [ ] DevTools: JWT chỉ gửi tới API, mọi field ký giữ nguyên và `file` cuối, không JWT/cookie tới S3; kiểm tra policy backend chặn hộ khác/type sai/kích thước quá giới hạn.
- [ ] Tải trực tiếp/reload `/households`, `/upload`, `/auth/callback`; `/api/missing` giữ lỗi JSON, asset không tồn tại giữ 403/404; API không có cache hit của tài khoản khác.
- [ ] Website dùng HTTPS; kiểm tra CDN → S3/ALB TLS và ALB → ECS theo cấu hình Chi triển khai; S3 frontend/receipts không truy cập công khai.
- [ ] Kiểm tra điện thoại 375 px, bàn phím, nhãn biểu mẫu, focus và trạng thái loading/lỗi; chọn lại ảnh không giữ trạng thái cũ.
