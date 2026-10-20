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
