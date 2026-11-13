mock_provider "aws" {
  mock_data "aws_caller_identity" { defaults = { account_id = "123456789012" } }
  mock_data "aws_region" { defaults = { name = "ap-southeast-1" } }
  mock_data "aws_iam_policy_document" { defaults = { json = "{}" } }
  mock_data "aws_kms_key" { defaults = { arn = "arn:aws:kms:ap-southeast-1:123456789012:key/00000000-0000-0000-0000-000000000000" } }
  mock_data "aws_secretsmanager_secret" { defaults = { arn = "arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:hw/dev/test-abcdef" } }
}

run "existing_stack_resilience_without_renaming" {
  command = plan
  variables {
    enable_api_https_gateway                = true
    enable_api_service_discovery            = true
    application_origin_verification_enabled = true
    resilience_hardening_enabled            = true
    resilience_apply_immediately            = true
    api_desired_count                       = 2
  }
  assert {
    condition = (
      module.compute.identities.cluster == "homewallet" &&
      module.data.identifier == "homewallet-dev-mysql" &&
      length(module.network.nat_gateway_ids) == 2
    )
    error_message = "Harden the current stack without replacing its database or cluster."
  }
  assert {
    condition = (
      module.data.safety_policy.multi_az &&
      module.data.safety_policy.retention == 14 &&
      module.data.safety_policy.deletion_protection &&
      !module.data.safety_policy.skip_final_snapshot &&
      !module.data.safety_policy.public &&
      module.data.safety_policy.encrypted
    )
    error_message = "Production requires private encrypted Multi-AZ RDS and retained backups."
  }
}

run "direct_ecs_requires_origin_verification" {
  command = plan
  variables {
    enable_api_https_gateway     = true
    enable_api_service_discovery = true
  }
  expect_failures = [var.enable_api_service_discovery]
}
mock_provider "aws" { alias = "us_east_1" }
mock_provider "random" {}
variables { gemini_model = "offline-test" }
run "legacy_names_and_defaults" {
  command = plan
  assert {
    condition     = module.compute.identities.cluster == "homewallet" && module.compute.identities.families == ["hw-api", "hw-worker", "hw-jobs"]
    error_message = "Legacy ECS cluster/families must remain unchanged."
  }
  assert {
    condition     = module.compute.identities.logs == ["/ecs/hw-api", "/ecs/hw-worker", "/ecs/hw-jobs"]
    error_message = "Legacy log groups must remain unchanged."
  }
  assert {
    condition     = module.compute.identities.roles == ["hw-api-task-role", "hw-worker-task-role", "hw-weekly-report-task-role"]
    error_message = "Legacy IAM task roles must remain unchanged."
  }
  assert {
    condition     = module.queue.queue_name == "receipts-queue" && module.queue.dlq_name == "receipts-dlq"
    error_message = "Default queue names must remain unchanged."
  }
  assert {
    condition     = module.data.identifier == "homewallet-dev-mysql" && length(module.network.nat_gateway_ids) == 1
    error_message = "Legacy RDS and single NAT topology must remain unchanged."
  }
}
