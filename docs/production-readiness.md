# HomeWallet: production trên stack hiện tại

Cập nhật **14/11/2026**. Chủ vận hành: **Kiên**.
**Đã nghiệm thu bản bàn giao cho 16 hộ đã duyệt**, có OCR kiểm tra consent và quota.
Không mở đăng ký công khai. Không phát sinh yêu cầu mua domain/account AWS khác.

## Điểm chuẩn đang chạy

| Phần | Trạng thái |
| --- | --- |
| Website | https://daoedidcrnf1f.cloudfront.net |
| Source / candidate | Main `5f2308ce8dc1b03bf63f9c7f9d5747ea410a1c8d`; [run 43542308036](https://github.com/mkien14/homewallet-gr13/actions/runs/43542308036) |
| Image | `sha256:7aebb61f9261145388427440ed53d4238ddf71d477293cb1a42e811af7ec4832`; scan 0 HIGH/CRITICAL/secret finding |
| Runtime | API `hw-api:36`, worker `hw-worker:12`, jobs `hw-jobs:10`; cùng immutable image và SHA |
| Lịch định kỳ | Ba lịch ENABLED; 07:45 hằng ngày, 20:00 hằng ngày, 08:00 thứ Hai; Asia/Ho_Chi_Minh; jobs lọc allowlist SQL |
| Frontend | Cùng artifact; invalidation hoàn tất, hash index và phiên bản public khớp |
| HTTPS | Browser → CloudFront → HTTP API `4o95mvff40` bằng HTTPS; VPC Link → Cloud Map → ECS dùng HTTP trong VPC |
| Origin/WAF | Kiểm tra origin secret; đóng ingress ALB công khai cũ; CommonRuleSet và rate rule bật chặn |
| API/HA | Hai task ở hai AZ; readiness/circuit breaker; scaling min 2/max 4, CPU target 60% |
| RDS | `homewallet-dev-mysql`, MySQL 8.4/db.t4g.micro, private/encrypted/TLS/Multi-AZ; backup 14 ngày, bảo vệ xóa |
| Redis/egress | Hai node/TLS/AUTH/failover, snapshot 7 ngày; NAT riêng mỗi AZ app |
| Log/monitoring | Log giữ 30 ngày; alarm gateway 5xx/latency và SNS subscription đã confirm |
| Đăng nhập | React/SRP chính, Hosted UI dự phòng; admin TOTP; khóa signup và callback localhost |
| OCR | Worker Gemini `gemini-3.5-flash-lite`; consent audit, membership/allowlist, prefix/queue riêng; cap 10 attempts/ngày UTC |
| Ngân sách | Cảnh báo AWS 100 USD/tháng; không tự ngắt tài nguyên hoặc giới hạn tiền Google |
| Terraform | Kết nối Secrets Manager đã hoạt động; saved plan/apply hoàn tất; plan cuối **No changes** |
| Gate cuối | **96/96 GO**, sau cập nhật jobs và bật ba lịch; Terraform No changes |

Tên/tag `dev` và state key `dev/terraform.tfstate` là tên cũ của stack đang dùng.
Phát triển dùng local/mock; không chạy Deploy Dev hoặc apply `infra/envs/prod`
vào stack này. TLS không được tuyên bố trên mọi hop nội bộ.

## Nghiệm thu

- [Bản cập nhật jobs/lịch](acceptance/production-schedules-5f2308c-20261114.md):
  cùng candidate mới, scope SQL trên DB phục hồi, rollback :36→:34→:36,
  hai clone khởi động bằng image mới và ba trạng thái ENABLED. Không gửi bù;
  thư của kỳ tương lai cần log/nhận riêng. Các ca OCR/Edge/failover dưới đây
  giữ đúng revision và thời điểm cũ; source API/OCR/UI/IaC/dependency không đổi.
- [Biên bản release](acceptance/production-release-a5097aa-20261114.md): CI,
  checksum/scan, cùng image/version, Edge SRP/TOTP, 12 kiểm tra trang/mobile,
  không page error/API 5xx. Local 234 PASS/60 SKIP; MySQL/policy riêng 15 PASS.
- [OCR](acceptance/production-ocr-a5097aa-20261114.json): upload có consent →
  S3 → queue → worker → Gemini → draft đúng cửa hàng/ngày/tổng/dòng hàng →
  xác nhận giao dịch. Kiểm tra policy, cap bằng audit thật và replay không gọi
  thêm provider. Chỉ dùng ảnh tổng hợp. Runtime grant SELECT/INSERT audit đã áp dụng.
- [Resilience](acceptance/production-resilience-a5097aa-20261114.json): PITR và
  snapshot sang DB riêng, đúng candidate; khoảng 14,6/11,2 phút; restore point
  trễ 254 giây. Thay task API, Redis/RDS failover, TLS/Lua và rollback API đạt.
  Clone/SG/role thử đã dọn, không ghi đè primary. RDS metadata AZ không đổi.

## Phạm vi giữ nguyên

16 hộ: `2,3,4,5,6,7,8,9,11,12,13,22,23,24,25,26`. Hộ 1 và ảnh/dữ liệu/
queue/DLQ cũ giữ theo quy trình có kiểm soát; không receive/purge/replay queue cũ.
Hộ/tài khoản/ảnh thử đã dọn; audit provider giữ để không reset quota. Hộ tương lai
không tự được đưa vào allowlist.

Chỉ worker nhận Gemini key mới. Kiên xác nhận thu hồi khóa cũ tại Google HWAPI;
đây là attestation của chủ project. API gợi ý ngân sách dùng rule, Textract
fallback tắt. Ba Scheduler **ENABLED** theo yêu cầu bật lại ngày 14/11/2026.
Tắt lịch trước khi rollback jobs về revision :9 chưa có bộ lọc hộ.

Một canary không thay benchmark chất lượng rộng #34, quota Google còn lại hay
SLA. Chưa diễn tập mất cả AZ, chưa chuyển primary endpoint sang DB phục hồi,
chưa kiểm inbox alarm trong đợt này. Đây là giới hạn bằng chứng đã ghi nhận.

Xem [bàn giao vận hành](runbooks/current-stack-production.md) và
[quy trình release](production-rollout.md). Không đưa state/tfvars, artifact,
token/key, email subscriber riêng hoặc DOCX hướng dẫn các tuần vào Git.
