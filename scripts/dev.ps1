$Region   = "ap-southeast-1"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$TfDir    = Join-Path $RepoRoot "infra\envs\dev"

if (-not $env:HW_TEST_PASSWORD) {
  $env:HW_TEST_PASSWORD = "Hw-" + (-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 12 | ForEach-Object { [char]$_ })) + "aA1"
}

$global:ApiBase = "http://localhost:5000"
function Use-LocalApi { $global:ApiBase = "http://localhost:5000" }
# API chạy trên ECS, vào qua CloudFront (ALB chỉ nhận request có header xác thực từ CloudFront).
function Use-CloudApi { $global:ApiBase = (Get-TfOutput cloudfront_url).Trim() }
function Use-AlbApi   { Use-CloudApi } # tên cũ trong hướng dẫn, giữ lại để kịch bản cũ chạy được

function Get-TfOutput($Name) {
  Push-Location $TfDir
  try { terraform output -raw $Name } finally { Pop-Location }
}

function Write-DevEnvFiles {
  # Ghi backend\.env + frontend\.env.local từ terraform output.
  # Mặc định: UI cục bộ gọi API trên ECS (qua CloudFront). -LocalApi: gọi backend chạy máy mình.
  # Nếu terraform output lỗi thì dừng và KHÔNG ghi, để không bao giờ để lại file env rỗng.
  param([switch]$LocalApi)

  $out = @{}
  foreach ($name in "cognito_user_pool_id", "cognito_issuer", "cognito_jwks_uri", "cognito_spa_client_id",
           "cognito_dev_client_id", "cognito_hosted_ui", "receipts_bucket", "cloudfront_url") {
    $value = (Get-TfOutput $name 2>$null)
    if ([string]::IsNullOrWhiteSpace("$value")) {
      throw "Terraform output '$name' trống hoặc lỗi. Chạy 'terraform init' trong infra\envs\dev rồi thử lại (không ghi file env khi thiếu giá trị)."
    }
    $out[$name] = "$value".Trim()
  }

  $apiTarget = if ($LocalApi) { "http://localhost:5000" } else { $out.cloudfront_url }
  $selfSignupEnabled = (Get-TfOutput "cognito_self_signup_enabled" 2>$null)
  if ($LASTEXITCODE -eq 0 -and "$selfSignupEnabled".Trim().ToLowerInvariant() -in @("true", "false")) {
    $selfSignupEnabled = "$selfSignupEnabled".Trim().ToLowerInvariant()
  } else {
    Write-Warning "Terraform output 'cognito_self_signup_enabled' is unavailable; local public sign-up stays disabled until infra\envs\dev is applied."
    $selfSignupEnabled = "false"
  }

  Set-Content -Encoding ascii -Path (Join-Path $RepoRoot "backend\.env") -Value @(
    "COGNITO_ISSUER=$($out.cognito_issuer)", "COGNITO_JWKS_URI=$($out.cognito_jwks_uri)",
    "COGNITO_CLIENT_IDS=$($out.cognito_spa_client_id),$($out.cognito_dev_client_id)",
    "COGNITO_HOSTED_UI=$($out.cognito_hosted_ui)",
    "DB_HOST=localhost", "DB_PORT=3307", "DB_USER=root", "DB_PASSWORD=devpass",
    "S3_BUCKET=$($out.receipts_bucket)", "AWS_REGION=$Region")

  Set-Content -Encoding ascii -Path (Join-Path $RepoRoot "frontend\.env.local") -Value @(
    "VITE_COGNITO_DOMAIN=$($out.cognito_hosted_ui)", "VITE_COGNITO_CLIENT_ID=$($out.cognito_spa_client_id)",
    "VITE_COGNITO_USER_POOL_ID=$($out.cognito_user_pool_id)", "VITE_ENABLE_REACT_AUTH_UI=true",
    "VITE_API_TARGET=$apiTarget", "VITE_ENABLE_HOSTED_UI_FALLBACK=false",
    "VITE_SELF_SIGN_UP=$selfSignupEnabled")

  $mode = if ($LocalApi) { "backend cục bộ localhost:5000" } else { "ECS qua CloudFront" }
  Write-Host "Đã ghi backend\.env và frontend\.env.local (API: $mode)."
  Write-Host "Nếu dev server đang chạy: Ctrl+C rồi 'npm run dev' lại để nạp cấu hình mới."
}

function New-TestUsers {
  param([string]$Prefix = $env:HW_USER_PREFIX)
  if (-not $Prefix) { throw "Đặt trước: `$env:HW_USER_PREFIX = 'ten-cua-ban' (chữ thường, không dấu)" }
  $pool = Get-TfOutput cognito_user_pool_id
  foreach ($n in 1, 2) {
    $u = "$Prefix.test$n@example.com"
    aws cognito-idp admin-create-user --user-pool-id $pool --username $u `
      --user-attributes "Name=email,Value=$u" "Name=email_verified,Value=true" `
      --message-action SUPPRESS --region $Region 2>$null | Out-Null
    aws cognito-idp admin-set-user-password --user-pool-id $pool --username $u `
      --password $env:HW_TEST_PASSWORD --permanent --region $Region
  }
  Write-Host "Đã tạo $Prefix.test1 và $Prefix.test2 (mật khẩu: `$env:HW_TEST_PASSWORD)."
}

function Get-DevToken($Email) {
  $client = Get-TfOutput cognito_dev_client_id
  $r = aws cognito-idp initiate-auth --auth-flow USER_PASSWORD_AUTH --client-id $client `
    --auth-parameters "USERNAME=$Email,PASSWORD=$env:HW_TEST_PASSWORD" --region $Region | ConvertFrom-Json
  if (-not $r.PSObject.Properties["AuthenticationResult"]) {
    throw "Đăng nhập Cognito thất bại cho $Email. Chạy lại New-TestUsers trong cùng phiên (mật khẩu test đổi theo mỗi phiên)."
  }
  $r.AuthenticationResult.AccessToken
}

function Invoke-Api($Method, $Path, $Token, $Body) {
  $p = @{ Method = $Method; Uri = ($global:ApiBase + $Path)
          Headers = @{ Authorization = "Bearer $Token" } }
  if ($Body) {
    $p.ContentType = "application/json; charset=utf-8"
    $p.Body = [Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json))
  }
  try {
    Invoke-RestMethod @p
  } catch {
    $status = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { $null }
    $detail = $_.Exception.Message
    if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
      $detail = $_.ErrorDetails.Message
    }
    if ($status) {
      throw "HTTP $status khi gọi $Method $Path tại $global:ApiBase`: $detail"
    }
    throw "Không thể gọi $Method $Path tại $global:ApiBase`: $detail"
  }
}

function Test-DevSetup {
  $checks = @(
    @{ Name = "git";       Cmd = { git --version } },
    @{ Name = "python";    Cmd = { python --version } },
    @{ Name = "node";      Cmd = { node --version } },
    @{ Name = "docker";    Cmd = { docker version --format "{{.Server.Version}}" } },
    @{ Name = "aws";       Cmd = { aws --version } },
    @{ Name = "terraform"; Cmd = { terraform -version } },
    @{ Name = "AWS login"; Cmd = { aws sts get-caller-identity --query Arn --output text } }
  )
  foreach ($c in $checks) {
    try {
      $out = & $c.Cmd 2>&1
      if ($LASTEXITCODE -ne 0) { throw ($out | Select-Object -First 1) }
      "{0,-10} OK    {1}" -f $c.Name, ($out | Select-Object -First 1)
    } catch {
      "{0,-10} LỖI   {1}" -f $c.Name, $_
    }
  }
  foreach ($f in "backend\.env", "frontend\.env.local") {
    "{0,-22} {1}" -f $f, $(if (Test-Path (Join-Path $RepoRoot $f)) { "có" } else { "THIẾU (chạy Write-DevEnvFiles)" })
  }
  $envLocal = Join-Path $RepoRoot "frontend\.env.local"
  if (Test-Path $envLocal) {
    $target = (Get-Content $envLocal | Where-Object { $_ -like "VITE_API_TARGET=*" }) -replace "^VITE_API_TARGET=", ""
    "{0,-22} {1}" -f "API target", $(if ($target) { $target } else { "THIẾU trong frontend\.env.local" })
  }
  $mysql = docker ps --filter name=hw-mysql --format "{{.Status}}" 2>$null
  "{0,-22} {1}" -f "MySQL hw-mysql", $(if ($mysql) { $mysql } else { "chưa chạy (docker start hw-mysql)" })
}