# Bật lại thông báo định kỳ trên stack production

Yêu cầu vận hành ngày 14/11/2026: bật lại ba lịch, tiếp tục giữ hộ 1 ngoài phạm vi.
Đã bật **ENABLED lúc 09:15:18 ngày 14/11/2026 (UTC+7)**, target `hw-jobs:10`.
Xem [biên bản đã áp dụng](../acceptance/production-schedules-5f2308c-20261114.md).
Gate 96/96 GO, Terraform No changes; input production/operator settings đã đồng bộ.
ENABLED không thay bằng chứng nhận thư của mỗi kỳ tương lai.

| Tên | Chức năng | Giờ Việt Nam (`Asia/Ho_Chi_Minh`) |
| --- | --- | --- |
| `hw-recurring-reminders` | Nhắc hạn hóa đơn đang hoạt động | 07:45 mỗi ngày |
| `hw-budget-alerts` | Cảnh báo ngân sách đạt 80%/100% | 20:00 mỗi ngày |
| `hw-weekly-report` | Tổng hợp tuần hoàn chỉnh trước đó | 08:00 thứ Hai |

## Điều kiện và triển khai

1. Merge bản sửa `jobs.household_scope` vào main; CI và Build release candidate
   phải đạt. Giữ OCR bật trong candidate. Triển khai cùng artifact/image đã quét
   cho frontend, API, worker và jobs theo runbook production hiện tại.
2. Jobs production phải có allowlist hợp lệ, không chứa hộ 1. Cả ba truy vấn
   chọn hộ/hóa đơn/ngân sách được lọc ngay trong SQL; thiếu/sai allowlist thì
   dừng trước khi mở DB, ghi `job_runs`, gửi email hoặc push.
3. Đối chiếu target mới, expression, timezone, input, IAM role, private network
   và retry với bản chụp trước thay đổi. Không thay kỳ chạy để gửi bù.
4. Trong **tfvars production ngoài Git**, đặt `job_schedules_enabled=true` và
   `notifications_release_accepted=true`. Trong operator settings, đặt cùng hai
   giá trị. Đây là quyết định bật gửi định kỳ cho các hộ đã được admin duyệt;
   không mở rộng hộ hay thay đổi sở thích/ngôn ngữ người nhận.
5. Chạy plan toàn stack, đọc saved plan; phần bật lịch chỉ được đổi State của
   đúng ba schedule từ DISABLED sang ENABLED. Apply saved plan, đọc lại AWS và
   chạy preflight. Không dùng `-target` hoặc mở cả lịch bằng lệnh không giữ target.
6. Cập nhật biên bản và báo cáo Word/PDF/sơ đồ bằng trạng thái thực tế. ENABLED
   chứng minh lịch được bật; chỉ ghi nhận một kỳ gửi thành công khi có log task
   thực tế và kết quả nhận tương ứng. Không tự chạy job để gửi bù nhiều thư.

## Dừng gửi

Đặt cả hai bản cấu hình vận hành về `job_schedules_enabled=false`, plan/review/apply
và đọc lại ba trạng thái DISABLED. Việc tắt lịch ngăn invocation tương lai;
không tự dừng task đã chạy, xóa dữ liệu, xóa `job_runs` hay gửi lại kỳ cũ.

Các giới hạn dữ liệu, quota OCR và các bằng chứng HA/restore cũ vẫn theo
[runbook production](current-stack-production.md).

Trước rollback jobs về :9 hoặc revision cũ chưa có bộ lọc, phải tắt cả ba lịch.
Không giữ ENABLED trên job cũ chỉ vì API trước đó đã có allowlist.
