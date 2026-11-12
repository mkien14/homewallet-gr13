mock_provider "aws" {
  mock_data "aws_caller_identity" { defaults = { account_id = "123456789012" } }
  mock_data "aws_region" { defaults = { name = "ap-southeast-1" } }
  mock_data "aws_iam_policy_document" { defaults = { json = "{}" } }
  mock_data "aws_kms_key" { defaults = { arn = "arn:aws:kms:ap-southeast-1:123456789012:key/00000000-0000-0000-0000-000000000000" } }
  mock_data "aws_secretsmanager_secret" { defaults = { arn = "arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:hw/dev/test-abcdef" } }
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
