# Production 5f2308c — bật lại ba lịch định kỳ

**PASS trong phạm vi ghi dưới đây**, cập nhật 14/11/2026. Chủ vận hành: Kiên.
Nguồn chi tiết: [JSON release/schedules](production-schedules-5f2308c-20261114.json)
và [restore/rollback](production-resilience-5f2308c-20261114.json).

## Release và kiểm tra

- Source `5f2308ce8dc1b03bf63f9c7f9d5747ea410a1c8d`, PR #134.
- [Candidate 43542308036](https://github.com/mkien14/homewallet-gr13/actions/runs/43542308036),
  artifact `14092630636`; 6 kiểm tra CI và candidate thành công.
- Image `sha256:7aebb61f9261145388427440ed53d4238ddf71d477293cb1a42e811af7ec4832`;
  HIGH=0, CRITICAL=0, secret findings=0. Frontend/API/worker/jobs cùng artifact/SHA.
- API `hw-api:36` (2/2, hai AZ); worker `hw-worker:12` (1/1); jobs `hw-jobs:10`.
- Frontend invalidation hoàn tất; hash index khớp artifact và hai public release
  endpoint cùng SHA. Gate **96/96 GO**; Terraform plan cuối exit 0/No changes.

## Ba lịch đã bật

AWS xác nhận **ENABLED lúc 09:15:18 ngày 14/11/2026, UTC+7** trong group
`homewallet-dev-jobs`; cùng target `hw-jobs:10`.

| Lịch | Giờ Việt Nam, `Asia/Ho_Chi_Minh` | Expression |
| --- | --- | --- |
| `hw-recurring-reminders` | 07:45 mỗi ngày | `cron(45 7 * * ? *)` |
| `hw-budget-alerts` | 20:00 mỗi ngày | `cron(0 20 * * ? *)` |
| `hw-weekly-report` | 08:00 thứ Hai | `cron(0 8 ? * MON *)` |

Saved plan phần bật lịch chỉ đổi State của đúng ba resource; giữ nguyên target,
input, timezone, expression, IAM role, network và retry. Hai cờ
`job_schedules_enabled=true`, `notifications_release_accepted=true` đã lưu trong
tfvars/operator settings ngoài Git. Không gọi job gửi ngay hoặc gửi bù kỳ cũ.

## Kiểm soát phạm vi và bằng chứng

Jobs lọc SQL theo 16 hộ đã duyệt; hộ 1 được giữ riêng. Kiểm trên DB phục hồi có
hộ 1 cho thấy selectors chỉ trả đúng phạm vi; scope rỗng không chọn dữ liệu và
18 ca cấu hình thiếu/sai bị chặn trước DB. Probe cuối PASS, không gửi email/push
và không ghi dữ liệu. Lần probe đầu sửa phép so sánh tuple rỗng/list trong công cụ
kiểm; mã production không đổi giữa hai lần. Chi tiết giữ trong JSON.

Candidate mới khởi động trên cả PITR/snapshot clone, kiểm TLS/schema/grants và
auth/readiness; API rollback `:36 → :34 → :36` đạt. Clone/SG/role tạm đã dọn,
primary không bị ghi đè; checkpoint cũ giữ nguyên. Các phép task replacement,
RDS/Redis failover của a5097aa giữ đúng release/timestamp cũ, không tuyên bố đã
chạy lại. IaC, dependency, API/OCR và frontend source không đổi; chỉ jobs thay.

## Giới hạn và dừng gửi

ENABLED là bằng chứng cấu hình đã bật, chưa phải xác nhận nhận thư của kỳ tương
lai. Email/push E2E trước đây vẫn có nguồn và thời điểm riêng. Không mở rộng hộ,
không nhận/xóa/replay queue cũ, không reset quota OCR hoặc thay đổi dữ liệu hộ 1.

Khi dừng gửi, đặt `job_schedules_enabled=false` ở cả tfvars và operator settings,
review/apply rồi đọc lại ba trạng thái. **Tắt cả ba lịch trước khi rollback jobs
về :9 hoặc revision cũ chưa có bộ lọc hộ.** Tắt lịch không dừng task đang chạy.

Xem [runbook](../runbooks/scheduled-notifications.md). State/tfvars/artifact,
key/token và DOCX hướng dẫn tuần tiếp tục nằm ngoài Git.
