mock_provider "aws" {
  mock_data "aws_caller_identity" { defaults = { account_id = "123456789012" } }
  mock_data "aws_region" { defaults = { name = "ap-southeast-1" } }
  mock_data "aws_iam_policy_document" { defaults = { json = "{}" } }
  mock_data "aws_kms_key" { defaults = { arn = "arn:aws:kms:ap-southeast-1:123456789012:key/00000000-0000-0000-0000-000000000000" } }
}
mock_provider "aws" { alias = "us_east_1" }
mock_provider "random" {}
variables {
  production_allowed_household_ids = [2]
  expected_account_id              = "123456789012"
  release_commit                   = "0000000000000000000000000000000000000000"
  migration_image_digest           = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
  release_digest                   = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
  origin_hostname                  = "origin.example.com"
  origin_zone_id                   = "Z1234567890"
  origin_certificate_arn           = "arn:aws:acm:ap-southeast-1:123456789012:certificate/00000000-0000-0000-0000-000000000000"
  gemini_model                     = "offline-test"
  ses_sender                       = "ops@example.com"
  db_instance_class                = "db.t4g.small"
  db_engine_version                = "8.4"
  final_snapshot_identifier        = "homewallet-prod-final-test123"
  operations_emails                = ["ops@example.com"]
  monthly_budget_usd               = 500
  waf_validation_reference         = "offline-test-only"
}
run "isolated_production" {
  command = plan
  assert {
    condition     = module.data.safety_policy.multi_az && module.data.safety_policy.retention >= 14 && module.data.safety_policy.deletion_protection && !module.data.safety_policy.skip_final_snapshot && !module.data.safety_policy.public && module.data.safety_policy.encrypted && !module.data.safety_policy.immediate
    error_message = "Production DB must retain HA, backups, encryption and deletion safeguards."
  }
  assert {
    condition     = module.compute.identities.cluster == "homewallet-prod" && module.compute.identities.families == ["homewallet-prod-api", "homewallet-prod-worker", "homewallet-prod-jobs"]
    error_message = "PROD must never use legacy DEV ECS identities."
  }
  assert {
    condition     = alltrue([for name in module.compute.identities.roles : startswith(name, "homewallet-prod-")]) && alltrue([for name in module.compute.identities.logs : startswith(name, "/ecs/homewallet-prod/")])
    error_message = "PROD roles/logs must be isolated."
  }
  assert {
    condition     = module.queue.queue_name == "homewallet-prod-receipts-queue" && module.queue.dlq_name == "homewallet-prod-receipts-dlq" && length(module.network.nat_gateway_ids) == 2
    error_message = "PROD requires isolated queues and a NAT per AZ."
  }
  assert {
    condition     = aws_secretsmanager_secret.runtime.name == "hw/prod/db-runtime" && aws_secretsmanager_secret.gemini.name == "hw/prod/gemini-api-key" && aws_secretsmanager_secret.vapid.name == "hw/prod/vapid-private-key"
    error_message = "PROD secrets must use hw/prod."
  }
}
run "reject_mutable_release" {
  command = plan
  variables { release_digest = "dev" }
  expect_failures = [var.release_digest]
}
run "reject_aws_origin_hostname" {
  command = plan
  variables { origin_hostname = "unsafe.ap-southeast-1.elb.amazonaws.com" }
  expect_failures = [var.origin_hostname]
}
