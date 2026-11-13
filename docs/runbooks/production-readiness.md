# Production readiness and release gates

> **Scope clarification, 2026-11-13:** this runbook describes the optional isolated
> stack introduced by PR #103. The administrator-selected path retains the
> existing CloudFront URL and does not purchase a domain or create another stack.
> Follow [the existing-stack decision](../production-readiness.md) and
> [its rollout](../production-rollout.md) for that path. Do not run this workflow
> against legacy resources or treat merged isolated-stack code as live HA evidence.

Status: code prepared only. No AWS resources applied and no production deployment performed.
All runtime acceptance gates remain open until evidence is attached to a change ticket.

## Isolation and DEV compatibility

Production uses `homewallet-prod`, CIDR `10.1.0.0/16`, a dedicated immutable ECR
repository, `hw/prod/*` application secrets, independent Cognito, queues, Redis,
RDS, buckets, WAF and monitoring. RDS manages its administrator secret under an
AWS-generated name; runtime tasks cannot read it. The team-access module is excluded.

The existing DEV collaborator policy allows `GetObject` on every key in
`hw-tfstate-homewallet-gr13`. Consequently PROD uses a **separate state bucket**
`hw-tfstate-homewallet-prod-gr13` and key `prod/terraform.tfstate`. Provision and
authorize that encrypted, versioned, private bucket under separate change control;
do not use the DEV bucket unless its wildcard access is separately corrected.
A separate production account is preferred. If using another bucket/account,
review `terraform init -backend-config=...`, bucket policy and role trust first.
No DEV backend or team policy is changed by this implementation.

Compute/migrate naming maps `homewallet-dev` to legacy names. All other names are
derived from the supplied environment name. Existing NAT, EIP, route table and
subnet association addresses remain intact. `moved` blocks map DEV API and worker
services to `[0]` without replacing them; DEV retains Terraform desired-count and
worker task-definition management. PROD uses release-managed service resources;
API scaling owns desired count. Service/container names `api`, `worker`, `jobs`
and inline policy names are locally scoped and may intentionally match.

## Before any apply

1. Review `production-name-inventory.md`, the exact source diff and lock files.
2. Run `terraform fmt -check -recursive infra`, then init with `-backend=false`
   and validate for both environments. Run `terraform test` in each environment
   when tests are present. CI performs these checks without AWS credentials.
3. Under an approved read-only DEV identity, initialize the actual DEV backend
   and run `terraform plan -lock=false -detailed-exitcode`. Require exit 0 and no
   replacements. A state-address move alone is acceptable only after reviewer
   confirmation. Stop on any actual DEV resource change; do not apply to fix drift.
4. Copy the safe PROD example into an ignored tfvars file and replace placeholders.
   Use a reviewed account and backend. Plan with a read-only production identity;
   inspect every ARN, resource action and tag. First plan must create only PROD.
   Never publish state, binary plan or full plan JSON; they contain sensitive data.
5. Verify RDS engine availability using `describe-db-engine-versions` and
   `describe-orderable-db-instance-options --engine mysql --engine-version <exact>
   --db-instance-class <reviewed> --region ap-southeast-1`. Require MultiAZCapable
   and the selected AZs. The example `db.t4g.small` is a candidate, not a verified
   region/engine sizing choice. Load-test connection/memory thresholds.
6. Confirm an issued ACM certificate in ap-southeast-1 covers the origin hostname,
   and authorize a new CNAME in the specified public zone. No existing record may
   be overwritten. The ALB origin is HTTPS only, TLS >=1.2; SG permits CloudFront
   prefix-list ingress on 443 only. Never use an AWS ALB hostname with an unrelated
   certificate. [AWS origin TLS requirements](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-https-cloudfront-to-custom-origin.html).
7. Approve cost: two NATs plus data processing, Multi-AZ RDS (standby billed), two
   Redis nodes, 2–4 API tasks plus one worker, WAF, logs/Container Insights,
   backup/S3 retention, ECR and transfer. Set a reviewed monthly budget, activate
   the `env` cost-allocation tag, confirm SNS email subscriptions. Budgets are
   alerts, not spend caps. DEV budgets remain independently managed.
8. Stage WAF in count mode, collect metrics and test legitimate auth/API/uploads;
   attach false-positive review to `waf_validation_reference`. Final production
   default applies managed blocking actions. Do not leave count mode on at launch.

## First provisioning and database bootstrap

Apply is a separate, approved operator action; no workflow performs it. Review a
staged infrastructure change: create dedicated ECR and secret containers before
starting ECS workloads. Do not apply the entire environment with empty secrets or
a nonexistent image digest. Promote the reviewed image into the new repository.
Populate `hw/prod/vapid-private-key` and
`hw/prod/db-runtime` through an approved secret-management session, never tfvars.
The origin-verification secret is populated by Terraform in protected state.
The merged application profile sets APP_ENV=production, admission/consent on,
and AI/OCR off; it does not inject the exposed Gemini key. Populate a rotated
Gemini key only for a separately accepted AI/OCR release.
The runtime JSON must contain `username: hw_runtime` and a generated `password`.
Run the reviewed migration and runtime-bootstrap tasks manually, in private app
subnets with the app SG, before enabling application traffic. Verify the limited
DB grants and TLS. Migration execution has its own schema/data approval; no DEV
data is copied. Shared service execution IAM cannot read the administrator secret.
Redis AUTH is generated in protected state; state is secret material.

RDS backup UTC window is 18:00–19:00 (01:00–02:00 Vietnam next day), maintenance
Sunday 20:00–21:00 UTC (Monday 03:00–04:00 Vietnam). Apply immediately and automatic
minor upgrades are disabled: schedule reviewed patch releases and monitor AWS
mandatory maintenance. Engine drift is intentionally ignored for legacy
compatibility; review actual engine version before every upgrade or release.

## GitHub and release approval setup

Create `production-plan` and `production` Environments in GitHub. Restrict both to
main; require independent reviewers for `production`, prevent self-review and
disable approval bypass. These server-side controls cannot be installed by YAML.
Use independent plan/deploy OIDC roles, with audience `sts.amazonaws.com` and
exact subjects `repo:mkien14/homewallet-gr13:environment:production-plan` and
`repo:mkien14/homewallet-gr13:environment:production` respectively. No wildcard
branch/repository trust. Scope state access to the PROD bucket/key. Plan role has
read/describe access only; deploy role cannot apply Terraform or modify DEV.
Deploy permissions: scoped ECR reads/scans, ECS describe/list/register new PROD
families/update PROD services, pass only PROD task roles to ecs-tasks, SQS read
attributes for PROD queue, and get/list/update only the PROD scheduler group.
Allow read-only ALB target health and CloudFront GetDistribution for the PROD
distribution so the release verifies actual targets and the smoke-test domain.
IAM policy review must account for ECS APIs that lack resource-level scoping.

Environment variables: `AWS_PROD_ACCOUNT_ID`, `AWS_PROD_PLAN_ROLE_ARN` (plan),
`AWS_PROD_DEPLOY_ROLE_ARN` (production), `PROD_TFVARS_JSON` (non-secret required
variables; omit release_digest and release_commit), `PROD_URL`, `PROD_QUEUE_URL`,
`PROD_CLOUDFRONT_DISTRIBUTION_ID`. Secret: `PROD_SMOKE_TOKEN`, a fresh short-lived
token for an approved synthetic Cognito principal. Never archive tokens.

Set `release_commit` and `release_digest` to the reviewed application identity.
Keep `migration_image_digest` pinned to the separately applied migration/bootstrap
image. Updating migrations, roles, environment, secrets, CPU/memory or any other
non-release configuration requires a separate infrastructure plan/apply and then
a fresh application plan; the application workflow cannot apply those changes.
It never runs a migration or bootstrap and cannot silently accept their changes.

The redacted plan artifact contains only resource addresses/actions, release
identity, release-only decisions and existing API/worker/jobs task revision ARNs.
It contains no container configuration or secret/environment values. Unknown
configuration fails closed. Both approval gate and deploy script check the same
artifact. Deploy clones these exact reviewed revisions and changes only image
and APP_RELEASE; the running revision is recorded as the rollback target.

Promote an attested image from the exact reviewed 40-character main ancestor,
verify build provenance/source commit, then tag it `sha-<commit>` in the dedicated
immutable repository. No automatic DEV/latest promotion. Record attestation
verification in the compatibility ticket. The workflow verifies digest/tag and a
completed ECR scan with no HIGH/CRITICAL findings. This scan is not a substitute
for provenance review. CI tests/builds the selected commit before planning.

Dispatch `deploy-prod.yml` on main with that commit, digest, observed migration
version and compatibility ticket. Review the redacted resource-action artifact
and detailed plan privately before approving. The workflow blocks infrastructure
changes except task-definition revisions; initial creation needs separate apply.
API deploy and authenticated smoke precede worker rollout. Pause receipt uploads
externally under the ticket, drain visible/inflight/delayed messages (three 20s
observations), then allow one stop-first worker. Keep uploads paused until worker
verification. Queue observations alone do not prevent new producers. Scheduled
job targets update to the same digest while remaining DISABLED. Resume uploads,
submit a synthetic receipt and verify worker processing; record the result.
Update the canonical release_digest in operator tfvars after success so future
Terraform plans do not propose obsolete task revisions. No automatic migrations.

## Runtime evidence required for launch

- API: at least two healthy tasks in distinct AZs; 100/200 rolling deployment,
  circuit-breaker rollback, CPU target 60%, min 2/max 4; load-test scale out/in.
  Confirm ECS AZ balancing. [ECS autoscaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-auto-scaling.html).
- `/health` is dependency-free liveness. `/ready` (ALB) and `/api/ready` (CloudFront)
  cache DB probes for 10s per process, use 2s socket connect/read/write timeouts,
  close connections, return generic 503 and fail closed during concurrent probes.
  DNS resolution and aggregate network timing still need environment testing.
  Redis/Gemini/SES failures do not directly fail readiness. Never cache readiness
  at a CDN. Confirm authenticated `/api/me` using the designated principal.
- RDS: Multi-AZ, >=14-day backup, no public access, encryption, deletion protection;
  observe snapshot/latest-restorable-time and complete `rds-restore.md`.
- NAT: inspect app subnet/AZ -> route table -> same-AZ NAT mappings; data subnet
  tables have no Internet default route. Record an approved AZ failure drill.
- Redis: two nodes in distinct AZs, TLS/AUTH, seven-day snapshots. Use the primary
  endpoint for writes; test reconnect/DNS failover and record timing/cost.
- Worker: visibility 180s, maxReceiveCount 3, DLQ retains 14 days. Verify processing
  stays within visibility or extends it, retries and poison-message redrive are
  idempotent; record restart drill. Do not add replicas or change stop-first.
- Monitoring: verify real dimensions with CloudWatch list-metrics, deliberately
  trigger/clear alarms and confirm on-call receipt. Check target 5xx/unhealthy,
  task counts, deployment/RDS failover events, RDS resources, queue age/DLQ,
  NAT drops/port exhaustion and Redis CPU/replication; missing metrics are not
  proof of health. Dashboards and 30-day ECS/migration/Lambda retention enabled.
  Review KMS, log access and longer forensic exports before launch.
- Keep schedules disabled until SES production access, sender/recipient approval,
  cron/timezone effects and limited runtime DB credentials are verified.
- Approve measured RPO/RTO, cost estimate, rollback and migration mitigation.

Evidence per drill: change ticket, UTC start/end, operator, account/region,
resource IDs, observations, duration, result and follow-up owner. Never mark
these gates complete based only on configuration or a successful validate.
