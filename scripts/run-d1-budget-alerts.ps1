# D1 (#25/#37): chạy job budget-alerts trên task hw-jobs, cluster homewallet (dev, ap-southeast-1).
# Cần policy homewallet-dev-d1-testing gắn trên user đang chạy (xem infra/policies/hoang-d1-testing.json).
# Chạy lần 1 và lần 2 CÙNG NGÀY để trùng period_key; lần 2 phải không gửi lại email và không
# tạo dòng trùng trong job_runs/alert_state. Lưu task id, exit code và log event làm bằng chứng.
param(
    [string]$Cluster = "homewallet",
    [string]$TaskDefinition = "hw-jobs"
)

$ErrorActionPreference = "Stop"

$overrides = "file://$PSScriptRoot/d1-overrides.json"
$network = "awsvpcConfiguration={subnets=[subnet-0b93773c2e4a4ca37,subnet-0e335e79cc6fb1c2d],securityGroups=[sg-09995b81438d70766],assignPublicIp=DISABLED}"

$result = aws ecs run-task `
    --cluster $Cluster `
    --task-definition $TaskDefinition `
    --launch-type FARGATE `
    --platform-version 1.4.0 `
    --network-configuration $network `
    --overrides $overrides |
    ConvertFrom-Json

if (-not $result.tasks) {
    throw "RunTask không tạo được task: $($result | ConvertTo-Json -Depth 5)"
}

$taskId = ($result.tasks[0].taskArn -split "/")[-1]
Write-Host "Đã khởi tạo task: $($result.tasks[0].taskArn)"
Write-Host ""
Write-Host "Bằng chứng cần lưu cho D1:"
Write-Host "  1. Chờ task xong rồi lấy exit code:"
Write-Host "       aws ecs wait tasks-stopped --cluster $Cluster --tasks $taskId"
Write-Host "       aws ecs describe-tasks --cluster $Cluster --tasks $taskId --query 'tasks[0].[lastStatus, stopCode, containers[0].exitCode, containers[0].reason]'"
Write-Host "  2. Log event:"
Write-Host "       aws logs get-log-events --log-group-name /ecs/hw-jobs --log-stream-name scheduled/jobs/$taskId"
Write-Host "  3. Kiểm tra không gửi trùng: chạy lại script này trong cùng ngày, sau đó đối chiếu"
Write-Host "     job_runs/alert_state không tăng dòng và hộp thư không nhận email lần 2."
