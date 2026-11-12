# Production hardening handoff

Implemented from the supplied production implementation brief on 2026-11-12.
This is a code delivery, not an operational acceptance or deployment report.

## Verification

| Check | Observed output |
| --- | --- |
| Terraform 1.10.5 `fmt -check -recursive infra` | exit 0 |
| DEV `init -backend=false -input=false` | Terraform has been successfully initialized! |
| DEV `validate -no-color` | Success! The configuration is valid. |
| PROD `init -backend=false -input=false` | Terraform has been successfully initialized! |
| PROD `validate -no-color` | Success! The configuration is valid. |
| DEV mocked Terraform plan test | Success! 1 passed, 0 failed. |
| PROD mocked Terraform plan tests | Success! 3 passed, 0 failed. |
| Backend pytest, Python 3.12 | 201 passed, 50 skipped in 199.73s |
| Production release safety pytest | 9 passed |
| Workflow YAML parsing and production Python syntax | passed |
| `git diff --check` | exit 0; Git reports normal LF/CRLF conversion notices |

The 50 backend skips are environment-gated integration/acceptance tests; they
are not evidence of MySQL/AWS runtime acceptance. Offline Terraform tests use
mock providers and do not read remote state or AWS. Local tooling/dependencies
were installed under ignored `.tools/`; no machine-wide installation was made.
DEV's existing provider lock was retained; PROD starts with the same versions.

No real DEV or PROD plan was run: an approved read-only AWS identity, authorized
backend access and reviewed production inputs were not supplied. Therefore the
real DEV no-op and PROD-only action gates remain **unverified**. Do not infer
zero replacements from validate or mock plans. No backend state was migrated.

## Remaining launch blockers

- Approved AWS production account, dedicated state bucket, GitHub OIDC plan/deploy
  roles and production Environment reviewer/branch protections.
- ACM issued certificate, matching public origin DNS/zone and ownership review.
- RDS exact engine/class Multi-AZ orderability, patch policy and capacity/cost
  approval; monthly budget and approved notification recipients.
- Dedicated ECR image promotion and provenance/attestation review, immutable
  release digest, populated production application secrets, reviewed schema
  migration and runtime credential bootstrap before ECS launch.
- SES access and sender/recipient approval; schedules remain disabled.
- WAF false-positive review and final blocking approval; notification testing.
- Real DEV no-op plan, reviewed PROD plan and separate infrastructure apply.
- Multi-AZ healthy API/scaling, TLS, Redis/NAT failover, queue/retry/worker drills,
  snapshot/PITR restore and measured/signed-off RPO/RTO plus rollback rehearsal.

The PROD backend intentionally uses `hw-tfstate-homewallet-prod-gr13`, rather than
the DEV bucket: existing DEV team access permits reading every object in the DEV
bucket. Using a new key alone would not isolate sensitive production state.
Provision/authorize the separate bucket before backend initialization; see
`production-readiness.md` for sequencing and required operational evidence.

No AWS resources applied and no production deployment performed.

## Changed files and purpose

The file inventory below records this delivery only. Pre-existing untracked
`Microsoft/` content was not modified.

| File | Reason |
| --- | --- |
| `.github/workflows/ci.yml` | Validate and mock-plan both environments; run release safety tests. |
| `.github/workflows/deploy-prod.yml` | Manual immutable release, security/plan review, protected approval, smoke and staged rollout. |
| `.gitignore` | Exclude portable local verification tools and dependencies. |
| `backend/app/db.py` | Optional short socket timeouts for readiness probes; regular DB behavior preserved. |
| `backend/app/main.py` | Expose dependency-free liveness and cached DB readiness routes. |
| `backend/app/readiness.py` | Cache/rate-limit DB SELECT 1 probes, close connections, fail closed without leaking errors. |
| `backend/tests/test_health.py` | Verify readiness success/failure/cache recovery/concurrency and liveness. |
| `docs/runbooks/ecs-rollback.md` | Compatibility-checked task rollback with smoke/queue verification and schema limitations. |
| `docs/runbooks/incident-response.md` | Incident triage, escalation, evidence and recovery checks. |
| `docs/runbooks/production-implementation-handoff.md` | Verification results, file inventory and explicit unresolved deployment blockers. |
| `docs/runbooks/production-name-inventory.md` | Inventory legacy shared names with audited source lines and safe mappings. |
| `docs/runbooks/production-readiness.md` | Launch evidence gates, protected OIDC setup, staged secret/bootstrap provisioning and operational tradeoffs. |
| `docs/runbooks/rds-restore.md` | Snapshot/PITR isolated restore drill, measured recovery and approved deletion procedure. |
| `infra/envs/dev/tests/compatibility.tftest.hcl` | Mock-plan assertions for legacy resource identities and single NAT default. |
| `infra/envs/prod/.terraform.lock.hcl` | Pin provider versions aligned with the existing DEV lock. |
| `infra/envs/prod/main.tf` | Independent production state/providers/network/data/services/secrets/storage/auth/origin resources. |
| `infra/envs/prod/monitoring.tf` | PROD alarms/dashboard/SNS/RDS and deployment events, scoped event role and tagged cost budget. |
| `infra/envs/prod/outputs.tf` | Expose non-secret operational identifiers for deployment and recovery. |
| `infra/envs/prod/terraform.tfvars.example` | Credential-free placeholders and explicit review requirements. |
| `infra/envs/prod/tests/isolation.tftest.hcl` | Mock-plan assertions for PROD isolation/DB safeguards and rejected unsafe inputs. |
| `infra/envs/prod/variables.tf` | Required reviewed account/image/TLS/sizing/budget inputs and guard validations. |
| `infra/envs/prod/waf.tf` | Separate managed-rule WAF with blocking default and explicit staging count mode. |
| `infra/modules/cache/main.tf` | Expose node/failover/AZ/snapshot/secret options with unchanged DEV defaults. |
| `infra/modules/cache/outputs.tf` | Expose non-secret identifiers/policy metadata for monitoring and isolation tests. |
| `infra/modules/cache/variables.tf` | Introduce optional production controls while preserving existing DEV defaults. |
| `infra/modules/cognito/custom-message.tf` | Configurable Lambda log retention; PROD 30 days, DEV unchanged. |
| `infra/modules/cognito/variables.tf` | Introduce optional production controls while preserving existing DEV defaults. |
| `infra/modules/compute/alb.tf` | Optional certificate-backed HTTPS listener; PROD readiness target check. |
| `infra/modules/compute/ecs.tf` | Preserve DEV service via moved block; isolate PROD cluster/families/logs, AZ rebalancing and CPU autoscaling. |
| `infra/modules/compute/iam.tf` | Use legacy-compatible environment-specific API task role name. |
| `infra/modules/compute/naming.tf` | Central legacy DEV and isolated PROD prefix/log mappings. |
| `infra/modules/compute/outputs.tf` | Expose non-secret identifiers/policy metadata for monitoring and isolation tests. |
| `infra/modules/compute/scheduled-jobs.tf` | Isolate schedules/family/role/logs; PROD release may update scoped revisions while Terraform owns enable state. |
| `infra/modules/compute/variables.tf` | Introduce optional production controls while preserving existing DEV defaults. |
| `infra/modules/compute/worker-iam.tf` | Use legacy-compatible environment-specific worker task role name. |
| `infra/modules/compute/worker.tf` | Isolate worker family/logs; retain single stop-first worker and DEV management; PROD release owns revision. |
| `infra/modules/data/main.tf` | Expose backup/maintenance/upgrade/snapshot policies with unchanged legacy defaults. |
| `infra/modules/data/outputs.tf` | Expose non-secret identifiers/policy metadata for monitoring and isolation tests. |
| `infra/modules/data/variables.tf` | Introduce optional production controls while preserving existing DEV defaults. |
| `infra/modules/ecr/main.tf` | Dedicated PROD immutable/protected repository; retain tagged release digests. |
| `infra/modules/edge/main.tf` | Select HTTPS-only origin for PROD; retain HTTP-only legacy default. |
| `infra/modules/edge/variables.tf` | Introduce optional production controls while preserving existing DEV defaults. |
| `infra/modules/migrate/main.tf` | Parameterize migration family, task role and log retention. |
| `infra/modules/migrate/naming.tf` | Preserve legacy migration names while deriving isolated PROD identities. |
| `infra/modules/migrate/runtime-bootstrap.tf` | Parameterize runtime bootstrap family/logs and retention. |
| `infra/modules/migrate/variables.tf` | Introduce optional production controls while preserving existing DEV defaults. |
| `infra/modules/network/main.tf` | Add same-AZ NAT/routes for additional AZs without moving original DEV addresses. |
| `infra/modules/network/outputs.tf` | Expose non-secret identifiers/policy metadata for monitoring and isolation tests. |
| `infra/modules/network/security_groups.tf` | Select CloudFront origin ingress 80 for DEV or 443 for PROD. |
| `infra/modules/network/variables.tf` | Introduce optional production controls while preserving existing DEV defaults. |
| `infra/modules/queue/main.tf` | Optional queue prefix; retain exact legacy names by default. |
| `infra/modules/queue/outputs.tf` | Expose non-secret identifiers/policy metadata for monitoring and isolation tests. |
| `infra/modules/queue/variables.tf` | Introduce optional production controls while preserving existing DEV defaults. |
| `scripts/deploy-production.py` | Guard immutable release/account/source/scan/domain/roles; deploy API then drained worker and disabled jobs; retain rollback metadata. |
| `scripts/production-plan-summary.py` | Publish action-only plan artifact without state, values or binary plan. |
| `scripts/tests/test_deploy_production.py` | Reject unsafe releases before mutations; ensure failed smoke stops worker rollout and preserves rollback record. |
