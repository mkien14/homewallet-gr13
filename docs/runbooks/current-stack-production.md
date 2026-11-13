# Bàn giao production core — stack hiện tại

Ngày: 13/11/2026. Chủ vận hành và quyết định dữ liệu: **Kiên**.
Hạ tầng/dependency đã merge main. Biên bản phát hành mới ở nhánh
`release/production-26a0645`. Agent chưa stage, commit hoặc push thay người dùng.

## 1. Điểm chuẩn đang chạy

| Thành phần | Điểm chuẩn |
| --- | --- |
| App release | `26a0645709af3acb123768bb21a6a788d4252373`, candidate [43408857810](https://github.com/mkien14/homewallet-gr13/actions/runs/43408857810) |
| API | `hw-api:29`, hai task ở hai AZ |
| Worker / jobs | `hw-worker:6` / `hw-jobs:6`; OCR tắt, ba lịch DISABLED |
| Image | `homewallet-backend@sha256:dfef1a60b3fee7e1733563a3aa040ebfc1cb0d92021b154b16f00eb788d74348` trong ECR account 179923444714/Singapore |
| URL / CloudFront | https://daoedidcrnf1f.cloudfront.net / `E1FBDSJYV9WAKM` |
| HTTPS API / discovery | `4o95mvff40`, VPC Link, Cloud Map SRV `api.homewallet-api.internal` |
| Database | `homewallet-dev-mysql`, MySQL 8.4, db.t4g.micro, Multi-AZ, TLS/private/encrypted |
| Redis | `homewallet-dev-redis`, hai node/TLS/AUTH/failover; snapshot 7 ngày |
| State | S3 `hw-tfstate-homewallet-gr13`, key `dev/terraform.tfstate`; encrypted/private/versioned, S3 lockfile |
| Frontend bucket | `hw-frontend-dev-179923444714`, private/OAC/versioning; noncurrent version 30 ngày |
| Restore checkpoint | `hw-prod-before-core-20261113-d8aca388`; giữ đến 27/11/2026 theo tag quản lý; checkpoint cũ `…ad8e7e2a` vẫn giữ |

Tag giữ snapshot không tự xóa khi đến hạn. Ngày 27/11, Kiên review snapshot mới,
restore point và thời hạn giữ dữ liệu trước khi quyết định dọn bản cũ.
Tên/tag `dev` không còn biểu thị môi trường phát triển độc lập. Không rename
resource/state hay apply `infra/envs/prod` vào stack này.

## 2. File vận hành ngoài Git

Trên máy đã triển khai:

```powershell
$ops = Join-Path $env:LOCALAPPDATA 'HomeWallet\production\20261113'
$productionVars = Join-Path $ops 'production.tfvars.json'
$productionSettings = Join-Path $ops 'operator-settings.json'
```

Thư mục được giới hạn ACL cho operator hiện tại, SYSTEM và Administrators.
Có tfvars cuối, settings preflight, backup state, bản ghi state move, checkpoint
frontend và revision rollback. Không upload thư mục này lên GitHub hoặc gửi qua
chat: state có thể chứa secret; tfvars có email nhận budget.
Hồ sơ release mới nằm trong `releases\26a0645`; `production.tfvars.json`,
`operator-settings.json`, active release và checkpoint frontend ở thư mục trên
đã cập nhật theo điểm chuẩn cuối. Credential/TOTP seed của fixture thử đã bỏ.
Không trông cậy vào các bản TEMP cũ. Nếu đổi máy, bàn giao qua kênh bảo mật và
kiểm tra account/Region/quyền, không copy access key vào repo.

## 3. Kiểm tra chỉ đọc

Chạy từ thư mục repo, bằng AWS profile đã được cấp quyền hợp lệ:

```powershell
$actualAccount = aws sts get-caller-identity --query Account --output text
if ($LASTEXITCODE -ne 0 -or $actualAccount -ne '179923444714') { throw 'Sai account' }
.\backend\.venv\Scripts\python.exe .\scripts\production-preflight.py --settings $productionSettings
if ($LASTEXITCODE -ne 0) { throw 'NO_GO: xem gate lỗi, không sửa attestation để vượt gate' }
aws ecs describe-services --region ap-southeast-1 --cluster homewallet --services api worker --query 'services[*].{name:serviceName,running:runningCount,desired:desiredCount,pending:pendingCount,task:taskDefinition}'
```

Preflight kiểm tra topology, image/profile, allowlist, WAF/HTTPS, MFA, bucket,
retention, alarm/SNS, budget, lịch và bằng chứng restore/rollback đúng release.
Bằng chứng quá 30 ngày hoặc khác image/release phải được chạy lại phù hợp.
MFA của Kiên đã có attestation challenge; admin mới phải tự bật TOTP và thử lại.
Metadata thiết bị MFA AWS không thay cho kiểm tra chính sách IAM của từng người.

## 4. Thay đổi Terraform tiếp theo

```powershell
$nextPlan = Join-Path $ops 'next-change.tfplan'
terraform '-chdir=infra/envs/dev' plan "-var-file=$productionVars" "-out=$nextPlan"
if ($LASTEXITCODE -ne 0) { throw 'Plan lỗi' }
# Review saved plan, các ARN/revision và chi phí trước bước apply.
terraform '-chdir=infra/envs/dev' apply $nextPlan
if ($LASTEXITCODE -ne 0) { throw 'Apply lỗi; xem log và trạng thái thật trước khi chạy tiếp' }
```

Không apply default dev, không dùng `-target`, không tái tạo service/bucket/DB.
Giữ `resilience_hardening_enabled`, discovery, HTTPS, WAF và app hardening bật;
`resilience_apply_immediately=false`, lịch tắt. Guard `prevent_destroy` trên
service/schedule production cố ý chặn cấu hình dev gây xóa tài nguyên.
Năm state move đã hoàn tất; không lặp lại. State backup ở ngoài Git và S3 có
version history; phục hồi state cần review riêng, không ghi đè state để chữa drift.

## 5. Phát hành ứng dụng tiếp theo

1. Kiên review/merge source, chạy **Build release candidate** từ đúng main.
2. Audit, lock, security scan và checksum phải đạt; không build lại riêng frontend.
3. ECR dùng immutable digest. Cập nhật release/digest trong tfvars đã review và
   settings; giữ allowlist. Không nạp Gemini key hoặc bật lịch như tác dụng phụ.
4. Saved plan/apply đăng ký revision; API/worker/Scheduler target có ignore_changes
   nên còn bước cập nhật release. API min 100%/max 200%; worker stop-first 0/100%.
5. Triển khai API, smoke, rồi worker. Cập nhật cả ba Scheduler target sang jobs mới
   với **State=DISABLED**, giữ expression/timezone/input/role/network/retry.
6. Có bằng chứng cùng candidate, gate GO, dùng `publish-frontend-release.py`.
   Script upload assets trước index, không xóa assets cũ; chờ invalidation xong.
7. Đối chiếu `/release.json`, `/api/release`; đăng nhập/SRP/MFA, chức năng, lỗi,
   scope dữ liệu, mobile và rollback trước khi ghi điểm chuẩn mới.

Không dùng **Deploy Dev** hoặc workflow **Reviewed production release** dành cho
stack `homewallet-prod`. Merge source không tự đổi APP_RELEASE đang chạy.

### Phương thức thực tế của release 26a0645

Plan local bị timeout khi đọc metadata Secrets Manager Singapore; đã dừng tiến
trình và giải phóng đúng lock của plan. Không Terraform apply/import/state push.
Đăng ký revision qua ECS API bằng cấu hình baseline production đã đối chiếu:
container chỉ đổi image và `APP_RELEASE`, tag được giữ. Cập nhật API/worker và
target ba lịch, giữ lịch DISABLED; frontend dùng chính artifact đã quét.

Input tfvars/settings ngoài Git đã cập nhật nhưng state/output Terraform có thể
còn revision cũ. Trước apply tiếp theo cần khắc phục kết nối metadata, tạo saved
plan với input production và review chênh lệch đăng ký task definition. Không
tuyên bố “No changes”, không dùng output revision cũ để deploy lại. Dừng nếu plan
đề xuất hạ profile hoặc thay/xóa DB, network, service ngoài phạm vi đã duyệt.
Chi tiết trong [biên bản release](../acceptance/production-release-26a0645-20261113.md).

## 6. Rollback và khôi phục

- API rollback mới đã diễn tập `hw-api:30 → :28 → :30` giữa candidate `26a0645`
  và production cũ `1bba075`, giữ guard production. Sau cleanup chạy `:29` với
  allowlist cuối; revision thử `:30` đã deregister. `:28` là fallback production
  đã thử cho đợt này; không dùng :22/:25 có profile dev để rollback.
- Với release tương lai, lấy revision ổn định đã lưu, đối chiếu production profile,
  allowlist, image và tương thích schema. `aws ecs update-service` sang revision
  đó, chờ services-stable, kiểm tra hai AZ/readiness/release và token. Worker/jobs
  phải rollback theo bộ tương thích; lịch tiếp tục tắt.
- Migration 006 là additive; đợt này không chạy down migration hoặc ghi đè DB.
- RDS: ưu tiên PITR hoặc snapshot **sang instance mới**, private/encrypted/SG riêng.
  Kiểm tra TLS, schema/grants, dữ liệu, giao dịch thử và ứng dụng trước quyết định
  đổi endpoint. Không restore đè primary. Secret/master password của bản phục hồi
  cần được xử lý riêng. Dọn clone, SG, role, grants/schema thử sau nghiệm thu.
- [Bằng chứng restore/failover cùng candidate](../acceptance/production-resilience-26a0645-20261113.json):
  độ trễ restore point khoảng 66 giây, thời gian đến kiểm tra ứng dụng PITR/
  snapshot khoảng 14,3/10,3 phút. Startup probe dùng profile dev cô lập; profile
  production thử riêng trên ứng dụng đang chạy. Chưa chuyển endpoint người dùng
  sang DB phục hồi hoặc thử mất toàn bộ AZ. Thời gian quan sát gồm polling,
  không phải SLA. [Đợt chuyển stack đầu](../acceptance/production-resilience-20261113.json)
  được giữ làm lịch sử.
- Frontend: chọn VersionId đã lưu cho index/release/sw/manifest từ checkpoint
  ngoài Git, kiểm tra cùng release và hashed asset còn tồn tại, copy version đó
  về key tương ứng rồi invalidation. Đã thử phục hồi version cùng candidate;
  chưa nghiệm thu frontend khác release. Không xóa asset cũ hoặc dùng sync --delete.

## 7. Ranh giới dữ liệu, email và tính năng tắt

16 hộ được duyệt: `2,3,4,5,6,7,8,9,11,12,13,22,23,24,25,26`.
Hộ 1 và ảnh/dữ liệu giữ nguyên; không purge/redrive DLQ, không gửi thử cho họ.
SQS có thời hạn lưu tối đa của dịch vụ; giữ DLQ không phải lưu trữ vô thời hạn.
Nếu cần giữ payload lâu hơn phải có kế hoạch lưu trữ/retention riêng được review,
không tự ReceiveMessage để xem nội dung trong một đợt deploy.

Hộ thử 27 của đợt đầu và hộ 28 của release mới đã xóa qua API; các Cognito user
thử tương ứng đã xóa. ID 27/28 không nằm trong allowlist cuối. TOTP của phép thử
browser mới dùng danh tính tổng hợp đã xóa, không thay thiết bị MFA của Kiên.
Một số hàng user/history tổng hợp có thể được giữ làm audit; chúng không cấp
quyền đăng nhập hoặc là dữ liệu khách hàng.

Onboarding mới là thao tác admin có kiểm soát: tạo danh tính, chuẩn bị membership
cho hộ đã duyệt và cập nhật allowlist theo change được review. Profile hiện tại
cố ý chặn user chưa có membership trước bước tạo user; không mở signup để lách.

AI/OCR và ba lịch tiếp tục tắt. Trước bật lại phải xác nhận thu hồi khóa Google
cũ tại HWAPI, quota/benchmark, consent, lỗi/chi phí và phạm vi worker/job/recipient.
Không chỉ đổi biến enabled: cần chứng minh worker/job không xử lý hộ đang giữ,
opt-out, bounce/complaint, chống trùng, delivery và stop procedure.

## 8. Theo dõi vận hành và chi phí

- CloudWatch dashboard `homewallet-dev-operations`; HTTP API alarms 5xx/latency
  phủ luồng mới qua Cloud Map. Log không chứa token/origin secret/nội dung hóa đơn.
- SNS email đã confirm; chưa xác nhận inbox nhận alarm trong đợt này. Không giả
  kết quả delivery từ trạng thái subscription.
- Budget 100 USD/tháng là cảnh báo account-wide, không tự ngắt hay giới hạn tiền.
  Hai NAT, Multi-AZ, replica, endpoints, ALB, log và traffic đều có phí. Forecast
  có độ trễ, không dùng số hiện tại làm dự toán cấu hình HA trọn tháng.
- Snapshot trước chuyển đổi giữ đến 27/11 cần review thủ công; backup RDS 14 ngày,
  Redis 7 ngày, log 30 ngày và noncurrent frontend 30 ngày.
- Chưa có benchmark tải kéo dài/SLA. CPU scaling policy đã kiểm tra cấu hình,
  còn phép dừng task/failover là kiểm tra phục hồi riêng.

## 9. Commit/push do Kiên thực hiện

Review `git diff --stat`, `git diff --check`, file bằng chứng và nhánh
`release/production-26a0645`. Add rõ tám file tài liệu của đợt này; không dùng `git add .`
nếu còn việc khác. Kiểm tra staged file trước commit, không stage state/tfvars,
artifact image, file operator riêng hoặc DOCX hướng dẫn các tuần.

Sau commit/push mở PR, chờ CI đạt rồi merge theo quy trình nhóm. Ứng dụng đã triển
khai; PR này ghi nhận nghiệm thu và bàn giao, không chạy lại deploy/apply khi pull.

### Lệnh commit/push cho các thay đổi đã rà soát

Chạy trong thư mục repo hiện tại, trên nhánh `release/production-26a0645`.
Nếu có thay đổi ngoài phạm vi đợt này, kiểm tra trước khi tiếp tục; rà soát danh sách
file đã stage trước khi commit.

```powershell
if ((git branch --show-current) -ne 'release/production-26a0645') {
    throw 'Sai nhánh. Chưa stage hoặc commit.'
}
git status --short
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'Cần sửa lỗi diff trước khi commit.' }
git add -- `
  docs/acceptance/production-browser-26a0645-20261113.json `
  docs/acceptance/production-preflight-26a0645-20261113.json `
  docs/acceptance/production-release-26a0645-20261113.json `
  docs/acceptance/production-release-26a0645-20261113.md `
  docs/acceptance/production-resilience-26a0645-20261113.json `
  docs/production-readiness.md `
  docs/production-rollout.md `
  docs/runbooks/current-stack-production.md
if ($LASTEXITCODE -ne 0) { throw 'Stage chưa thành công. Chưa commit.' }
git diff --cached --name-only
git diff --cached --stat
git commit -m "docs: record production release 26a0645 acceptance"
if ($LASTEXITCODE -ne 0) { throw 'Commit chưa thành công. Chưa push.' }
git push -u origin release/production-26a0645
if ($LASTEXITCODE -ne 0) { throw 'Push chưa thành công. Kiểm tra thông báo Git.' }
```

Sau khi push, mở PR `release/production-26a0645` vào `main`, chờ CI đạt rồi
Squash and merge. Kiểm tra danh sách staged chỉ có tám tài liệu trên; không đưa
file vận hành ngoài Git hay DOCX hướng dẫn các tuần vào PR.
