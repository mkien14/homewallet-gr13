# Cập nhật frontend dev — 13/11/2026

**Kết quả: DEPLOYED_VERIFIED.** Kiên yêu cầu xử lý frontend chưa được cập nhật.
Website hiện có: https://daoedidcrnf1f.cloudfront.net.

## Nguồn và phạm vi

- Code giao diện từ main `63fd2b9ae935097c557f56adbf1928aaa9e8ef13`, có UI lịch
  sử hộ/giải tán của Hoàng, tương thích API `hw-api:22` đã triển khai.
- Hai file package.json/package-lock.json lấy bản vá dependency trên nhánh
  `fix/production-integration`. Đây là bản vá local chưa commit; không mô tả
  artifact này là bản nguyên trạng của main. Bản main ban đầu audit có 1 HIGH;
  sau ghép dependency patch, npm audit báo 0 lỗ hổng.
- Build ID: `dev-63fd2b9ae935-7005744427cc`. Thông tin nguồn, profile dev,
  dependency_patch=true và bundle hash có trong `/release.json` trên website.
- Các thay đổi UI production chưa commit (privacy/MFA/consent) không thuộc
  lần publish này. Backend/container/hạ tầng production chưa được triển khai.
- Build thực hiện từ archive source trong thư mục tạm, không checkout hoặc
  thay đổi các file công việc đang làm dở trong repo. Không tạo clone/worktree.

## Cách cập nhật

1. Đọc lại account, CloudFront, bucket đích, API/profile và SPA client. Giữ
   React/SRP, API thật và public push configuration khớp bundle đang chạy.
   Không ghi token, mật khẩu hoặc khóa push vào biên bản.
2. npm ci, audit, lint và build thành công. Không chạy bộ test hoặc thực hiện
   thao tác nghiệp vụ bằng tài khoản thật.
3. Trước publish, xác nhận S3 index và CloudFront index giống nhau; bundle cũ
   chưa có route `/api/me/household-history`. Đây là thiếu bản frontend mới,
   không chỉ là cache trình duyệt.
4. Bucket frontend chưa bật versioning, nên sao lưu các root object sẽ ghi đè,
   nội dung và metadata vào thư mục tạm trước khi upload. Giữ mọi asset cũ.
5. Upload 27 file; asset trước, index.html cuối cùng, có điều kiện ETag để chặn
   ghi đè một deployment đồng thời. Asset có immutable cache; root file no-store.
6. Yêu cầu invalidation `/*`; đã chờ trạng thái Completed.
7. Tải lại đủ 27 file qua HTTPS và đối chiếu SHA-256 với artifact. Các đường
   `/`, `/auth/react`, `/receipts` trả đúng index mới. Main asset hiện tại:
   `/assets/index-BGoyQVjx.js`.

## Trạng thái sau triển khai và giới hạn

- Backend vẫn `hw-api:22`, không có API/worker deploy trong lần này.
- Ba lịch Scheduler gốc vẫn DISABLED; không gửi email/push hoặc sửa subscription.
- Không thay dữ liệu hộ, hóa đơn, giao dịch hoặc DLQ. Không apply Terraform.
- Nhánh làm việc vẫn `fix/production-integration`; không commit/push thay Kiên.
- Kiểm tra artifact/HTTP không thay thế nghiệm thu UI đã đăng nhập hoặc E2E.
- Production vẫn NO-GO theo [biên bản tích hợp](production-integration-20261113.md).

## Dự phòng local

Build, bản sao root object trước cập nhật, checksum và trạng thái triển khai lưu
ngoài Git dưới `%TEMP%/homewallet-frontend-main-20261113-tsro4wjb/` và
`%TEMP%/homewallet-frontend-deploy-20261113.json`.
Nếu cần phục hồi, kiểm tra ETag/current deployment trước, phục hồi root object
từ bản sao đã lưu (index sau cùng), rồi invalidation và kiểm tra lại artifact.
Không xóa asset cũ hoặc dùng file build từ nhánh/commit khác để chữa tạm.
