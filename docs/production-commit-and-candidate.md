# Commit, push và nghiệm thu candidate

Đợt source: `fix/production-integration`, nền main `63fd2b9`.
Kiên tự làm Git; agent đã cấu hình 5 biến public cho candidate trên GitHub.
Không chạy Deploy Dev hoặc Reviewed production release của stack riêng.

## 1. Stage đúng danh sách, review, commit và push

Chạy tại repo hiện tại, không tạo thư mục mới. File pathspec chỉ gồm các file
của đợt này, không dùng `git add .`. Đọc danh sách trước nếu muốn đối chiếu:

```powershell
Set-Location 'C:\kì I 2026-2027\Cloud Computing\homewallet-gr13'
$currentBranch = git branch --show-current
if ($LASTEXITCODE -ne 0 -or $currentBranch -ne 'fix/production-integration') {
    throw 'Chưa ở đúng nhánh fix/production-integration'
}
git status --short
Get-Content .\deploy\production-change-paths-20261113.txt
git add --pathspec-from-file=deploy/production-change-paths-20261113.txt
if ($LASTEXITCODE -ne 0) { throw 'Stage chưa thành công' }

$stagedFiles = @(git diff --cached --name-only)
$approvedFiles = @(Get-Content .\deploy\production-change-paths-20261113.txt)
$unexpected = @($stagedFiles | Where-Object { $_ -notin $approvedFiles })
$unsafe = @($stagedFiles | Where-Object {
    $_ -match '(?i)\.(docx|pem|key|tfstate|tfplan|tar|zip)$|\.tfstate\.|\.tfvars(\.json)?$|(^|/)\.env($|\.)' -and
    $_ -notmatch '(^|/)\.env\.example$'
})
if ($unexpected.Count -gt 0 -or $unsafe.Count -gt 0) {
    throw 'Có file staged ngoài danh sách hoặc có file nhạy cảm/DOCX; dừng và kiểm tra'
}
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'Diff có lỗi cần xử lý' }
git diff --cached --stat
git diff --cached
```

Sau khi đọc diff, chạy riêng:

```powershell
git commit -m "fix: harden runtime and prepare controlled production rollout"
if ($LASTEXITCODE -ne 0) { throw 'Commit chưa thành công' }
git push -u origin fix/production-integration
if ($LASTEXITCODE -ne 0) { throw 'Push chưa thành công; không force push' }
git status --short
git log -1 --oneline
```

Nếu `git diff` mở màn hình phân trang, bấm `q` để thoát. Không reset/clean/stash
pop để xử lý lỗi Git chưa xác định. DOCX hướng dẫn các tuần không được stage.

## 2. PR và merge

Vào repository GitHub `mkien14/homewallet-gr13`, New pull request:
base `main`, compare `fix/production-integration`.

Tiêu đề gợi ý: `Harden runtime and prepare controlled production rollout`.
Nội dung: thay base/lock dependency; auth/limits/consent; API Gateway HTTPS;
release gates; budget 100 USD; closed rollout giữ/exclude household 1; chưa
apply AWS, MFA và resilience còn cần nghiệm thu. CI phải xanh và diff được
review trước Squash and merge. Không ép merge bỏ check đang đỏ.

Sau merge:

```powershell
git switch main
if ($LASTEXITCODE -ne 0) { throw 'Chưa chuyển được main' }
git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) { throw 'Main chưa fast-forward được; dừng để kiểm tra' }
$releaseSha = git rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $releaseSha -notmatch '^[a-f0-9]{40}$') { throw 'SHA không hợp lệ' }
$releaseSha
```

SHA squash trên main có thể khác commit nhánh. Dùng SHA main trong mọi bước
release. Báo link PR đã merge cho agent để tiếp tục; không làm Git cùng lúc
agent đang chỉnh source.

## 3. Candidate

Agent có quyền GitHub API hiện tại và có thể tự dispatch/download/kiểm tra sau
merge. Nếu Kiên tự thao tác UI: Actions → Build release candidate → Run workflow
→ branch `main` → Run workflow. Workflow phải thực sự xanh, không phải skipped.
Workflow dispatch chỉ xuất hiện sau khi workflow có trên default branch.
[GitHub: chạy workflow thủ công](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).

Đối chiếu commit của run với `$releaseSha`, đọc audit/scan/build/package steps.
Artifact `homewallet-release-<SHA>` phải có `backend.tar`, `frontend/`,
`manifest.json`, `SHA256SUMS`, `security/container-scan.json`,
`security/sbom.cdx.json`. Chỉ tải từ workflow chính repository này. Nếu muốn
kiểm tra file đã tải bằng máy hiện tại:

```powershell
$candidateZip = Join-Path $env:USERPROFILE "Downloads\homewallet-release-$releaseSha.zip"
$artifactDirectory = Join-Path $env:TEMP "homewallet-release-$releaseSha"
if (Test-Path -LiteralPath $artifactDirectory) { throw 'Thư mục đã có; chọn nơi trống, không trộn artifact' }
Expand-Archive -LiteralPath $candidateZip -DestinationPath $artifactDirectory -ErrorAction Stop
.\backend\.venv\Scripts\python.exe .\scripts\publish-frontend-release.py --artifact-dir $artifactDirectory --release $releaseSha --verify-only
if ($LASTEXITCODE -ne 0) { throw 'Candidate chưa đạt integrity/security gate' }
```

Mong đợi `ARTIFACT_INTEGRITY_VERIFIED`. Scan phải trong 72 giờ, 0 HIGH/CRITICAL
kể cả lỗi chưa có bản vá, 0 secret; SBOM đúng image và không có SQLite. Không
sửa timestamp hoặc ignore để chạy qua lỗi. Đạt integrity chưa nghiệm thu UI,
tenant isolation, AWS readiness hay hiệu năng. Agent sẽ kiểm tra API/worker/jobs
với đúng image trong môi trường canary kiểm soát, không dùng hộ 1 làm fixture.

## 4. MFA — từng chủ tài khoản tự thực hiện

Trước khi bỏ callback localhost/client CLI trong production profile, có thể
dùng source local mới để enroll:

```powershell
$env:VITE_API_TARGET = 'https://daoedidcrnf1f.cloudfront.net'
npm --prefix .\frontend run dev
```

Mở `http://localhost:5173/auth/react`, dùng tài khoản **admin ứng dụng** của mình
(không phải IAM user AWS). Vào `http://localhost:5173/security`, bấm bật ứng dụng
xác thực. Trong Microsoft/Google Authenticator chọn thêm tài khoản khác, nhập
setup key theo kiểu Time-based/TOTP. Nhập mã 6 số vào trang HomeWallet và xác nhận.
Đăng xuất và đăng nhập lại; phải được hỏi mã TOTP và đăng nhập thành công.
Lặp lại cho mọi admin còn bật. Không gửi mã/setup key/mật khẩu/token trong chat.
Chỉ báo kết quả challenge; agent đọc lại enrollment/preference trên Cognito.

Dừng Vite bằng Ctrl+C; gỡ biến cho shell này khi xong:

```powershell
Remove-Item Env:VITE_API_TARGET -ErrorAction SilentlyContinue
```

## 5. Sau candidate và MFA

Agent tiếp tục theo `production-rollout.md`: snapshot ID hộ hiện có trừ 1,
review recipient budget, saved plan, HTTPS origin/canary, cutover riêng, đóng
ingress cũ, review WAF rồi BLOCK, profile và image cùng SHA, gate/publish FE.
Không chạy Terraform song song hoặc dùng saved plan working-tree cũ.

Bàn giao resilience của Chi hiện chưa có; giữ NO_GO và phân công/bằng chứng trong
`acceptance/production-owner-decisions-20261113.md`. Chuẩn bị origin/budget có
thể tiến hành sau candidate; mở production đầy đủ phải chờ bàn giao này.
