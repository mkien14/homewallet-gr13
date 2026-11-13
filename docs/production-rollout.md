# Chuyển phiên bản production trên stack hiện có

Kiên thực hiện commit/push. Đã chốt cảnh báo 100 USD/tháng; phối hợp với người
sửa HA/restore trước mở production. Mỗi phase có saved plan riêng, không dùng `-target`. Không gửi
plan/state/token/secret vào báo cáo. Không có bước bật lịch hay xóa dữ liệu.

## 1. Source và candidate

Review nhánh `fix/production-integration`, commit/push/merge main theo quy trình
nhóm. Không dùng `git add .` khi còn công việc khác; bỏ DOCX hướng dẫn các tuần.
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
cùng SHA. Candidate tắt OCR. Chưa có AWS deployment ở bước này.
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

## 3. Tạo HTTPS origin, chưa đổi traffic

```powershell
$actualAccount = aws sts get-caller-identity --query Account --output text
if ($LASTEXITCODE -ne 0 -or $actualAccount -ne '179923444714') { throw 'Sai AWS account' }
terraform '-chdir=infra/envs/dev' init
if ($LASTEXITCODE -ne 0) { throw 'Init lỗi' }
$phaseInputs = Join-Path $env:TEMP 'homewallet-https-origin.tfvars.json'
.\backend\.venv\Scripts\python.exe .\scripts\prepare-https-origin-plan.py --output $phaseInputs
if ($LASTEXITCODE -ne 0) { throw 'Không chuẩn bị được input hoặc file đã có; kiểm tra trước khi dùng lại' }
terraform '-chdir=infra/envs/dev' plan "-var-file=$phaseInputs" '-out=https-origin.tfplan'
if ($LASTEXITCODE -ne 0) { throw 'Plan lỗi' }
```

Review: API Gateway/VPC Link/SG thêm mới, WAF rate rule COUNT, output mới. Không
thay RDS/VPC/Redis, không xóa pool/data. Có thể đăng ký revision task definition
API mới do Terraform vẫn quản lý revision cũ trong khi service đã lên `hw-api:22`.
Service không được đổi revision ở phase HTTPS; giữ revision cũ để rollback bằng
`skip_destroy=true`. Các cập nhật metadata skip_destroy không thay task đang chạy.
Drift khác cần xử lý cùng người phụ
trách trước apply; không áp dụng plan có thay đổi ngoài phạm vi chưa review.
Helper giữ nguyên URI image API/worker/jobs/migrate, bao gồm digest: default cũ trong source có thể
khác runtime và gây kế hoạch thay revision không liên quan. Helper không đọc
secret. Giữ các giá trị image/model đó trong tfvars ở phase tiếp theo.

```powershell
terraform '-chdir=infra/envs/dev' apply https-origin.tfplan
if ($LASTEXITCODE -ne 0) { throw 'Apply lỗi' }
```

Đợi VPC Link AVAILABLE. Direct gateway thiếu origin header phải bị từ chối.
Canary có Authorization và origin header chỉ dùng trong bộ nhớ, không in giá
trị, không gửi qua HTTP/query string. Kiểm tra GET/PATCH/POST/DELETE, presign,
CSV, 413/429. HTTP API integration tối đa 30 giây: đo các endpoint chậm trước
chuyển. Đây là HTTPS trên các hop public, HTTP trên VPC Link/ALB/task nội bộ.

## 4. Chuyển CloudFront, sau đó đóng ingress cũ

Trong tfvars cục bộ đã review, giữ enable_api_https_gateway=true và thêm
route_api_via_https_gateway=true. Plan/apply saved plan mới. Chờ CloudFront
Deployed và nghiệm thu API, đăng nhập, hình/PDF, request ID/cache.

Sau canary, thêm close_legacy_http_origin=true, plan/apply riêng để đóng rule
CloudFront → public ALB:80 cũ. Không đóng cùng lúc đổi origin vì edge cần thời
gian lan truyền; VPC Link vẫn dùng SG riêng vào ALB:80.

Quan sát WAF COUNT với login/upload/cộng đồng hợp lệ rồi mới bật
waf_enforce_common_rules=true và waf_enforce_api_rate=true. Rate theo IP có thể
ảnh hưởng nhiều user chung NAT; Redis quota bổ sung giới hạn theo user.

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
job_schedules_enabled         = false
production_budget_enabled     = true
production_monthly_budget_usd  = 100
production_budget_emails       = ["<existing-reviewed-operations-mailbox>"]
production_allowed_household_ids = [<fixed-current-IDs-excluding-1>]
```

Review plan rồi apply. Không xóa User Pool/user/household nhưng sẽ **bỏ client
CLI dev và callback localhost**; script lấy token bằng password flow dev không
còn dùng được. Profile bỏ nạp Gemini key cho API/worker, AI/OCR tắt, worker pause;
origin header chuyển vào secret riêng; giữ tagged image trong ECR. Không thêm
migration: consent dùng bảng audit_logs hiện có.
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
revision mới sau apply. Worker/job/Scheduler target do Terraform cập nhật, lịch
vẫn DISABLED:

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
true khi có bằng chứng. resilience_signoff thuộc người phụ trách hạ tầng; không
đổi true để vượt gate. Không đặt token/key/email người dùng vào settings.

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

## 8. Khóa Gemini và thông báo: release tiếp theo

Thu hồi key cũ trong Google project **HWAPI**; AWS không làm thay bước thu hồi
Google key. Không gửi key mới trong chat. Helper ghi vào secret đã có, input ẩn:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\put-gemini-secret-version.py --secret-id '<explicit-reviewed-secret-name>' --expected-account 179923444714
```

Helper không thu hồi key Google hay tự restart consumer. Profile vẫn tắt và bỏ
nạp Gemini key. Mở AI/OCR sau benchmark #34, quota/cost, consent và failure
acceptance. Bật Scheduler sau opt-out, bounce/complaint, review người nhận,
chống gửi trùng, delivery và stop procedure. Không gắn hai bước đó vào release
core hiện tại.
