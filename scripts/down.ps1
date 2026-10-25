# Dỡ hạ tầng dev cuối buổi kiểm: xóa compute, migrate, data, network.
# Giữ nguyên tài nguyên tồn tại lâu: Cognito, S3 (hw-receipts + hw-frontend), ECR, CloudFront, SQS.
# Dựng lại sau này: terraform apply trong infra\envs\dev, rồi chạy lại task hw-migrate.
param([switch]$Yes)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$TfDir    = Join-Path $RepoRoot "infra\envs\dev"
$Region   = "ap-southeast-1"

# Hai biến không có default trong config; giá trị phải khớp lần apply gần nhất (xem terraform.tfvars nếu có).
$tfVars = @("-var", "gemini_model=gemini-3.6-flash", "-var", "worker_image_tag=worker-5c8186f")

Push-Location $TfDir
try {
  terraform plan -destroy -target=module.compute -target=module.migrate `
    -target=module.data -target=module.network @tfVars -out=down.tfplan
  if ($LASTEXITCODE -ne 0) { throw "terraform plan -destroy thất bại." }

  if (-not $Yes) {
    $answer = Read-Host "Plan đã lưu ở down.tfplan. Gõ YES để hủy các tài nguyên trong plan"
    if ($answer -cne "YES") {
      Write-Host "Đã dừng, chưa hủy gì. Khi muốn tiếp tục: terraform apply down.tfplan"
      return
    }
  }
  terraform apply -auto-approve down.tfplan
  if ($LASTEXITCODE -ne 0) { throw "terraform apply thất bại." }
}
finally { Pop-Location }

# Đối chiếu tài nguyên tồn tại lâu vẫn còn — đầu ra mong đợi của mục 6 buổi kiểm
$poolId = (terraform -chdir=$TfDir output -raw cognito_user_pool_id 2>$null)
$pool   = aws cognito-idp describe-user-pool --user-pool-id $poolId --region $Region --query "UserPool.Name" --output text 2>$null
"{0,-28} {1}" -f "Cognito pool", $(if ($pool) { "CÒN ($pool)" } else { "MẤT?!" })

$buckets = aws s3 ls --region $Region 2>$null | Where-Object { $_ -match "hw-" } | ForEach-Object { ($_ -split '\s+')[-1] }
"{0,-28} {1}" -f "S3 (receipts + frontend)", $(if ($buckets.Count -ge 2) { "CÒN ($($buckets -join ', '))" } else { "MẤT?!" })

$tags = aws ecr describe-images --repository-name homewallet-backend --region $Region --query "imageDetails[*].imageTags" --output text 2>$null
"{0,-28} {1}" -f "ECR homewallet-backend", $(if ($tags) { "CÒN ($($tags -replace '\s+', ', '))" } else { "MẤT?!" })

Write-Host "Lưu ý: API sẽ 502 cho tới khi dựng lại hạ tầng (terraform apply) và chạy lại hw-migrate."
