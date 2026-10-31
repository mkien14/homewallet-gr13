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

## Weekly spending report

Run from the `backend` directory:

```powershell
python -m jobs.weekly_report
python -m jobs.weekly_report --period-key 2026-10-19
```

`period_key` is the Monday (`YYYY-MM-DD`) starting the report week. With no key, the job selects the previous complete week in `Asia/Ho_Chi_Minh`. The query uses `[Monday, next Monday)`, includes only `CONFIRMED` transactions, and produces total/count plus category and household-member breakdowns. It excludes drafts and transaction-level details.

The report query data has this shape; `total_amount` values are integer VND:

```json
{
  "transaction_count": 6,
  "total_amount": 1250000,
  "by_category": [
    {"category_id": 2, "name": "Ăn uống", "transaction_count": 4, "total_amount": 900000},
    {"category_id": null, "name": "Chưa phân loại", "transaction_count": 2, "total_amount": 350000}
  ],
  "by_member": [
    {"user_id": 7, "display_name": "Kien", "transaction_count": 6, "total_amount": 1250000}
  ]
}
```

Each household is claimed independently in `job_runs` using `job_name=WEEKLY_REPORT_HH_<household_id>` and the week-start date as `period_key`. `SUCCEEDED` is skipped; `FAILED` or `RUNNING` older than 30 minutes can be reclaimed. Empty reports or households without recipient email are skipped. The job sends a text email with BCC through the ECS task role and `SES_FROM_ADDRESS`; in SES sandbox, every recipient must be verified.

Terraform configures `python -m jobs.weekly_report` for Monday at 08:00 with timezone `Asia/Ho_Chi_Minh`. The ECS task receives `SES_FROM_ADDRESS` and DB credentials; its task role grants `ses:SendEmail` only on the verified SES identity. A database failure after SES accepts an email can cause a duplicate on a later rerun; SES and MySQL cannot provide exactly-once delivery.

## AWS dev schedules and Redis cache

The dev receipt worker has Textract fallback enabled. Its task role can call
`textract:AnalyzeExpense`; do not grant that action to the API or user roles.
The worker result log includes `ocr_source` (`gemini` or `textract`) so a fallback
run can be distinguished from a normal Gemini run. The `worker_image_tag` Terraform
variable defaults to `dev`; after Deploy Dev promotes the new backend image, that
workflow restarts the worker service so it pulls the promoted image.
The GitHub OIDC role is managed outside this Terraform stack. Its deploy policy
must allow `ecs:DescribeServices` and `ecs:UpdateService` on
`arn:aws:ecs:ap-southeast-1:179923444714:service/homewallet/worker` for that
workflow step; it does not need `iam:PassRole` because the workflow reuses the
existing worker task definition.

The API task role can list and delete versions only under
`receipts/uploads/*`. This is used by household deletion to remove all versions
and delete markers for that household's uploaded receipts before deleting its DB
records.

The `hw-jobs` Fargate task definition runs the same backend image as the API. EventBridge Scheduler overrides its command and runs these schedules in `Asia/Ho_Chi_Minh`:

| Schedule | Local time | Command |
| --- | --- | --- |
| `hw-recurring-reminders` | Daily 07:45 | `python -m jobs.recurring_alerts reminders` |
| `hw-weekly-report` | Monday 08:00 | `python -m jobs.weekly_report` |
| `hw-budget-alerts` | Daily 20:00 | `python -m jobs.recurring_alerts budget-alerts` |

The jobs use the RDS-managed secret for `DB_USER` and `DB_PASSWORD`. Their task role is `hw-weekly-report-task-role`; its only application permission is `ses:SendEmail` on the configured verified SES identity. Container logs go to `/ecs/hw-jobs` with a 14-day retention period. Scheduler retries failed `RunTask` API invocations twice for up to one hour. Scheduler cannot observe a container's later exit code, so a job that starts and then exits non-zero must be diagnosed from ECS stopped-task details and CloudWatch logs; its failed `job_runs` entry can then be retried by running the command again.

SES remains in sandbox. The sender identity is `homewallet26@gmail.com`; every household recipient must also be verified before SES will accept a scheduled email. Otherwise the task will log/fail at SES send time even though Scheduler started the task successfully.

The jobs task uses the mutable ECR tag `dev`. The Deploy Dev workflow promotes the image to that tag only after the API service reaches stability, and the ECR lifecycle policy retains the current `dev` image. After applying Terraform, run Deploy Dev so the latest Terraform-created `hw-api` task definition (including Redis environment variables and Secrets Manager reference) is deployed and the matching image is promoted for jobs.

Terraform provisions one private Redis 7.1 node in the data subnets with encryption at rest, TLS, and an AUTH token in Secrets Manager. Only the API service has the dedicated security group accepted by Redis; the receipt worker and scheduled jobs use the shared app security group without Redis ingress. The API receives the Redis endpoint and token at task start. Dashboard cache failures remain cache misses: MySQL stays authoritative and the dashboard query continues without Redis.
