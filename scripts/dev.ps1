$Region = "ap-southeast-1"
$TfDir  = Join-Path $PSScriptRoot "..\infra\envs\dev"

if (-not $env:HW_TEST_PASSWORD) {
  $env:HW_TEST_PASSWORD = "Hw-" + (-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 12 | ForEach-Object { [char]$_ })) + "aA1"
}

function Get-TfOutput($Name) {
  Push-Location $TfDir
  try { terraform output -raw $Name } finally { Pop-Location }
}

function New-TestUsers {
  $pool = Get-TfOutput cognito_user_pool_id
  foreach ($u in "test1@example.com", "test2@example.com") {
    aws cognito-idp admin-create-user --user-pool-id $pool --username $u `
      --user-attributes "Name=email,Value=$u" "Name=email_verified,Value=true" `
      --message-action SUPPRESS --region $Region 2>$null | Out-Null
    aws cognito-idp admin-set-user-password --user-pool-id $pool --username $u `
      --password $env:HW_TEST_PASSWORD --permanent --region $Region
  }
  Write-Host "Đã đặt mật khẩu thử cho phiên này (HW_TEST_PASSWORD)."
}

function Get-DevToken($Email) {
  $client = Get-TfOutput cognito_dev_client_id
  $r = aws cognito-idp initiate-auth --auth-flow USER_PASSWORD_AUTH --client-id $client `
    --auth-parameters "USERNAME=$Email,PASSWORD=$env:HW_TEST_PASSWORD" --region $Region | ConvertFrom-Json
  $r.AuthenticationResult.AccessToken
}

function Invoke-Api($Method, $Path, $Token, $Body) {
  $p = @{ Method = $Method; Uri = ("http://" + (Get-TfOutput alb_dns_name) + $Path)
          Headers = @{ Authorization = "Bearer $Token" } }
  if ($Body) {
    $p.ContentType = "application/json; charset=utf-8"
    $p.Body = [Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json))
  }
  try { Invoke-RestMethod @p }
  catch { Write-Host "Lỗi HTTP:" $_.ErrorDetails.Message -ForegroundColor Yellow }
}