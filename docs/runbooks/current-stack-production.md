# Bàn giao production — stack hiện tại

Cập nhật **14/11/2026**. Chủ vận hành/dữ liệu: **Kiên**.
Biên bản hiện hành: [phát hành công khai 16f87ea](../acceptance/production-public-16f87ea-20261114.md); hồ sơ trước đó được giữ làm lịch sử.
Kiên giữ quyền commit/push/merge tài liệu vận hành.

## 1. Điểm chuẩn

| Thành phần | Giá trị |
| --- | --- |
| Website | https://daoedidcrnf1f.cloudfront.net |
| Main / candidate | `16f87ea10d4fc6c47afd198e3ee77274fa6c3013` / [43567562979](https://github.com/mkien14/homewallet-gr13/actions/runs/43567562979) |
| API / worker / jobs | `hw-api:38` / `hw-worker:14` / `hw-jobs:12` |
| ECR image | `homewallet-backend@sha256:7c2a2473aabe3536d6dbca2dd509589f782955104b69438d2a9e7e8767b43b23` |
| Scheduler | Ba lịch ENABLED, target jobs :12; truy vấn phục vụ `household_id > 1`; Asia/Ho_Chi_Minh |
| Account / Region | `179923444714` / `ap-southeast-1` |
| CloudFront / HTTP API | `E1FBDSJYV9WAKM` / `4o95mvff40` |
| RDS / Redis | `homewallet-dev-mysql` / `homewallet-dev-redis` |
| Frontend bucket | `hw-frontend-dev-179923444714`, private/OAC/versioned |
| State | Bucket `hw-tfstate-homewallet-gr13`, key `dev/terraform.tfstate`, encrypted/private/versioned, S3 lockfile |
| Restore checkpoint | `hw-prod-before-core-20261113-df1fc11e`, review giữ/dọn ngày 27/11/2026 |
| Gate / Terraform | 99/99 GO; plan cuối No changes |

Tên/tag `dev` là tên cũ của stack production hiện tại. Không rename tài nguyên,
không chạy Deploy Dev hoặc apply `infra/envs/prod` vào đây. Phát triển dùng local/mock.

## 2. Cấu hình vận hành ngoài Git

```powershell
$ops = Join-Path $env:LOCALAPPDATA 'HomeWallet\production\20261113'
$productionVars = Join-Path $ops 'production.tfvars.json'
$productionSettings = Join-Path $ops 'operator-settings.json'
```

Thư mục giới hạn ACL cho operator, SYSTEM và Administrators. Bản ghi release mới
nằm trong `public-registration-20261114`; root tfvars/settings, active release,
checkpoint frontend và rollback đã cập nhật. Bản cũ giữ để truy vết. Không upload thư mục này: state
có thể chứa secret, tfvars chứa email nhận budget. Bàn giao sang máy khác bằng
kênh bảo mật, cấp AWS identity/MFA phù hợp; không đưa access key vào repo/chat.

## 3. Kiểm tra chỉ đọc

```powershell
$actualAccount = aws sts get-caller-identity --query Account --output text
if ($LASTEXITCODE -ne 0 -or $actualAccount -ne '179923444714') { throw 'Sai account' }
.\backend\.venv\Scripts\python.exe .\scripts\production-preflight.py --settings $productionSettings
if ($LASTEXITCODE -ne 0) { throw 'NO_GO: xử lý gate lỗi, không sửa attestation để vượt gate' }
aws ecs describe-services --region ap-southeast-1 --cluster homewallet --services api worker --query 'services[*].{name:serviceName,running:runningCount,desired:desiredCount,pending:pendingCount,task:taskDefinition}'
```

Preflight kiểm API/worker/jobs, public registration và email verification Cognito,
HTTPS/WAF, MFA, topology, budget, lịch và bằng chứng cùng release/image. Ngày
14/11/2026 kết quả là 99/99 GO. Chủ dự án xác nhận trực tiếp signup, email
verification, login, tạo hộ và tham gia hộ; acceptance ghi riêng các kiểm thử
tài khoản tổng hợp và các giới hạn.

## 4. Thay đổi và release tiếp theo

1. Review/merge source vào main; chạy **Build release candidate**. Muốn giữ OCR
   bật thì chọn **enable_ocr=true**; mặc định của workflow vẫn false.
2. CI/scan/checksum phải đạt. Dùng cùng artifact và immutable image cho frontend,
   API, worker, jobs. Không build riêng frontend hoặc dùng image working-tree.
3. Dùng tfvars production đã lưu. Kết nối Secrets Manager đã khắc phục; các saved
   plan đã review/apply. Plan cuối của bản bàn giao không còn drift cần apply.

```powershell
$nextPlan = Join-Path $ops 'next-change.tfplan'
terraform '-chdir=infra/envs/dev' plan "-var-file=$productionVars" "-out=$nextPlan" -input=false -lock-timeout=60s -detailed-exitcode
$nextPlanExit = $LASTEXITCODE
if ($nextPlanExit -notin @(0, 2)) { throw 'Plan lỗi. Không apply.' }
# 0: No changes. 2: có thay đổi, phải review saved plan trước khi apply.
```

Giữ HA, HTTPS/discovery, WAF, app hardening, public onboarding và guard chống xóa. Không
dùng default dev, `-target`, import/state push để chữa drift. Năm state move
trước đây đã hoàn tất, không lặp lại. Task definition replacement khác với xóa
ECS service/DB; đọc đúng address và skip_destroy.

Terraform đăng ký revision; service/target lịch có ignore_changes nên còn bước
cập nhật release thực tế. API rolling 100/200%, worker stop-first 0/100%. Cập nhật
ba target Scheduler sang jobs mới, giữ expression/timezone/input/role/network/retry.
Tạm dừng lịch khi chuyển target, rồi bật theo quyết định đã được duyệt sau kiểm
scope. Trạng thái hiện hành là ENABLED, `notifications_release_accepted=true` ở
tfvars/operator settings; không lấy default false để ghi đè input đang dùng.
Chỉ publish bằng `publish-frontend-release.py` sau gate GO;
assets trước index, không sync --delete, chờ invalidation và nghiệm thu phiên bản.

## 5. OCR, dữ liệu và quota

Đăng ký công khai: hộ mới không cần allowlist. Household 1, ảnh/dữ liệu và
queue/DLQ cũ giữ nguyên, tách khỏi phạm vi công khai; không tự cấp quyền đọc chéo
hộ. Tài khoản/hộ tổng hợp trong nghiệm thu đã dọn; audit provider giữ để không
reset số lần đã gọi trong ngày.

Chỉ nhận ảnh mới ở `receipts/production/<household>/` qua
`production-ocr-queue` và `production-ocr-dlq`. Không receive/purge/replay queue
cũ trong một đợt deploy. SQS có giới hạn retention; giữ DLQ không phải lưu vô hạn.

Worker kiểm lại household boundary, membership/consent trước S3/provider. Model đang dùng
`gemini-3.5-flash-lite`; cap **10 attempts/ngày UTC**, cách nhau ít nhất 30 giây,
hai attempts/receipt kể cả retry, output tối đa 4096 token. Cap app không thay
quota/billing của Google project. Không xóa audit attempts để lấy quota mới.
Kết quả là draft; người dùng đối chiếu ảnh rồi mới xác nhận giao dịch.

`hw_runtime` cần **SELECT, INSERT trên homewallet.audit_logs**; SQL quota dùng
cột `at`. Grant đã áp dụng và kiểm trên bản phục hồi. Khi bootstrap môi trường
mới, dùng file bootstrap/image của candidate đã sửa; không dùng image migrate
cũ để suy ra grant mới đã có. Không đổi mật khẩu runtime hoặc thêm quyền DDL.

Chỉ worker nhận Gemini secret. Kiên xác nhận thu hồi khóa cũ ở Google HWAPI;
rotation sau dùng helper nhập ẩn trong [runbook khóa](../gemini-ocr-production-enablement.md).
API gợi ý ngân sách dùng rule; Textract fallback tắt. Ba lịch gửi đã ENABLED:
nhắc hạn 07:45 hằng ngày, ngân sách 20:00 hằng ngày, báo cáo tuần 08:00 thứ Hai.
Jobs lọc SQL `household_id > 1`, phục vụ cả hộ mới và loại household 1; chế độ
đóng có thể quay lại allowlist đã review. Thiếu/sai scope dừng trước DB/gửi. Kết quả từng kỳ cần
log/nhận riêng, không suy từ trạng thái ENABLED.
Onboarding công khai cần email được xác minh; tạo/tham gia hộ không tự cấp quyền admin. Quyền dữ liệu luôn theo membership.

## 6. Dừng, rollback và phục hồi

- Release công khai hiện hành đã thử rollback API **:38 → :37 → :38**; bản :37 tạm
  tắt public registration. Đã khôi phục :38, kiểm readiness, xác nhận lại đăng ký
  công khai và dọn tài nguyên thử. Nếu rollback toàn bộ sang jobs cũ không lọc household
  1, phải tắt lịch trước; không đưa household 1 vào phạm vi. Biên bản hiện hành ghi
  rõ trình tự và các bản release lịch sử.
- Đợt a5097aa trước đã thử **:35 → :29 → :35**, điểm chuẩn khi đó là **:34**. Fallback
  của đợt đó là API **:29**, worker **:6** (OCR paused), jobs **:6** (lịch
  tắt), frontend candidate `26a0645`. Bản ghi rollback/checkpoint ở thư mục ops.
  Không dùng :22/:25 có profile dev hoặc candidate OCR lỗi `727f929`.
- Khi dừng OCR: chặn upload mới ở API/UI và pause worker trước ReceiveMessage;
  queue riêng và ảnh được giữ. Thực hiện bằng profile/candidate đã review, không
  sửa JS trên S3 hay purge queue. Rollback đầy đủ phải ghép frontend/backend/
  worker tương thích, chờ stable rồi kiểm readiness, SRP/MFA và phiên bản.
- Frontend: dùng VersionId trong checkpoint để phục hồi entry point và kiểm
  hashed assets, sau đó invalidation. Không xóa assets cũ. Restore cùng candidate
  đã được thử ở đợt trước; không coi đó là nghiệm thu frontend khác release.
- DB: PITR/snapshot sang instance **mới**, private/encrypted/SG riêng. Kiểm TLS,
  schema, runtime/audit grants, giao dịch thử và ứng dụng trước quyết định đổi
  endpoint. Secret/password của clone xử lý riêng; không restore đè primary.
- Đợt a5097aa đạt PITR/snapshot khoảng **14,6/11,2 phút**, restore point trễ
  **254 giây**; clone/SG/role tạm đã dọn. Task replacement, Redis/RDS failover,
  TLS/Lua sau failover và rollback đạt. RDS metadata AZ không đổi. Không tuyên
  bố thử mất cả AZ, cutover DB endpoint hoặc SLA từ các thời gian này.
- Bản 5f2308c khởi động đúng image trên PITR/snapshot clone mới khoảng
  **900,07/901,57 giây**, rollback :36→:34→:36 đạt; clone/SG/role đã dọn. Đây là
  bằng chứng lịch sử, không thay cho diễn tập mới ở release công khai.

Snapshot có tag giữ đến 27/11, không tự xóa. Kiên review checkpoint mới và chính
sách dữ liệu trước quyết định dọn. RDS backup 14 ngày, Redis 7, log 30 và frontend
noncurrent version 30 ngày. Dữ liệu hộ ngoài phạm vi tiếp tục giữ có kiểm soát.

## 7. Chi phí, bằng chứng và Git

AWS Budget **100 USD/tháng** là ngưỡng cảnh báo toàn account, không phải số chi
thực tế được phân bổ cho HomeWallet và không tự ngắt tài nguyên. Gemini được theo
dõi riêng, ngoài AWS Budget. Chưa có kỳ Cost Explorer/hóa đơn phân bổ riêng cho
project được chốt. SNS subscription đã confirm; CloudWatch dashboard: `homewallet-dev-operations`.

[Biên bản phát hành công khai](../acceptance/production-public-16f87ea-20261114.md)
liên kết release, onboarding, preflight và giới hạn. OCR canary ảnh tổng hợp ở
release trước không chứng minh luồng OCR live cho tài khoản công khai mới; benchmark
#34 hoặc đo tải kéo dài cũng không được suy ra từ preflight.

Kiên tạo nhánh tài liệu, stage theo `deploy/scheduler-evidence-paths-20261114.txt`,
kiểm staged diff, commit/push và merge sau CI. Không stage
state/tfvars, artifact, key/token hoặc DOCX hướng dẫn các tuần. PR tài liệu này
ghi nhận hệ thống đã deploy; pull/merge tài liệu không yêu cầu deploy lại.
