# Thông báo định kỳ — trạng thái production

Cập nhật **14/11/2026**: ba lịch đang **ENABLED**, cùng target jobs `hw-jobs:12`
của bản phát hành công khai `16f87ea`. [Biên bản phát hành và nghiệm thu](../acceptance/production-public-16f87ea-20261114.md).

| Lịch | Chức năng | Múi giờ và thời gian |
| --- | --- | --- |
| `hw-recurring-reminders` | Nhắc hạn hóa đơn | 07:45 hằng ngày, `Asia/Ho_Chi_Minh` |
| `hw-budget-alerts` | Cảnh báo ngân sách 80%/100% | 20:00 hằng ngày, `Asia/Ho_Chi_Minh` |
| `hw-weekly-report` | Báo cáo tuần hoàn chỉnh trước đó | 08:00 thứ Hai, `Asia/Ho_Chi_Minh` |

## Phạm vi và bằng chứng gửi

Job truy vấn dữ liệu bằng SQL với `household_id > 1`: hộ mới được phục vụ mà không
cần allowlist; household 1 luôn bị loại. Mỗi nghiệp vụ vẫn kiểm tra dữ liệu thuộc
hộ tương ứng. Bật schedule xác nhận trạng thái cấu hình, không xác nhận một email
cụ thể đã tới inbox. Kiểm tra kỳ gửi bằng log `job_runs`, số gửi/skip/fail của job
và hộp thư đã đăng ký; không chạy kỳ tương lai thủ công để gửi bù.

## Thay đổi release

1. Merge mã job lên `main`; CI, candidate và security scan phải đạt.
2. Review profile/plan đã lưu; API, worker, jobs và cả ba target phải cùng SHA và
   image digest. Không áp dụng stack `infra/envs/prod` vào stack đang chạy có tên dev.
3. Khi cập nhật target, tạm dừng lịch trong lúc chuyển, giữ nguyên expression,
   timezone, input, role, network và retry; kiểm tra target mới rồi mới bật lại.
4. Chạy production preflight và đối chiếu trạng thái AWS. Lịch ENABLED chỉ được
   coi là hoàn tất khi target trỏ đúng revision jobs đã review.
5. Ghi nhận riêng kết quả gửi của từng kỳ, không đưa địa chỉ email riêng vào Git.

## Dừng và rollback

Để ngăn gửi tiếp, đặt schedule về DISABLED trong AWS và cập nhật operator settings
để lần reconcile sau không bật lại. Khi rollback sang jobs revision không lọc
`household_id > 1`, giữ lịch tắt cho đến khi revision an toàn được khôi phục. Không
receive, purge hay replay DLQ/queue cũ trong thao tác release thông thường.
