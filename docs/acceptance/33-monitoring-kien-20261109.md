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

## Read-only follow-up ngày 2026-11-10

AWS CLI được xác nhận chạy bằng IAM user `kien` trong account `179923444714`,
region `ap-southeast-1`. Chỉ đọc attributes và CloudWatch metrics; không nhận
message, sửa queue, sửa DB, hay thay đổi alarm.

| Đối tượng | Trạng thái đọc được |
| --- | --- |
| `receipts-queue` | 0 visible / 0 in-flight / 0 delayed; retention 345600 giây (4 ngày); visibility timeout 180 giây; redrive `maxReceiveCount=3` tới `receipts-dlq` |
| `receipts-dlq` | 1 visible / 0 in-flight / 0 delayed; retention 1209600 giây (14 ngày); không cấu hình redrive policy trên chính DLQ |
| CloudWatch alarm `homewallet-dev-dlq-visible` | Vẫn `ALARM`; threshold 1; cập nhật `2026-11-09T00:13:49+07:00` |
| CloudWatch log group `/ecs/hw-worker` | Retention 14 ngày; log cũ hơn thời hạn này không còn là nguồn phù hợp để xác định lỗi ngày 2026-10-25 |
| `ApproximateAgeOfOldestMessage` của DLQ | Khoảng 969601 giây (~11,22 ngày) tại datapoint `2026-11-10T17:50+07:00` |

Tuổi DLQ không phải enqueue timestamp gốc. Với standard SQS queue, thời điểm hết hạn
dựa trên enqueue timestamp ban đầu; metric age của DLQ bắt đầu khi message chuyển vào
DLQ. Vì vậy không suy ra ngày hết hạn chính xác từ datapoint này hoặc từ `created_at`
của receipt. [AWS mô tả retention và timestamp của DLQ](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/setting-up-dead-letter-queue-retention.html).

Mã `backend/jobs/pipeline.py` hiện ném lỗi nếu receipt ở trạng thái `FAILED`, còn
`backend/jobs/worker.py` để message lỗi cho SQS redrive sau `WORKER_MAX_ATTEMPTS`.
Do đó redrive message nguyên trạng không phải quy trình khôi phục. Hồ sơ trước đó
ghép message duy nhất trong DLQ với receipt `id=1`, `household_id=1`; lần kiểm tra
này không đọc body SQS để xác minh lại liên kết.

**Kết quả điều tra:** nguyên nhân gốc không xác định được từ log còn giữ; chỉ kết luận
được worker đã hết số lần nhận và đánh dấu receipt `FAILED`. Cần chủ sở hữu dữ liệu
quyết định receipt/S3 object còn cần phục hồi hay được phép loại bỏ. Giữ nguyên
receipt, object và DLQ message cho tới khi có quyết định đó; chưa chạy redrive hoặc
cleanup. Việc này là disposition của dữ liệu cũ, tách biệt với nghiệm thu cấu hình
monitoring #33 đã đạt.
