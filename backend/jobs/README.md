# Worker

Chạy các lệnh dưới đây từ thư mục `backend`. Để worker nhận thông điệp, hãy
cấu hình biến môi trường `SQS_QUEUE_URL` và thông tin xác thực AWS:

```powershell
python jobs/worker.py
```

Worker long-poll SQS với thời gian chờ 20 giây, in một dòng log JSON cho mỗi
thông điệp, sau đó xóa thông điệp khỏi queue. Có thể đặt `AWS_REGION` để chọn
region; mặc định là `ap-southeast-1`.

Để chạy thử với một tệp local mà không tạo client SQS hoặc S3:

```powershell
python jobs/worker.py --file C:\path\to\receipt.jpg
```

Ở chế độ tệp local, worker hiện kiểm tra tệp tồn tại, rồi in đường dẫn đầy đủ
và kích thước tệp dưới dạng JSON. Phần xử lý hóa đơn/OCR có thể được bổ sung
sau tại điểm vào này.
