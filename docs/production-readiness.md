# HomeWallet: trạng thái production trên stack hiện tại

Cập nhật 13/11/2026. Chủ vận hành: **Kiên**. Nhánh hạ tầng:
`fix/production-live-rollout`; Kiên thực hiện commit/push/merge.

Ứng dụng được phát hành từ main `1bba075aa1a6dd609d180f4610fe4f55d527cbdf`
(PR #123). Candidate GitHub Actions
[43375269892](https://github.com/mkien14/homewallet-gr13/actions/runs/43375269892)
đã build/quét thành công; API, worker, jobs và frontend cùng release này.
Digest ECR: `sha256:74d74145723517d20330c9bd9d34cc58e8f41dbda96a8da8a1dfd629b6699527`.
Đây là bản **core cho các hộ của nhóm đã được duyệt**, chưa mở đăng ký công khai.

## Đã triển khai và kiểm tra trên AWS

| Phần | Trạng thái hiện tại |
| --- | --- |
| Account/Region | `179923444714`, `ap-southeast-1`; giữ stack và dữ liệu hiện có. |
| Website | https://daoedidcrnf1f.cloudfront.net; không cần domain riêng. |
| HTTPS | Browser → CloudFront → HTTP API `4o95mvff40` bằng HTTPS; VPC Link → Cloud Map SRV → ECS dùng HTTP riêng trong VPC. Không tuyên bố TLS trên mọi hop. |
| Bypass origin | App kiểm tra khóa origin; gateway không có khóa trả 403, có khóa nhưng thiếu token trả 401. Ingress HTTP từ CloudFront vào ALB cũ đã đóng. |
| WAF | CommonRuleSet và giới hạn IP đã bật chặn; canary có đăng nhập đạt sau cutover. |
| API | Hai task ở hai AZ, readiness `/ready`, circuit breaker, autoscaling min 2/max 4 với CPU target 60%. |
| RDS | `homewallet-dev-mysql`, db.t4g.micro, Multi-AZ, private/encrypted; backup 14 ngày, bảo vệ xóa và final snapshot. |
| Redis | Hai node ở hai AZ, automatic failover, TLS/AUTH, snapshot 7 ngày; client Redis 8.1 đã thử trên server 7.1 thực tế. |
| Egress/logs | Một NAT cho mỗi AZ của app; log API/worker/jobs/migrate/gateway giữ 30 ngày. |
| Monitoring | Thêm alarm HTTP API 5xx và IntegrationLatency; SNS vận hành có một email subscription đã xác nhận. Chưa kiểm tra inbox nhận cảnh báo trong đợt này. |
| Dữ liệu | Allowlist cố định 16 household ID khác 1; hộ 1 và ảnh/dữ liệu/DLQ giữ theo quyết định trước. Không purge/replay DLQ. Hộ tương lai không tự được cấp quyền. |
| Đăng nhập | React/SRP chính, Hosted UI dự phòng; bỏ client CLI password flow và callback localhost, khóa tự đăng ký. User Pool bật deletion protection. |
| MFA | Kiên xác nhận challenge TOTP sau đăng nhập lại; metadata toàn bộ admin đang bật phù hợp. Root MFA và thiết bị MFA IAM operator đã kiểm tra. |
| Runtime | API/worker/jobs cùng immutable image; UID/GID 10001, drop ALL capabilities, init process; runtime DB credentials qua Secrets Manager/TLS. |
| Frontend | Candidate đã upload, invalidation hoàn tất, `/release.json` khớp `/api/release`; Edge qua 12 kiểm tra trang/mobile, không có page error hay API 5xx. |
| Lịch sử frontend | S3 versioning, giữ noncurrent version 30 ngày; đã thử copy phục hồi entry point cùng candidate và kiểm tra hash. |
| Budget | `HomeWallet-Production-Monthly`, 100 USD/tháng, cảnh báo actual 50/80/100% và forecast 100%; giữ hai budget cũ. Đây là cảnh báo tổng account, không phải hard cap hay cam kết HA tốn dưới 100 USD. |

Tên tài nguyên, tag `env=dev` và Terraform key `dev/terraform.tfstate` là tên cũ.
Stack này đã dùng cho production core; phát triển dùng local/mock. Không áp dụng
`infra/envs/prod`: đó là thiết kế stack riêng của PR #103. Không chạy Deploy Dev.

## Bằng chứng nghiệm thu

- [Restore/HA/rollback đúng stack](acceptance/production-resilience-20261113.json):
  PITR và snapshot tạo DB riêng; kiểm tra TLS, migration 006, quyền runtime,
  commit/rollback dữ liệu tổng hợp và chạy ứng dụng. Không ghi đè primary.
  Thời gian đến kiểm tra ứng dụng đạt khoảng **28,3 phút / 24,4 phút**;
  độ trễ restore point khoảng **118 giây**. DB/SG/role thử đã được dọn.
- Redis đã chuyển primary; API tự thay một task bị dừng và trở về hai AZ;
  RDS ghi nhận sự kiện bắt đầu/kết thúc failover và API phục hồi. Metadata AZ
  RDS không đổi trong phép thử, nên không tuyên bố đã quan sát đổi AZ.
- Rollback production giữa hai revision giữ nguyên guard đã đạt; không dùng
  `hw-api:22` làm rollback sau khi đóng ranh giới production.
- [Browser thực tế](acceptance/production-browser-20261113.json): SRP, các tab,
  tự đăng ký bị ẩn, OCR upload bị tắt, màn 390×844 không tràn ngang.
- [Biên bản triển khai](acceptance/production-live-20261113.md), preflight cuối
  và inventory lưu trong cùng thư mục acceptance.

Ngưỡng kiểm tra restore là RPO 15 phút/RTO một giờ cho phép thử có kiểm soát;
đây chưa phải SLA. Chưa diễn tập mất cả AZ, chưa chạy tải kéo dài để công bố năng
lực tối đa, chưa chuyển DNS primary sang DB phục hồi. Thử rollback frontend
sử dụng cùng candidate, chưa hạ về frontend release khác.

## Tính năng chủ động giữ tắt

- **Gemini/OCR:** `false`, không nạp Gemini key vào API/worker. Khóa đã lộ vẫn
  cần chủ Google project HWAPI xác nhận thu hồi. Đổi secret AWS không thu hồi
  khóa Google. Chưa coi #34/provider benchmark là đạt production.
- **Scheduler:** ba lịch DISABLED và trỏ jobs production. Chỉ bật sau review
  người nhận, opt-out, bounce/complaint, delivery, idempotency và stop procedure.
  Không dùng dữ liệu hộ 1 để thử gửi hoặc OCR.
- Có thể dùng nhập chi tiêu, ngân sách/gợi ý bằng rule, hộ, cộng đồng, xem hóa
  đơn đã có, thông báo trong ứng dụng và thiết lập bảo mật trong phạm vi duyệt.

## Vận hành tiếp theo

Xem [bàn giao stack](runbooks/current-stack-production.md) và
[runbook phát hành](production-rollout.md). Không đưa tfvars, Terraform state,
image artifact, token, mật khẩu hoặc email subscriber riêng vào Git.
Preflight yêu cầu topology AWS lẫn bằng chứng cùng release/image, đúng
account/Region/DB và không quá 30 ngày; không sửa attestation để vượt gate.
