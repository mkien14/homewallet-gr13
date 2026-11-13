# Bàn giao production — stack hiện tại

Cập nhật **14/11/2026**. Chủ vận hành/dữ liệu: **Kiên**.
Biên bản ở nhánh `release/production-a5097aa`; Kiên commit/push/merge.

## 1. Điểm chuẩn

| Thành phần | Giá trị |
| --- | --- |
| Website | https://daoedidcrnf1f.cloudfront.net |
| Main / candidate | `a5097aa3fd941c53a9cc9a3961f205d9e55d1553` / [43471247102](https://github.com/mkien14/homewallet-gr13/actions/runs/43471247102) |
| API / worker / jobs | `hw-api:34` / `hw-worker:10` / `hw-jobs:9` |
| ECR image | `homewallet-backend@sha256:4e6af786b86b595f9526010848e52d023bc027030260910edfcd91f02d41ca4a` |
| Account / Region | `179923444714` / `ap-southeast-1` |
| CloudFront / HTTP API | `E1FBDSJYV9WAKM` / `4o95mvff40` |
| RDS / Redis | `homewallet-dev-mysql` / `homewallet-dev-redis` |
| Frontend bucket | `hw-frontend-dev-179923444714`, private/OAC/versioned |
| State | Bucket `hw-tfstate-homewallet-gr13`, key `dev/terraform.tfstate`, encrypted/private/versioned, S3 lockfile |
| Restore checkpoint | `hw-prod-before-core-20261113-df1fc11e`, review giữ/dọn ngày 27/11/2026 |
| Gate / Terraform | 93/93 GO; plan cuối No changes |

Tên/tag `dev` là tên cũ của stack production hiện tại. Không rename tài nguyên,
không chạy Deploy Dev hoặc apply `infra/envs/prod` vào đây. Phát triển dùng local/mock.

## 2. Cấu hình vận hành ngoài Git

```powershell
$ops = Join-Path $env:LOCALAPPDATA 'HomeWallet\production\20261113'
$productionVars = Join-Path $ops 'production.tfvars.json'
$productionSettings = Join-Path $ops 'operator-settings.json'
```

Thư mục giới hạn ACL cho operator, SYSTEM và Administrators. Bản ghi mới nằm
trong `ocr-final`; root tfvars/settings, active release, checkpoint frontend và
rollback đã cập nhật. Bản cũ giữ để truy vết. Không upload thư mục này: state
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

Preflight kiểm image/profile, allowlist, HTTPS/WAF, MFA, topology, budget, lịch
và bằng chứng cùng release/image không quá 30 ngày. Admin mới phải tự đăng ký
TOTP và thử đăng nhập lại. Kiên đã xác nhận challenge; bản mới thử SRP/TOTP thực
tế trên Edge bằng danh tính tổng hợp, sau đó xóa danh tính đó.

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

Giữ HA, HTTPS/discovery, WAF, app hardening, allowlist và guard chống xóa. Không
dùng default dev, `-target`, import/state push để chữa drift. Năm state move
trước đây đã hoàn tất, không lặp lại. Task definition replacement khác với xóa
ECS service/DB; đọc đúng address và skip_destroy.

Terraform đăng ký revision; service/target lịch có ignore_changes nên còn bước
cập nhật release thực tế. API rolling 100/200%, worker stop-first 0/100%. Cập nhật
ba target Scheduler sang jobs mới, giữ DISABLED và giữ expression/timezone/input/
role/network/retry. Chỉ publish bằng `publish-frontend-release.py` sau gate GO;
assets trước index, không sync --delete, chờ invalidation và nghiệm thu phiên bản.

## 5. OCR, dữ liệu và quota

Allowlist: `2,3,4,5,6,7,8,9,11,12,13,22,23,24,25,26`. Hộ 1, ảnh/dữ liệu và
queue/DLQ cũ giữ nguyên. Hộ 29 và danh tính/ảnh/user DB thử đã dọn; không tự thêm
hộ tương lai. Audit provider thử giữ để không reset số lần đã gọi trong ngày.

Chỉ nhận ảnh mới ở `receipts/production/<household>/` qua
`production-ocr-queue` và `production-ocr-dlq`. Không receive/purge/replay queue
cũ trong một đợt deploy. SQS có giới hạn retention; giữ DLQ không phải lưu vô hạn.

Worker kiểm lại membership/allowlist/consent trước S3/provider. Model đang dùng
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
API gợi ý ngân sách dùng rule; Textract fallback và ba lịch gửi tự động giữ tắt.
Onboarding là thao tác admin có kiểm soát, không mở signup để lách allowlist.

## 6. Dừng, rollback và phục hồi

- Rollback API **:35 → :29 → :35** đã đạt, điểm chuẩn cuối là **:34**. Fallback
  production trước là API **:29**, worker **:6** (OCR paused), jobs **:6** (lịch
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
- Candidate này đạt PITR/snapshot khoảng **14,6/11,2 phút**, restore point trễ
  **254 giây**; clone/SG/role tạm đã dọn. Task replacement, Redis/RDS failover,
  TLS/Lua sau failover và rollback đạt. RDS metadata AZ không đổi. Không tuyên
  bố thử mất cả AZ, cutover DB endpoint hoặc SLA từ các thời gian này.

Snapshot có tag giữ đến 27/11, không tự xóa. Kiên review checkpoint mới và chính
sách dữ liệu trước quyết định dọn. RDS backup 14 ngày, Redis 7, log 30 và frontend
noncurrent version 30 ngày. Dữ liệu hộ ngoài phạm vi tiếp tục giữ có kiểm soát.

## 7. Chi phí, bằng chứng và Git

Budget **100 USD/tháng** cảnh báo toàn account, không tự ngắt tài nguyên; cấu
hình HA có chi phí liên tục. SNS subscription đã confirm; chưa kiểm inbox alarm
trong đợt này. CloudWatch dashboard: `homewallet-dev-operations`.

[Biên bản bàn giao](../acceptance/production-release-a5097aa-20261114.md) liên kết
JSON release/OCR/resilience. Một ảnh tổng hợp là canary release, không thay bộ
benchmark rộng #34 hoặc đo tải kéo dài.

Kiên stage theo `deploy/release-evidence-paths-a5097aa.txt`, kiểm staged diff,
commit/push nhánh `release/production-a5097aa` và merge sau CI. Không stage
state/tfvars, artifact, key/token hoặc DOCX hướng dẫn các tuần. PR tài liệu này
ghi nhận hệ thống đã deploy; pull/merge tài liệu không yêu cầu deploy lại.
