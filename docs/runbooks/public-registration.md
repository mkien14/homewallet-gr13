# Đăng ký công khai — production đã phát hành

Cập nhật 14/11/2026. Public release `16f87ea10d4fc6c47afd198e3ee77274fa6c3013`
đã triển khai lên website và cùng stack AWS hiện tại.

- [Biên bản nghiệm thu](../acceptance/production-public-16f87ea-20261114.md)
- Website: https://daoedidcrnf1f.cloudfront.net
- Runtime API/worker/jobs: `hw-api:38`, `hw-worker:14`, `hw-jobs:12`
- Cognito self-signup và email verification được bật; frontend React/SRP là chính.
- Production preflight: 99/99 GO; Terraform plan cuối: No changes.
- Admin xác nhận trực tiếp signup, email verification, login, tạo hộ và tham gia hộ.

## Hành vi và ranh giới dữ liệu

Người dùng xác minh email trước khi đăng nhập. Sau đăng nhập, họ có thể tạo hộ
hoặc dùng mã mời tham gia hộ. Đăng ký không cấp quyền admin. API kiểm tra membership
trong mọi truy vấn nghiệp vụ; household 1 cùng dữ liệu/ảnh/queue/DLQ lịch sử được
giữ riêng và không thể tham gia qua luồng mời công khai. Các job lọc trong SQL
`household_id > 1`. Tài khoản/hộ tổng hợp dùng nghiệm thu đã được dọn.

## Rollback và tạm dừng đăng ký

Rollback phải ghép frontend, Cognito policy, API, worker và jobs theo cùng một
release đã review. Không rollback jobs về revision chưa lọc household 1 khi ba lịch
đang ENABLED. Bản thử `:38 → :37 → :38` xác nhận :37 tạm tắt đăng ký; :38 được
khôi phục và kiểm readiness. Nếu cần đóng signup, cập nhật Cognito và frontend/runtime
qua change plan có review, đồng thời quyết định cách tiếp tục phục vụ các hộ mới đã
tạo; không xóa hoặc chuyển dữ liệu hộ.

Không dùng danh sách 16 hộ cũ làm allowlist mặc định sau khi đã có người dùng mới.
Giữ hộ 1 và dữ liệu ngoài phạm vi theo quy trình phục hồi có kiểm soát. Chi tiết
máy đọc được ở [acceptance JSON](../acceptance/production-public-16f87ea-20261114.json).
