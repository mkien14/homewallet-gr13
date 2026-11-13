# Nghiệm thu triển khai production core — 13/11/2026

**Kết quả: PASS trong phạm vi phát hành cho 16 hộ đã được duyệt.**
Kiên là chủ vận hành. Chưa mở signup công khai, AI/OCR và Scheduler tiếp tục tắt.
Code hạ tầng/bằng chứng nằm trên `fix/production-live-rollout`, chưa commit/push
thay Kiên. Các số dưới đây là kết quả AWS thực tế, không suy từ việc merge PR.

## Release và cấu hình cuối

- Main: `1bba075aa1a6dd609d180f4610fe4f55d527cbdf` (PR #123).
- [Candidate build](https://github.com/mkien14/homewallet-gr13/actions/runs/43375269892):
  artifact `14014451095`, archive SHA-256
  `db5198be37cac02dc9b300eb7fb01c689310b33f27811677f805979c5a29cfc8`.
- ECR manifest digest:
  `sha256:74d74145723517d20330c9bd9d34cc58e8f41dbda96a8da8a1dfd629b6699527`.
  Artifact verifier đối chiếu image config digest của image đang chạy với candidate.
- Container scan gồm unfixed finding: **0 HIGH, 0 CRITICAL, 0 secret finding**.
  Không hạ ngưỡng hoặc ignore để vượt gate.
- API `hw-api:28` (2 task, 2 AZ), worker `hw-worker:5` (1 task), jobs `hw-jobs:5`.
  Cùng image/release, production profile, UID/GID 10001, drop ALL capabilities,
  init process và secret runtime. Worker không ReceiveMessage khi OCR tắt.
- https://daoedidcrnf1f.cloudfront.net — frontend/API cùng release, invalidation xong.
- HTTP API `4o95mvff40` → VPC Link → Cloud Map SRV → API. Hop public HTTPS;
  hop nội bộ HTTP. ALB cũ giữ cho health/rollback riêng; ingress public cũ đã đóng.
- RDS Multi-AZ, backup 14 ngày/deletion protection; Redis 2 AZ/failover/TLS/AUTH,
  backup 7 ngày; NAT mỗi AZ; log 30 ngày. Không thay primary bằng DB restore.
- Hai alarm HTTP API mới nối SNS đã confirm; budget 100 USD/month có notification.
  Budget là cảnh báo, không phải cap. Hai budget cũ được giữ.

## Phép thử đã thực hiện

| Ca | Kết quả và phạm vi |
| --- | --- |
| Main CI / candidate | Thành công; dùng artifact cùng main commit, không dùng image working-tree. |
| HTTPS canary | Thiếu origin secret → 403; có secret/thiếu JWT → 401; readiness/release → 200 đúng SHA. |
| Cutover/WAF | Chuyển edge sau canary, bật CommonRuleSet/IP rate BLOCK, chạy lại API có đăng nhập, rồi đóng ingress HTTP cũ. |
| DB/cache runtime | TLS MySQL và Redis/AUTH/RESP2, Unicode, TTL, INCR và atomic Lua bằng client mới trên Redis thật; xóa key thử. Chạy lại sau failover đạt. |
| API functions | SRP trực tiếp Cognito; GET/PATCH profile, categories, CRUD/idempotency giao dịch, dashboard, CSV, budget PUT/GET/rule suggestion, recurring bill CRUD, community read/admin denial, malformed JSON, cross-household 404. |
| Admission | User thử nhận 429 ở write thứ 31, có Retry-After, không trả từ cache. |
| Data boundary | Danh tính thử chưa có household → 403. Household 1 không nằm trong allowlist. Không đăng nhập giả danh chủ hộ 1 để thử. |
| API task recovery | Dừng đúng 1 task sau khi có hai task healthy/two-AZ; service tự tạo task thay và trở lại hai AZ. |
| Redis failover | `test_failover` một lần, primary thay đổi, automatic failover và API readiness trở lại; xác minh DB/cache bằng probe sau thử. |
| RDS failover | AWS có event bắt đầu/kết thúc requested Multi-AZ failover, khoảng 48,7 giây giữa hai event; readiness có 503 ngắn rồi phục hồi. Metadata AZ giữ nguyên, không dùng nó làm bằng chứng đổi AZ. |
| PITR | Restore riêng, TLS/migration 006/grants/read/commit-rollback/app startup/auth gate đạt; full validation khoảng 28,3 phút. |
| Snapshot restore | Restore riêng và cùng bộ kiểm tra đạt; full validation khoảng 24,4 phút. Restore point lag khoảng 118 giây. |
| API rollback | Trước promotion thử revision cũ và candidate; sau production thử `:26 → :27 → :26` giữ nguyên guard, hai AZ và readiness. Các pha khoảng 146/158 giây; :27 thử đã deregister. |
| Jobs | CLI `recurring_alerts --help` bằng image jobs production exit 0; không chạy job gửi thật trong đợt này. Cả ba schedule được cập nhật đúng target và giữ DISABLED. |
| Frontend/browser | Edge headless đăng nhập qua React/SRP và mở 10 trang chức năng, self-signup ẩn, OCR file input tắt; mobile 390×844 không tràn ngang; 0 page error/API 5xx trong phép thử. |
| Frontend version recovery | Bật versioning, copy 4 entry point từ VersionId, đối chiếu hash và release; cùng candidate, chưa thử frontend khác release. |
| Local infrastructure checks | fmt/validate dev và prod; mock tests dev 3, prod riêng 3; release-script tests 27 đạt. |
| Final gate | **90/90 PASS, GO**; Terraform final plan: **No changes**. |

Canary dùng hộ tổng hợp 27 do operator tạo, không chứa dữ liệu khách hàng.
Hộ và hai Cognito user thử đã xóa; ID 27 đã bỏ khỏi allowlist. Dữ liệu audit tổng
hợp có thể được giữ. Không gửi SES/push, gọi Gemini hoặc đưa ảnh vào OCR trong
phép thử production core. Phép thử mailbox/job lịch sử không được tính lại thành
nghiệm thu delivery của đợt phát hành này.

## Liên kết bằng chứng

- [Inventory/scan/ca API/checkpoint](production-live-20261113.json).
- [Preflight cuối](production-preflight-20261113.json).
- [Restore/failover/rollback](production-resilience-20261113.json).
- [Browser](production-browser-20261113.json).
- [Default dev downgrade guard](production-default-guard-20261113.json): plan sai
  profile bị `lifecycle.prevent_destroy` chặn; không apply plan này.
- [Bàn giao và điểm chuẩn rollback](../runbooks/current-stack-production.md).

State và input vận hành được lưu ngoài Git, ACL riêng trong
`%LOCALAPPDATA%\HomeWallet\production\20261113`. S3 state backend đã kiểm tra
private/encrypted/versioned. Giữ snapshot trước chuyển đổi đến 27/11, review trước
khi dọn. Các clone DB, SG/role, diagnostic path/analysis và revision probe thử
đã được dọn; primary/ảnh/DLQ hộ 1 không bị ghi đè hoặc replay/purge.

## Giới hạn và bước sau

- Không coi GO này là nghiệm thu đăng ký công khai, AI/OCR hoặc email Scheduler.
- Chưa có xác nhận thu hồi Google key cũ của HWAPI. Runtime không nạp key đó;
  bật lại phải có rotation/benchmark/quota/consent và đúng ranh giới dữ liệu.
- Chưa có xác nhận inbox nhận alarm SNS trong đợt này; subscription confirmed
  không thay bằng chứng nhận thư. Các mailbox E2E trước đây là biên bản riêng.
- Chưa thử mất toàn bộ AZ hoặc chạy tải dài để chứng minh throughput/SLA;
  CPU scaling policy được kiểm tra cấu hình. Restore chưa đổi endpoint primary.
- RTO đo cả thời gian polling/operator, không phải SLA. Version-copy frontend
  cùng candidate chỉ chứng minh cơ chế phục hồi object, không chứng minh tương
  thích với một frontend release khác.
- Kiên review/commit/push/merge nhánh hạ tầng này trước Terraform apply tiếp theo.
  Không checkout main cũ rồi apply default vào stack đã chuyển production.
