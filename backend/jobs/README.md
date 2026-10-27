# Worker

Chạy các lệnh dưới đây từ thư mục `backend`. Để worker nhận thông điệp, hãy
cấu hình `SQS_QUEUE_URL`, thông tin xác thực AWS và Gemini:

```powershell
python jobs/worker.py
```

Worker long-poll SQS với thời gian chờ 20 giây, in một dòng log JSON cho mỗi
thông điệp, sau đó xóa thông điệp khỏi queue. Có thể đặt `AWS_REGION` để chọn
region; mặc định là `ap-southeast-1`.

Để chạy thử với một tệp local và lưu bản nháp vào database, không dùng SQS/S3:

```powershell
python -m jobs.worker --file ocr-lab\data_small\001.jpg --household-id 1 --user-id 1
```

Chạy lệnh trên từ thư mục `backend`. Ở chế độ `--file`, cần cấu hình Gemini và
MySQL trong `backend/.env`; AWS không cần thiết. Worker gọi Gemini và ghi
receipt cùng giao dịch nháp vào MySQL, không tạo client SQS hoặc S3.

Worker nhận một message mỗi lần, chờ tối đa 20 giây và chạy tuần tự. Message
chỉ bị xóa sau khi xử lý thành công hoặc nhận được sự kiện `s3:TestEvent`.
Nếu xử lý thất bại, message được giữ lại để thử lại sau visibility timeout;
từ lần nhận thứ ba, receipt được đánh dấu `FAILED` và lỗi được ném tiếp để SQS
có thể chuyển message vào DLQ theo redrive policy.

## Tác vụ nhắc hạn và cảnh báo ngân sách

Chạy lệnh từ thư mục `backend`. Hai entrypoint dùng ngày tại
`Asia/Ho_Chi_Minh` khi không truyền `--period-key`; có thể truyền ngày để chạy
lặp lại có kiểm soát:

```powershell
python -m jobs.recurring_alerts reminders --period-key 2026-10-28
python -m jobs.recurring_alerts budget-alerts --period-key 2026-10-28
```

`reminders` gửi email cho thành viên hộ khi hóa đơn định kỳ đến ngày nhắc,
điều chỉnh ngày đến hạn về ngày cuối tháng nếu `due_day` lớn hơn số ngày trong
tháng. `budget-alerts` tính chi tiêu `CONFIRMED` trong kỳ hiện tại và gửi một
cảnh báo khi từng danh mục chạm 80% hoặc 100% ngân sách đang `ACTIVE`.

Các lần chạy được ghi trong `job_runs`; trạng thái `FAILED` có thể chạy lại,
`RUNNING` cũ hơn 30 phút có thể được claim lại. Bảng `alert_state` đảm bảo mỗi
mốc 80%/100% chỉ gửi một lần cho mỗi hộ, kỳ và danh mục. Alert state chỉ commit
sau khi SES chấp nhận email; nếu gửi lỗi, transaction rollback và job trả mã lỗi
để Scheduler có thể retry. SES gửi qua AWS task role, không dùng credential nhúng.

Cấu hình `SES_FROM_ADDRESS` bằng địa chỉ đã xác minh trong SES. Trong SES
sandbox, mọi địa chỉ nhận cũng phải được xác minh. Nếu hộ chưa có địa chỉ email,
job ghi log skip; log chỉ chứa mã hộ/danh mục và số lượng, không ghi email hay số
tiền. `AWS_REGION` mặc định là `ap-southeast-1`. Scheduler nên gọi một trong hai
command trên mỗi ngày; `--period-key` chỉ cần dùng cho chạy lại/đối chiếu thủ công.
