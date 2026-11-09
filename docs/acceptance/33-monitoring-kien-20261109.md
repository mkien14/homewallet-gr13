# Nghiệm thu #33: giám sát dev (09/11/2026)

Người kiểm tra: Kiên. Môi trường: AWS account `179923444714`, region
`ap-southeast-1`. Các lệnh kiểm tra AWS trong ghi chú này chỉ đọc, trừ lần
`sns publish` kiểm tra kênh email đã thực hiện trước đó.

## Kết quả hạ tầng giám sát

- Dashboard `homewallet-dev-operations` tồn tại và có 8 biểu đồ: ALB 5xx,
  CPU và memory của API, CPU và memory của worker, CPU và dung lượng trống RDS,
  số message hiện trong `receipts-dlq`.
- Có đủ 8 alarm `homewallet-dev-*`. Tất cả bật action gửi đến SNS topic
  `homewallet-dev-operations`. Tại thời điểm kiểm tra: 7 `OK`, alarm
  `homewallet-dev-dlq-visible` là `ALARM`.
- Subscription email `homewallet26@gmail.com` đã xác nhận
  (`PendingConfirmation=false`). Lệnh `sns publish` kiểm tra trả về MessageId
  `f8796696-b54a-55c0-81d0-05fc643b98fd`, và hộp thư đã nhận email
  `HomeWallet dev monitoring test`.
- Lịch sử alarm DLQ ghi nhận action SNS thực thi thành công lúc
  `2026-11-09 00:13:49 +07:00`. Không có bằng chứng email của **lần chuyển
  ALARM đó** đã đến hộp thư; email kiểm tra sau khi xác nhận subscription
  chứng minh kênh SNS → email đang hoạt động.

## Điều tra alarm DLQ

- `receipts-dlq` hiện có 1 message visible, 0 message đang xử lý; do đó alarm
  `ALARM` phản ánh đúng trạng thái queue. Message này có trước bài tải D4 ngày
  09/11, không quy lỗi cho bài tải.
- S3 event trong message trỏ tới receipt `id=1`, `household_id=1`. Task ECS
  tra cứu DB kết thúc `STOPPED`, exit code `0`, trả về `status=FAILED`,
  `error_code=WORKER_MAX_ATTEMPTS`, `created_at=2026-10-25 08:25:44`,
  `processed_at=2026-10-25 08:31:46`.
- `WORKER_MAX_ATTEMPTS` chỉ cho biết worker đã hết số lần thử; chưa xác định
  lỗi gốc. Không tìm thấy log worker tương ứng trong dữ liệu CloudWatch Logs
  còn giữ. Mã `backend/jobs/pipeline.py` từ chối xử lý lại receipt đã `FAILED`,
  nên redrive nguyên message này sẽ không khôi phục receipt.

## Kết luận và việc tiếp theo

**Đạt nghiệm thu #33 về triển khai giám sát, phát hiện DLQ và đường gửi SNS
email.** Alarm DLQ vẫn phải ở `ALARM` cho tới khi sự cố receipt cũ được xử lý
theo quyết định riêng. Chưa xác nhận đường alarm → email bằng một transition
mới sau lúc subscription được xác nhận.

Giữ message DLQ và receipt làm bằng chứng; không purge queue, xóa message,
đổi alarm sang `OK` bằng tay hay redrive trực tiếp. Người phụ trách receipt cần
điều tra lỗi gốc từ dữ liệu còn lại, quyết định khôi phục hay đóng sự cố, rồi
ghi lại cách xử lý và kiểm tra alarm trở về `OK` theo metric thực tế. Không
được coi việc alarm còn đỏ là lỗi của cấu hình #33.
