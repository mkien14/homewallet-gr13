Set-StrictMode -Version Latest

if (-not $global:ApiBase) {
  throw "ApiBase is not configured. Dot-source scripts\dev.ps1 and call Use-LocalApi or Use-CloudApi first."
}
if (-not $env:HW_USER_PREFIX) {
  throw "Set `$env:HW_USER_PREFIX and create both test users with New-TestUsers first."
}

function Get-Code($Method, $Path, $Token) {
  $headers = @{}
  if ($Token) {
    $headers.Authorization = "Bearer $Token"
  }

  try {
    return [int](Invoke-WebRequest -Method $Method -Uri ($global:ApiBase + $Path) `
      -Headers $headers -UseBasicParsing).StatusCode
  } catch {
    if ($_.Exception.Response) {
      return [int]$_.Exception.Response.StatusCode
    }
    throw "Unable to call $Method $Path at ${global:ApiBase}: $($_.Exception.Message)"
  }
}

function Check($Name, $Got, $Want) {
  # In bằng Write-Host để dòng PASS/FAIL hiện ra ngay và không bị gom vào kết quả trả về.
  $ok = $Got -eq $Want
  Write-Host ("{0,-48} {1}" -f $Name, $(if ($ok) { "PASS" } else { "FAIL (nhận $Got, cần $Want)" }))
  $ok
}

function Ensure-Household($Token, $Name) {
  $me = Invoke-Api GET /api/me $Token
  if (-not $me) {
    throw "Could not load the user profile from /api/me."
  }
  if ($me.household) {
    return $me.household.id
  }

  $created = Invoke-Api POST /api/households $Token @{ name = $Name }
  if (-not $created -or -not $created.id) {
    throw "Could not create household '$Name'."
  }
  return $created.id
}

$a = Get-DevToken ("{0}.test1@example.com" -f $env:HW_USER_PREFIX)
$b = Get-DevToken ("{0}.test2@example.com" -f $env:HW_USER_PREFIX)
if (-not $a -or -not $b) {
  throw "Could not get tokens for both test users. Check HW_TEST_PASSWORD and Cognito."
}

$hidA = Ensure-Household $a "Hộ A"
$hidB = Ensure-Household $b "Hộ B"
if ($hidA -eq $hidB) {
  throw "Both test users belong to the same household; cross-household access cannot be verified."
}

$rec = Invoke-Api POST /api/receipts $a @{ content_type = "image/jpeg"; size = 1000 }
if (-not $rec -or -not $rec.receipt -or -not $rec.receipt.id) {
  throw "Could not create the test receipt."
}

$results = @(
  Check "Không có token"                     (Get-Code GET /api/me $null) 401
  Check "B xem thành viên hộ A"              (Get-Code GET "/api/households/$hidA/members" $b) 404
  Check "B xem hóa đơn của hộ A"             (Get-Code GET "/api/receipts/$($rec.receipt.id)" $b) 404
  Check "A xem thành viên hộ của chính mình" (Get-Code GET "/api/households/$hidA/members" $a) 200
)

if ($results -contains $false) {
  throw "AC3 verification FAILED at ${global:ApiBase}."
}

"AC3 verification PASSED at ${global:ApiBase}."
