# Chuyển phiên bản production trên stack hiện có

Kiên thực hiện commit/push. Đã chốt cảnh báo 100 USD/tháng; HA/restore đã nghiệm thu trên stack hiện tại; xem biên bản ngày 13/11/2026. Thay đổi Terraform cần saved plan riêng, không dùng `-target`. Không gửi
plan/state/token/secret vào báo cáo. Không có bước bật lịch hay xóa dữ liệu.

**Điểm chuẩn ngày 14/11/2026:** main `a5097aa3fd941c53a9cc9a3961f205d9e55d1553`,
API `hw-api:34`, worker `hw-worker:10`, jobs `hw-jobs:9`, frontend cùng candidate;
gate cuối **93/93 GO**. Xem [biên bản](acceptance/production-release-a5097aa-20261114.md).
Kết nối Secrets Manager đã khắc phục; saved plan đã review/apply, plan cuối
**No changes**. Không import hoặc push state. Biên bản timeout/state cũ ngày
13/11 được giữ làm lịch sử, không còn mô tả điểm chuẩn hiện tại.

OCR đã nghiệm thu và bật với Gemini `gemini-3.5-flash-lite` tại worker, consent/
membership/allowlist và queue riêng; cap 10 attempts/ngày UTC. Chỉ thử ảnh tổng
hợp. API Gemini gợi ý ngân sách, Textract fallback và Scheduler vẫn tắt.
Xem [phạm vi và vận hành OCR](gemini-ocr-production-enablement.md).

## 1. Source và candidate

Các thay đổi hạ tầng/dependency/OCR đã merge main; candidate `a5097aa` đã phát hành.
Biên bản mới ở `release/production-a5097aa`. Với lần phát hành sau, review và
merge source mới theo quy trình nhóm. Không dùng `git add .` khi còn công việc
khác; bỏ DOCX hướng dẫn các tuần.
Không chạy workflow Deploy Dev sau chuyển production vì nó dùng tag dev.

Đây là runbook cho stack hiện có. Workflow **Reviewed production release** trong
PR #103 và `infra/envs/prod` phục vụ stack riêng, không áp dụng cho cluster
`homewallet`/CloudFront hiện tại. Không đổi tên tài nguyên để vượt guard.
Container local đã xử lý bằng Python 3.12/Alpine 3.24 và dependency khóa hash:
0 HIGH/CRITICAL, 0 secret finding. Xem
[bằng chứng](acceptance/container-security-20261113.md). Candidate từ commit main
vẫn phải build/quét lại; không lấy image working-tree làm release. Thay libc
sang musl cần nghiệm thu chức năng API/worker/jobs, bên cạnh build/scan.

Điền GitHub Repository Variables **công khai**:

| Variable | Giá trị |
| --- | --- |
| PRODUCTION_COGNITO_DOMAIN | Output cognito_hosted_ui, bỏ https:// |
| PRODUCTION_COGNITO_CLIENT_ID | Output cognito_spa_client_id |
| PRODUCTION_COGNITO_USER_POOL_ID | Output cognito_user_pool_id |
| PRODUCTION_VAPID_PUBLIC_KEY | Public key hiện có, không phải private key |
| PRODUCTION_SUPPORT_EMAIL | Hộp thư nhóm đọc được, đề xuất homewallet26@gmail.com |

Actions → **Build release candidate** → Run workflow từ main. Khắc phục nếu audit
lỗi; không ignore hàng loạt. Tải artifact `homewallet-release-<SHA>` từ chính
workflow của nhóm, giải nén vào thư mục tạm ngoài repo. Backend/frontend phải
cùng SHA. Muốn giữ OCR bật, chọn input **enable_ocr=true**; mặc định vẫn false.
Manifest và profile API/worker phải khớp lựa chọn đó. Chưa deploy AWS ở bước build.
Runtime chỉ dùng MySQL, không còn SQLite/binding Python sqlite3; verifier chặn
SBOM có SQLite vì bản trong base từng còn nằm trong khoảng CVE dù feed không báo.
Dependency mới cần SQLite phải được review lại, không bỏ guard để build qua.
Artifact có `security/container-scan.json` và `security/sbom.cdx.json`; verifier
đối chiếu image config từ tar và chỉ chấp nhận scan trong 72 giờ. Quá hạn chạy
lại candidate; không sửa timestamp/manifest hay bỏ gate. Khi cập nhật dependency,
regenerate `backend/requirements.lock` với hash và review thay đổi; Docker sẽ
không tự lấy phiên bản mới ngoài lock. Dependabot vẫn theo dõi base image/pip.

## 2. Admin tự đăng ký TOTP

Đăng nhập React → Menu → Bảo mật tài khoản → bật ứng dụng xác thực; thêm khóa vào
authenticator, nhập mã 6 số. Giữ kín khóa. Đăng xuất/đăng nhập lại, phải được hỏi
mã. Không bật MFA bắt buộc cho cả pool trước khi người dùng sẵn sàng.
Chỉ đặt `admin_mfa_challenge_verified=true` trong settings khi tất cả admin đang
bật đã xác nhận được challenge sau đăng nhập lại; enrollment metadata chưa đủ.

Nếu website chưa có màn này, có thể dùng source mới ở local:

```powershell
$env:VITE_API_TARGET = 'https://daoedidcrnf1f.cloudfront.net'
npm --prefix .\frontend run dev
```

Dùng cấu hình SPA/pool hiện có trong .env.local. Mở localhost:5173/auth/react,
đăng nhập rồi vào /security. Vite proxy API qua CloudFront; Cognito nhận SRP
trực tiếp. Dừng server và Remove-Item Env:VITE_API_TARGET khi không còn dùng.

## 3. HTTPS và HA trên stack hiện tại

**Stack đã chuyển production ngày 13/11/2026.** Không dùng lại bootstrap helper
HTTPS/default dev. Dùng tfvars vận hành đã review trong
[bàn giao](runbooks/current-stack-production.md). Mỗi phase dùng saved plan
riêng; không dùng `-target` hoặc tạo lại ECS service để đổi state address.

Luồng đang chạy: CloudFront → HTTP API HTTPS → VPC Link → Cloud Map SRV → API.
Canary đầu với ALB trả 503; network probe xác nhận ALB vẫn truy cập được trong
VPC. Không kết luận nguyên nhân 503 chỉ từ scheme ALB. Cloud Map được tạo,
ECS đăng ký SRV/health, app nhận origin secret trước khi chuyển traffic.
Canary mới đạt 403/401/200 và CRUD có token trên HTTPS.

Các flag phải giữ trong input của stack này:

```hcl
enable_api_https_gateway                = true
enable_api_service_discovery            = true
application_origin_verification_enabled = true
resilience_hardening_enabled            = true
resilience_apply_immediately            = false
api_desired_count                       = 2
```

Lần chuyển HA đầu đã backup state và thực hiện **năm state move**, giữ AWS ID:
`module.compute.aws_ecs_service.api[0]` sang `api_scaled[0]`, `worker[0]` sang
`worker_release[0]`, ba schedule `jobs["key"]` sang `jobs_release["key"]`.
Key: `budget_alerts`, `recurring_reminders`, `weekly_report`.
**Không lặp lại move trên state đã chuyển.** Không apply plan xóa/tạo lại ECS
service, RDS hay bucket. Service/schedule production có `prevent_destroy` để
chặn apply nhầm default dev; tháo bỏ có kiểm soát cần review guard riêng.

HA bật Multi-AZ/backup RDS, replica/failover Redis, NAT mỗi AZ, API min 2/max 4,
readiness/circuit breaker và log 30 ngày. `resilience_apply_immediately=true`
chỉ dùng trong đợt thay đổi đã review; trạng thái cuối đặt false.
Budget 100 USD không dừng tài nguyên khi vượt mức.

## 4. CloudFront, WAF và đóng ingress cũ

```hcl
route_api_via_https_gateway = true
close_legacy_http_origin   = true
waf_enforce_common_rules   = true
waf_enforce_api_rate       = true
```

Đã tách canary, chuyển edge và đóng ingress CloudFront → ALB:80 thành các phase.
Luồng public dùng HTTPS, hop VPC Link → task là HTTP nội bộ. ALB còn để health
check/đường dự phòng có kiểm soát, không còn rule CloudFront prefix list.
Direct HTTP API không có origin secret phải bị từ chối. Không gửi origin secret
hay bearer token qua query string/HTTP, không log chúng hoặc đưa vào Git.

Cảnh báo public API dùng HTTP API `5xx` và `IntegrationLatency`, dimension
`ApiId`; alarm ALB cũ không đại diện lưu lượng Cloud Map. SNS có email đã
confirm. Rate theo IP có thể dùng chung cho nhiều người sau NAT; Redis bổ sung
giới hạn theo user. Kiểm tra canary sau mỗi thay đổi WAF.

## 5. Kiểm tra candidate và đưa image vào ECR

Docker Engine phải chạy. Không đưa artifact/backend.tar vào Git. Checksum chỉ
chứng minh toàn vẹn; vẫn phải lấy artifact từ workflow main đã review của nhóm.

```powershell
$releaseSha = '<40-character-SHA-of-reviewed-main-commit>'
$artifactDirectory = '<absolute-path-to-extracted-artifact>'
.\backend\.venv\Scripts\python.exe .\scripts\publish-frontend-release.py --artifact-dir $artifactDirectory --release $releaseSha --verify-only
if ($LASTEXITCODE -ne 0) { throw 'Artifact không hợp lệ' }
$repoUri = terraform '-chdir=infra/envs/dev' output -raw ecr_url
if ($LASTEXITCODE -ne 0) { throw 'Không lấy được ECR URL' }
$registry = ($repoUri -split '/')[0]
aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin $registry
if ($LASTEXITCODE -ne 0) { throw 'ECR login lỗi' }
docker load -i (Join-Path $artifactDirectory 'backend.tar')
if ($LASTEXITCODE -ne 0) { throw 'Docker load lỗi' }
docker tag "homewallet-release:$releaseSha" "${repoUri}:sha-$releaseSha"
if ($LASTEXITCODE -ne 0) { throw 'Docker tag lỗi' }
docker push "${repoUri}:sha-$releaseSha"
if ($LASTEXITCODE -ne 0) { throw 'Docker push lỗi' }
$repositoryName = ($repoUri -split '/', 2)[1]
$imageDigest = aws ecr describe-images --region ap-southeast-1 --repository-name $repositoryName --image-ids "imageTag=sha-$releaseSha" --query 'imageDetails[0].imageDigest' --output text
if ($LASTEXITCODE -ne 0 -or $imageDigest -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Digest sai' }
```

## 6. Profile ứng dụng và API task

Giữ flag HTTPS/WAF, thêm vào tfvars cục bộ:

```hcl
application_hardening_enabled = true
release_commit                = "<same Git SHA>"
release_image_digest          = "sha256:<digest from ECR>"
waf_enforce_common_rules      = true
waf_enforce_api_rate          = true
job_schedules_enabled         = true
notifications_release_accepted = true
production_budget_enabled     = true
production_monthly_budget_usd  = 100
production_budget_emails       = ["<existing-reviewed-operations-mailbox>"]
production_allowed_household_ids = [<fixed-current-IDs-excluding-1>]
```

Review plan rồi apply. Không xóa User Pool/user/household nhưng sẽ **bỏ client
CLI dev và callback localhost**; script lấy token bằng password flow dev không
còn dùng được. API không nhận Gemini key; worker chỉ nhận key khi OCR và rotation
được bật có bằng chứng. Input hiện tại giữ `production_ocr_enabled=true`,
`gemini_rotation_confirmed=true`, model `gemini-3.5-flash-lite`. Origin header
ở secret riêng; giữ tagged image trong ECR. Consent/quota dùng bảng audit_logs
hiện có, cột thời gian `at`; runtime cần SELECT và INSERT trên bảng này.
API/worker/jobs trong profile này đều chạy UID/GID 10001:10001, drop ALL Linux
capabilities và có init process. Task revision cũ không tự nhận cấu hình này.
Chốt allowlist bằng snapshot chỉ đọc ID các hộ hiện có khác 1 theo quyết định
Kiên, không đưa token/email/tên thành viên vào biên bản. Household 1 và danh tính
chưa thuộc hộ được duyệt nhận 403 trước bước tạo user; không có bypass cho admin.
Cognito và frontend tắt tự đăng ký mới; onboarding cần quy trình admin riêng.
Budget 100 USD là cảnh báo tổng account, không phải hard cap; giữ hai budget cũ.
Không copy giá trị placeholder trên vào apply. Email nhận cảnh báo lấy từ danh
sách vận hành đã được duyệt, lưu ở tfvars local ngoài Git.

ECR chuyển sang immutable tags khi bật profile. Deploy Dev kiểm tra cả task đang
chạy và revision chuẩn bị mới nhất, từ chối profile production trước push/deploy;
không dùng workflow đó để ghi lại tag dev sau khi chuyển.

API service có ignore_changes task_definition từ thiết kế cũ; chuyển sang
revision mới sau apply. Khi bật HA, worker service và Scheduler target cũng
ignore task revision. Phải cập nhật worker và cả ba target theo saved outputs;
giữ lịch DISABLED trong lúc chuyển target, kiểm bộ lọc hộ rồi bật lại theo input
đã được duyệt. Bản 5f2308c hiện có ba lịch ENABLED; xem
[biên bản bật lịch](acceptance/production-schedules-5f2308c-20261114.md). Hai cờ
trên phải đồng bộ với operator settings. Không bật lịch trên jobs :9 hoặc bản
cũ chưa có bộ lọc SQL:

Health check ALB dùng `/health` hoặc `/ready` trực tiếp nên chỉ hai đường nội bộ
này được miễn origin header. Các đường `/api/health`, `/api/ready`, `/api/release`
vẫn cần origin header do CloudFront thêm. Readiness của Chi được giữ khi ghép.

```powershell
$apiTaskArn = terraform '-chdir=infra/envs/dev' output -raw api_task_definition_arn
if ($LASTEXITCODE -ne 0) { throw 'Không lấy được API task' }
aws ecs update-service --region ap-southeast-1 --cluster homewallet --service api --task-definition $apiTaskArn --query 'service.serviceName' --output text
if ($LASTEXITCODE -ne 0) { throw 'API deploy lỗi' }
aws ecs wait services-stable --region ap-southeast-1 --cluster homewallet --services api
if ($LASTEXITCODE -ne 0) { throw 'API chưa stable; dùng quy trình rollback được bàn giao' }
```

## 7. Gate và frontend

Copy deploy/production.example.json ra ngoài repo, điền cluster/service/bucket,
admin group, ba schedule name/group, budget/subscriber thật. Attestation chỉ
true khi có bằng chứng. resilience_signoff chỉ được true sau nghiệm thu có bằng chứng. Gate còn kiểm
tra topology AWS và bằng chứng cùng account/Region/DB/release/image không quá
30 ngày; không đổi true hoặc sửa ngày để vượt gate. Không đặt token/key/email người dùng vào settings.

```powershell
$settingsFile = '<absolute-path-to-reviewed-settings.json>'
.\backend\.venv\Scripts\python.exe .\scripts\production-preflight.py --settings $settingsFile
if ($LASTEXITCODE -ne 0) { throw 'NO_GO: xử lý gate trước publish' }
.\backend\.venv\Scripts\python.exe .\scripts\publish-frontend-release.py --settings $settingsFile --artifact-dir $artifactDirectory --release $releaseSha
if ($LASTEXITCODE -ne 0) { throw 'Chưa đủ điều kiện publish' }
.\backend\.venv\Scripts\python.exe .\scripts\publish-frontend-release.py --settings $settingsFile --artifact-dir $artifactDirectory --release $releaseSha --apply
if ($LASTEXITCODE -ne 0) { throw 'Publish chưa hoàn tất' }
```

Script kiểm checksum, metadata gate, /api/release cùng SHA; upload asset trước
index, không xóa asset cũ, đặt cache header và yêu cầu invalidation. Chờ
invalidation hoàn tất, đối chiếu /release.json và /api/release, nghiệm thu UI.
Gate kiểm tra API/worker/jobs cùng image/SHA, private network, ECR immutable,
cấu hình container và target jobs của ba lịch đang DISABLED. Publisher đọc
manifest image ở ECR để đối chiếu config digest với image trong artifact đã quét;
chỉ trùng APP_RELEASE chưa đủ. Image phát hành là single-platform Linux amd64.
Nếu upload lỗi giữa chừng, không kết luận release thành công. Dùng rollback của
người được giao, không build frontend khác commit để chữa tạm.

Cần bằng chứng release thật về auth/tenant isolation, hộ, CRUD chi tiêu/ngân
sách, cộng đồng, xóa/xuất và xử lý lỗi mạng/quota. Build/validate không thay thế
regression, security scan, tải thực tế hoặc bàn giao resilience.

## 8. Rotation Gemini và thông báo

Kiên đã xác nhận thu hồi key cũ trong Google project **HWAPI**, key mới đã được
worker dùng trong E2E đạt. AWS không làm thay thao tác thu hồi Google key.
Với lần rotation sau, dùng helper nhập ẩn, không gửi key qua chat:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\put-gemini-secret-version.py --secret-id '<explicit-reviewed-secret-name>' --expected-account 179923444714
```

Helper không thu hồi key Google hay tự restart consumer. Candidate hiện tại đã
đạt canary ảnh/quota/consent/rollback; không dùng một ảnh để tự chốt benchmark
rộng #34. Chỉ worker được nạp key; không mở thêm Gemini ngân sách như tác dụng
phụ. Ba lịch vẫn DISABLED. Bật lịch là change riêng sau kiểm người nhận,
opt-out, bounce/complaint, chống trùng, delivery và stop procedure.

## 9. Sau khi đã triển khai

Dùng cấu hình vận hành bền vững ngoài Git theo
[bàn giao](runbooks/current-stack-production.md). Dùng lại bootstrap tfvars từ
TEMP/default dev có thể đề xuất hạ cấu hình hoặc xóa tài nguyên; giữ guard
production. Không dùng `git clean -fdx` để dọn cấu hình vận hành.

Frontend có S3 versioning; entry point cùng candidate đã thử copy từ version
và đối chiếu hash. Giữ hashed asset cũ, không sync `--delete`. Rollback về app
khác release vẫn cần kiểm tra tương thích API, guard và migration.
