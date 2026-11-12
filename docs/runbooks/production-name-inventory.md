# Shared-name inventory and safe mapping

Line references below identify the audited pre-change sources. New expressions
preserve exact legacy names when `name == homewallet-dev`; PROD uses the provided
prefix. This is a source compatibility claim; a real DEV no-op plan remains a gate.

| Audited source:line | Legacy shared identifier | Safe PROD mapping |
| --- | --- | --- |
| compute/ecs.tf:4,9,13 | /ecs/hw-api, homewallet, hw-api | /ecs/homewallet-prod/api, homewallet-prod, homewallet-prod-api |
| compute/iam.tf:22 | hw-api-task-role | homewallet-prod-api-task-role |
| compute/worker.tf:2,7 | /ecs/hw-worker, hw-worker | /ecs/homewallet-prod/worker, homewallet-prod-worker |
| compute/worker-iam.tf:29 | hw-worker-task-role | homewallet-prod-worker-task-role |
| compute/scheduled-jobs.tf:4,13,38 | /ecs/hw-jobs, hw-weekly-report-task-role, hw-jobs | PROD log path, prefix for role/family |
| compute/scheduled-jobs.tf:135,140,145 | hw-recurring-reminders, hw-budget-alerts, hw-weekly-report | homewallet-prod-* schedule names in separate group |
| migrate/main.tf:14,19,24 | hw-migrate-task-role, /ecs/hw-migrate, hw-migrate | PROD prefix and /ecs/homewallet-prod/migrate |
| migrate/runtime-bootstrap.tf:20,27 | /ecs/hw-db-runtime-bootstrap, hw-db-runtime-bootstrap | PROD log path and family |
| queue/main.tf:6,17 | receipts-dlq, receipts-queue | optional name_prefix; empty default preserves DEV |
| envs/dev/main.tf:272,280 | hw/dev/gemini-api-key, hw/dev/vapid-private-key | separate secret containers hw/prod/* |
| envs/dev/db-runtime.tf:4 | hw/dev/db-runtime | hw/prod/db-runtime, separate bootstrap grants |
| cache/main.tf:7 | homewallet-dev/redis-auth-token | optional secret name hw/prod/redis-auth-token |
| compute/iam.tf:12; migrate/execution-iam.tf:2 | already name-derived execution roles | remain name-derived |
| data/main.tf; cache/main.tf | name-derived database/Redis IDs/groups | homewallet-prod-* |
| storage/main.tf; frontend/main.tf | env/account bucket names | prod/account distinct, force_destroy=false |
| cognito/main.tf, custom-message.tf | name-derived pool/client/domain/Lambda/roles | distinct PROD name; no DEV CLI client |
| ecr/main.tf | caller-selected repository | dedicated homewallet-prod-backend, immutable tags |
| edge/main.tf | name-derived OAC/function, generated distribution ID | PROD names and independent distribution |
| envs/dev/waf.tf, monitoring.tf | DEV-specific names | separate PROD root resources |
| team-access/main.tf:17 | state bucket /* read grant | PROD excluded; separate PROD backend bucket mandatory |

Files are relative to `infra/modules` unless prefixed `envs/`. AWS managed policies,
prefix lists, managed cache policies and alias/aws/s3 are AWS shared services,
not mutable DEV-owned resources. Inline policy names, ECS service/container names
and local origin IDs are scoped to their parent resource and can safely match.
