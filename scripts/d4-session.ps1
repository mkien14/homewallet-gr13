# Dot-source this file: . .\scripts\d4-session.ps1
# Configures the approved D4 dev session. Does not create users or test data.
. (Join-Path $PSScriptRoot 'dev.ps1')

$global:ApiBase = 'https://daoedidcrnf1f.cloudfront.net'
$env:HW_USER_PREFIX = 'd4-hoang-20261108'

# Override in global scope so the original Terraform-based helper is not used.
# Loading dev.ps1 again afterwards replaces this function; reload this file then.
function global:Get-DevToken($Email) {
    if ([string]::IsNullOrWhiteSpace($env:HW_TEST_PASSWORD)) {
        throw 'D4 password is empty. Reload scripts/d4-session.ps1.'
    }
    $d4Raw = aws cognito-idp initiate-auth --no-sign-request `
        --auth-flow USER_PASSWORD_AUTH --client-id '5h1qm7tdm4ksbrd8bv9ltcmsma' `
        --auth-parameters "USERNAME=$Email,PASSWORD=$env:HW_TEST_PASSWORD" `
        --region ap-southeast-1 --output json --no-cli-pager
    if ($LASTEXITCODE -ne 0) {
        throw "D4 Cognito login failed for $Email. Check the supplied password; this command does not use Terraform or IAM credentials."
    }
    $d4Auth = $d4Raw | ConvertFrom-Json
    if (-not $d4Auth -or -not $d4Auth.PSObject.Properties['AuthenticationResult']) {
        throw 'D4 login did not return AuthenticationResult. Check account status or an auth challenge.'
    }
    $d4Result = $d4Auth.AuthenticationResult
    if (-not $d4Result.PSObject.Properties['AccessToken'] -or
        [string]::IsNullOrWhiteSpace([string]$d4Result.AccessToken)) {
        throw 'D4 login did not return an access token.'
    }
    return $d4Result.AccessToken
}

# Clear any old/generated password and require the one supplied by Kien.
$env:HW_TEST_PASSWORD = ''
$d4Secret = Read-Host 'Nhap mat khau Kien da cap roi Enter (ky tu duoc an)' -AsSecureString
if ($d4Secret.Length -eq 0) {
    throw 'D4 password was not entered. Stop here and reload scripts/d4-session.ps1.'
}
$env:HW_TEST_PASSWORD = ([pscredential]::new('d4', $d4Secret)).GetNetworkCredential().Password
Remove-Variable d4Secret -ErrorAction SilentlyContinue

Write-Host "D4 dev session configured: $global:ApiBase"
Write-Host 'Next: verify both logins, then run AC3 after Kien confirms the test window.'
