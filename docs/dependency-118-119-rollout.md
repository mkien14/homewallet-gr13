# Merge bản sửa gộp #118 và #119

Agent đã sửa và kiểm tra tại repo hiện tại, nhánh
`fix/dependency-release-118-119`; Kiên tự thực hiện commit/push/merge.
Không merge nguyên trạng PR #118 hoặc #119 cũ.

## 1. Review, commit và push

```powershell
git branch --show-current
git status --short
Get-Content .\deploy\dependency-118-119-paths-20261113.txt
git add --pathspec-from-file=deploy/dependency-118-119-paths-20261113.txt
if ($LASTEXITCODE -ne 0) { throw 'Stage thất bại' }
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'Diff chưa hợp lệ' }
git diff --cached --stat
git diff --cached
```

Chỉ chạy sau khi review:

```powershell
git commit -m "fix: align React versions and upgrade Redis client safely"
if ($LASTEXITCODE -ne 0) { throw 'Commit thất bại' }
git push -u origin fix/dependency-release-118-119
if ($LASTEXITCODE -ne 0) { throw 'Push thất bại' }
```

Danh sách stage đã gồm biên bản MFA của Kiên, bằng chứng test/security và audit
HA chỉ đọc. Không gồm DOCX hướng dẫn tuần, .env, secret, tfstate, tar hoặc log.

## 2. Tạo PR và chờ CI

GitHub: base `main`, compare `fix/dependency-release-118-119`.
Tiêu đề: `Fix #118/#119: align React versions and upgrade Redis safely`.
Nội dung: thay thế hai PR Dependabot #118/#119; React/DOM 19.3.1; Redis client
8.1.0 + hash lock; TLS/cache/admission tests; chưa deploy AWS; HA chưa nghiệm thu.

Chờ mọi check bắt buộc xanh, đặc biệt Frontend tests, Backend tests với bước
Redis TLS mới và Build backend image, rồi Squash and merge. Nếu check đỏ, giữ PR
mở để sửa. Sau khi bản gộp đã merge, đóng hai PR #118/#119 cũ vì đã được thay thế.
Sáu PR GitHub Actions vẫn để đợt riêng.

## 3. Đồng bộ main và tiếp tục production

```powershell
git switch main
if ($LASTEXITCODE -ne 0) { throw 'Chưa chuyển được main' }
git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) { throw 'Chưa cập nhật được main' }
git rev-parse HEAD
```

Agent dùng SHA main mới để build/quét candidate; kiểm tra artifact, thực hiện
canary rồi mới đưa image/frontend cùng SHA lên AWS. Bằng chứng HA hiện còn thiếu:
RDS Multi-AZ/bảo vệ xóa/backup retention; API hai AZ/scaling/readiness; diễn tập
snapshot/PITR restore và rollback đo được. Theo `production-rollout.md`, không
chuyển NO_GO thành GO khi chỉ có code hoặc một snapshot sẵn có.
