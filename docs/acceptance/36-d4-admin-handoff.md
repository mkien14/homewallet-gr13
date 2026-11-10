# D4 / #36: Kiên chuẩn bị và bàn giao cho Hoàng

> Bản bàn giao lịch sử ngày 08/11/2026, được giữ lại khi hợp nhất worktree.
> #36 đã được nhóm chốt CLOSED ngày 09/11/2026; trạng thái hiện hành nằm trong
> [36-d4-evidence.md](36-d4-evidence.md). Không coi các việc chờ bên dưới là yêu
> cầu chạy lại nghiệm thu đã đóng.

Ngày kiểm tra: 08/11/2026 (Asia/Bangkok).
Trạng thái cập nhật: đã kiểm tra cấu hình/runtime và sự tồn tại của hai tài
khoản bằng thao tác chỉ đọc. Kiên báo Hoàng đã chạy xong mục 4; chưa nhận
output AC3 để đối chiếu. Chưa có bằng chứng tải nhẹ hoặc OCR mới trong cuộc
trao đổi này. Không đánh dấu toàn bộ D4 là PASS từ thông tin này.

## Phân công đã chốt sau mục 4

| Người | Việc cần hoàn tất | Đầu ra |
| --- | --- | --- |
| Hoàng | Gom output mục 4 đã chạy; ghi endpoint, commit thực tế, giờ chạy, kết quả từng ca, request ID/giới hạn bằng chứng và ID fixture nếu có | Phần AC3 trong `36-d4-evidence.md`; không chạy lại chỉ để lấy log |
| Hoàng | Tìm report/lock D3 từ máy đã chạy; tổng hợp mẫu thực có và lỗi; nếu chưa có thì ghi blocker | Phần OCR `Partial/Blocked`; chưa gọi OCR mới |
| Hoàng | Chạy tải đọc tối đa 5 client/2 phút sau tín hiệu sẵn sàng của Kiên; báo ngay khi dừng | p50/p95, số request, HTTP status, lỗi mạng/timeout, thời gian chạy |
| Hoàng | Làm sạch bằng chứng và ghi ID dữ liệu test đã tạo để phối hợp dọn | Báo cáo `36-d4-evidence.md` và artifact đã che dữ liệu |
| Kiên | Là người chịu trách nhiệm theo dõi tải; kiểm tra lại endpoint, commit/digest, API/worker, queue baseline và quyền xem metrics/log ngay trước tải | Tín hiệu "Dev và monitoring sẵn sàng, bắt đầu tải" cho Hoàng |
| Kiên | Thu CloudWatch trước/trong/sau tải, đối chiếu log và xử lý nếu có lỗi; Chi hỗ trợ khi cần | CPU/memory, ALB/target 5xx, SQS/DLQ, log đã làm sạch |
| Kiên | Giữ nguyên quyết định OCR chưa chạy mới/chưa mở rộng 42 ảnh; review bằng chứng, chốt kết quả và phối hợp dọn đúng fixture | Quyết định nghiệm thu Done/Partial/Blocked có lý do |

Không đặt giờ tải cố định khi chưa xác nhận monitoring. Hoàng chỉ bắt đầu
sau tín hiệu sẵn sàng của Kiên; Chi là người hỗ trợ, không thay đổi trách
nhiệm chính của Kiên. Nếu không thu được metrics/log, ghi blocker và hoãn tải.
Không deploy hoặc đổi cấu hình trong cửa sổ đo; nếu buộc phải thay đổi, dừng
và ghi nhận lần đo không còn cùng baseline.

Mục 1–4 bên dưới giữ làm hướng dẫn tái lập và xử lý sự cố, không yêu cầu tạo
lại user, đặt lại mật khẩu hoặc chạy lại AC3 khi mục 4 đã hoàn tất.

## Kết quả đã kiểm tra

| Mục | Giá trị / kết quả |
| --- | --- |
| AWS identity | `arn:aws:iam::179923444714:user/kien` |
| Region | `ap-southeast-1` |
| Dev endpoint | `https://daoedidcrnf1f.cloudfront.net` |
| Cognito pool | `ap-southeast-1_9mOMUx9Ds` |
| Cognito dev CLI client | `5h1qm7tdm4ksbrd8bv9ltcmsma` |
| Dev client auth | Có `ALLOW_USER_PASSWORD_AUTH` |
| API task definition | `hw-api:19` |
| API image commit tag | `95658d3b2bdfaad9b1930416f4b265e5861da16e` |
| API image digest | `sha256:28e13fd5bcf16e1663be2e9b03ebe8ac21cbc52469f91d6211096a71700ff264` |
| API service | Running 1/desired 1, pending 0, rollout `COMPLETED` |
| ALB target | `healthy` |
| API ping | HTTP 200, JSON `{"message":"pong"}` |
| Ping request ID | `e0e90eda-c98f-407a-b9cb-014325decf79` |
| Worker task definition | `hw-worker:2` |
| Worker cuối lần kiểm tra | Running 1/desired 1, pending 0, rollout `COMPLETED` |

Đây là ảnh chụp trạng thái, cần kiểm tra lại ngay trước khi chạy. Worker từng
đang thay task trong deployment ở lần đọc đầu; lần đọc cuối xác nhận cả API và
worker running 1/desired 1, pending 0, PRIMARY rollout `COMPLETED`.

## 1. Kiên tạo hai tài khoản riêng

Mở PowerShell tại thư mục gốc repo. Các lệnh tạo user dưới đây sẽ thay đổi
Cognito dev. Dùng prefix này riêng cho Hoàng/D4; chạy lại helper có thể đặt
lại mật khẩu hai tài khoản cùng prefix.

```powershell
$d4Account = aws sts get-caller-identity --query Account --output text
if ($LASTEXITCODE -ne 0 -or ([string]$d4Account).Trim() -ne '179923444714') {
    throw 'Dung lai: AWS session khong dung account dev.'
}

# Nhập mật khẩu riêng, nên từ 16 ký tự, có chữ hoa/thường và số.
# Gửi mật khẩu cho Hoàng qua kênh riêng; không đưa vào output/commit/tài liệu.
$d4Secret = Read-Host 'Mat khau test rieng cho Hoang' -AsSecureString
if ($d4Secret.Length -eq 0) { throw 'Chua nhap mat khau; dung tai day.' }
$env:HW_TEST_PASSWORD = ([pscredential]::new('d4', $d4Secret)).GetNetworkCredential().Password

. .\scripts\dev.ps1
$d4Pool = ([string](Get-TfOutput cognito_user_pool_id)).Trim()
$d4Client = ([string](Get-TfOutput cognito_dev_client_id)).Trim()
if ($d4Pool -ne 'ap-southeast-1_9mOMUx9Ds' -or $d4Client -ne '5h1qm7tdm4ksbrd8bv9ltcmsma') {
    throw 'Dung lai: pool/client khac ban da kiem tra.'
}
$env:HW_USER_PREFIX = 'd4-hoang-20261108'
New-TestUsers
```

Hai user dự kiến:

- `d4-hoang-20261108.test1@example.com`
- `d4-hoang-20261108.test2@example.com`

Helper dùng `SUPPRESS`, vì vậy không gửi email mời tới các địa chỉ giả này.
Đây là tài khoản cho AC3/tải đọc; không dùng để nghiệm thu nhận email, không
thêm vào group admin. Khi chưa có household, ca AC3 sẽ tạo hộ. Sau lần chạy
mục 4 đã được báo hoàn tất, cần lấy ID hộ/receipt từ bằng chứng thực tế;
không coi đây là tài khoản trống để tự tạo lại dữ liệu.

## 2. Kiên xác minh tạo user và đăng nhập

Giữ nguyên PowerShell ở bước 1 và chạy:

```powershell
foreach ($d4N in 1, 2) {
    $d4Email = "$env:HW_USER_PREFIX.test$d4N@example.com"
    $d4RawUser = aws cognito-idp admin-get-user --user-pool-id $d4Pool `
        --username $d4Email --region ap-southeast-1 `
        --query '{Username:Username,Enabled:Enabled,Status:UserStatus}' `
        --output json --no-cli-pager
    if ($LASTEXITCODE -ne 0) { throw "Khong doc duoc user $d4Email" }
    $d4User = $d4RawUser | ConvertFrom-Json
    if (-not $d4User.Enabled -or $d4User.Status -ne 'CONFIRMED') {
        throw "User chua san sang: $d4Email"
    }
    $d4Token = Get-DevToken $d4Email
    if ([string]::IsNullOrWhiteSpace([string]$d4Token)) {
        throw "Dang nhap that bai: $d4Email"
    }
    Write-Host "$d4Email : CONFIRMED / Enabled / LOGIN PASS"
}
Remove-Variable d4Token -ErrorAction SilentlyContinue
```

Chỉ bàn giao khi cả hai dòng `LOGIN PASS` xuất hiện. Không in/gửi access token.
Thông báo tạo thành công của `New-TestUsers` chưa đủ, vì helper chưa kiểm tra
đầy đủ exit code của AWS CLI.

## 3. Kiên/Chi chốt dịch vụ và người theo dõi

```powershell
aws ecs wait services-stable --cluster homewallet --services api worker `
    --region ap-southeast-1
if ($LASTEXITCODE -ne 0) { throw 'Chua xac nhan ECS stable; chua ban giao chay tai.' }

aws ecs describe-services --cluster homewallet --services api worker `
    --region ap-southeast-1 --output json --no-cli-pager `
    --query 'services[].{service:serviceName,running:runningCount,desired:desiredCount,pending:pendingCount,deployments:deployments[].{status:status,rollout:rolloutState}}'
```

Điều kiện: running bằng desired, pending 0, rollout PRIMARY `COMPLETED` cho
cả API và worker. Nếu có deploy mới, lấy lại commit/digest thực tế trước khi
bàn giao; không dùng snapshot ở trên cho bản deploy khác.

Chốt một người (Kiên hoặc Chi) theo dõi CloudWatch trong thời gian tải. Kiểm
tra dashboard/metrics/log thực sự xem được, không suy ra alarm đã deploy chỉ
từ file Terraform. Theo dõi:

- API/worker CPU và memory; ALB-generated và target-generated 5xx.
- SQS visible/in-flight và DLQ visible; ghi baseline trước tải.
- Log API `/ecs/hw-api` và log worker; chỉ chia sẻ trích đoạn đã che dữ liệu.

Tải tối đa 5 client đồng thời, 2 phút, chỉ GET
`/api/dashboard?period=2026-11`; `/api/ping` dùng kiểm tra đường đi trước tải.
Ghi p50/p95, request count, HTTP status, lỗi mạng/timeout và cửa sổ thời gian
đo. Dừng khi có 5xx hoặc queue tăng liên tục. Không upload/OCR/LLM trong tải.
Không dùng `/health` qua CloudFront làm bằng chứng backend: cấu hình hiện tại
chỉ route `/api/*` về ALB.

## 4. Hoàng cấu hình chạy AC3 mà không cần đọc Terraform state

Kiên gửi các ID cấu hình công khai ở trên và mật khẩu qua kênh riêng. Không
cấp quyền đọc toàn bộ Terraform state chỉ để đăng nhập hai tài khoản test.
Gửi kèm `scripts/d4-session.ps1`, đặt đúng thư mục `scripts` trong repo Hoàng.
File này chỉ cấu hình phiên, chưa gọi API hoặc tạo dữ liệu test.

Luôn nạp bằng dấu chấm `. .\scripts\d4-session.ps1`. Nạp lại `dev.ps1` sau
đó sẽ ghi đè hàm đăng nhập bằng bản cũ gọi Terraform; nếu đã làm vậy, nạp lại
`d4-session.ps1`. Lỗi STS `InvalidClientTokenId` kèm client ID trống và stack
trace trỏ vào `dev.ps1` cho thấy đang chạy hàm cũ, không chứng minh mật khẩu
Cognito sai. Không cần chạy `New-TestUsers` trên máy Hoàng để sửa lỗi này.

Trong PowerShell của Hoàng, tại thư mục gốc repo. Chuỗi trong dấu nháy của
`Read-Host` chỉ là lời nhắc. Khi hiện dấu `:`, gõ mật khẩu Kiên đã cấp rồi
Enter; ký tự được ẩn. Không thay lời nhắc bằng mật khẩu. Nhập trống có thể
khiến helper cũ tự sinh mật khẩu khác; hướng dẫn này chặn trường hợp đó.

```powershell
. .\scripts\d4-session.ps1

foreach ($n in 1, 2) {
    $email = "$env:HW_USER_PREFIX.test$n@example.com"
    $testToken = Get-DevToken $email
    if ([string]::IsNullOrWhiteSpace([string]$testToken)) {
        throw "Khong lay duoc token: $email"
    }
    Write-Host "$email : LOGIN PASS"
}
Remove-Variable testToken -ErrorAction SilentlyContinue

$d4Ping = Invoke-RestMethod -Method Get -Uri "$global:ApiBase/api/ping" -TimeoutSec 20
if ($d4Ping.message -ne 'pong') { throw 'Dev API ping khong hop le.' }

# Chỉ chạy sau khi Kiên chốt quyền tạo dữ liệu test và môi trường ở bước 3.
& .\scripts\verify-ac3.ps1
```

Lần chạy đầu tạo tối đa hai household riêng và một receipt `UPLOADING`.
Không join hai user vào cùng household/NewHome. Mỗi lần chạy tiếp lại tạo một
receipt; thống nhất số lượt chạy trước, ghi ID dữ liệu phát sinh. Script hiện
chưa tự dọn receipt và chưa lưu request ID, nên không coi PASS console là đã
đủ toàn bộ bằng chứng D4. Hoàng bổ sung ghi request ID của các ca và danh sách
fixture tạo ra trước khi đóng #36; dọn đúng receipt test theo ID đã ghi nhận,
không xóa dữ liệu hộ khác. Không tự chạy lại khi FAIL mà chưa xem nguyên nhân.

## 5. OCR giữ phạm vi đã duyệt

D3 ghi nhận quyền gửi 021–030 và nhãn tương ứng cho Gemini/Bedrock, trần
1 USD tổng / 0,50 USD mỗi provider cho pilot đã duyệt. Hai lần thử đã được
ghi nhận kết thúc một phần. Không tự mở rộng lên 42 ảnh, thêm Textract hoặc
chạy lại pilot. Workspace này chưa có report/lock lịch sử: lấy lại từ nơi đã
chạy, không xem thiếu lock là quyền chạy mới.

Nếu cần inference mới, Kiên chốt cùng nhóm danh sách ảnh, dịch vụ/model,
số lượt gọi, quyền chia sẻ và ngân sách còn lại/mới sau đối soát. Nhãn dùng
chấm offline. Phần OCR có thể ghi `Partial/Blocked` trong D4 với owner rõ.

## 6. Nội dung Kiên gửi Hoàng để chốt phần việc còn lại

Đây là phân công tiếp theo sau khi Kiên báo Hoàng đã chạy xong mục 4; không
thay thế kết quả kiểm thử hoặc xác nhận nghiệm thu toàn bộ D4.

> Hoàng, chốt phần còn lại của D4 như sau:
>
> Em gom output AC3 của mục 4 đã chạy, thông tin endpoint/commit/giờ chạy và
> ID dữ liệu test nếu có. Thiếu request ID hoặc log thì ghi giới hạn; không
> tự chạy lại chỉ để bổ sung bằng chứng.
>
> OCR: tìm lại report/lock D3 và tổng hợp kết quả thực có. Chưa chạy lại,
> thêm provider hoặc mở rộng 42 ảnh. Chưa lấy được artifact thì ghi blocker;
> phần này giữ Partial/Blocked, không tự kết luận model nào tốt hơn.
>
> Tải nhẹ: anh Kiên phụ trách kiểm tra dev và theo dõi CloudWatch; Chi hỗ trợ
> khi cần. Em chỉ bắt đầu sau khi anh báo dev/monitoring sẵn sàng. Tối đa
> 5 client đồng thời trong 2 phút, chỉ GET /api/dashboard?period=2026-11,
> kiểm tra /api/ping trước. Không upload/OCR/LLM. Dừng ngay khi có 5xx hoặc
> queue tăng liên tục; anh thông báo dừng nếu phát hiện từ monitoring.
>
> Em thu p50/p95, request count, status/lỗi, giờ bắt đầu/kết thúc. Anh thu
> CPU/memory API–worker, ALB/target 5xx, SQS/DLQ và log trước/trong/sau tải.
> Ghi rõ giới hạn: /api/ping không thay thế health check phụ thuộc; tải đọc
> dashboard không chứng minh tải xử lý OCR hoặc LLM.
>
> Em điền docs/acceptance/36-d4-evidence.md, gửi kèm artifact đã che dữ liệu.
> Anh review, chốt trạng thái từng phần và phối hợp dọn đúng receipt test.
> Phần không có bằng chứng giữ Partial/Blocked; không ghi toàn bộ D4 PASS.
