# ECS release rollback

1. Open an incident/change record: account/region, UTC timestamp, bad commit and
   digest, cluster `homewallet-prod`, service, task revision, observed migration
   version and impact. Retrieve `production-release-record.json` from the release.
2. Verify the recorded previous task ARN belongs to the same PROD family/account,
   its image digest still exists in `homewallet-prod-backend`, and roles, secrets,
   schema and writes are backward compatible. Obtain schema owner approval.
   An irreversible migration needs its own forward repair or isolated recovery
   plan. ECS rollback never reverses database changes or user writes.
3. With approved deploy identity, update the affected service to the recorded
   previous task ARN and wait for ECS services-stable. Use the recorded ARN,
   never guess a revision or use latest/dev tags. Circuit breaker may already
   have rolled back a failed release: inspect primary deployment/task definition.
4. API: require >=2 ALB healthy targets across two AZs, `/api/ready` and authenticated
   `/api/me`; check application 5xx and RDS resources. `/health` inside the VPC
   confirms liveness only. Stop further rollout if checks fail.
5. Worker: pause uploads, drain visible/inflight/delayed queue messages, confirm
   old/new processing compatibility, roll back the single stop-first worker,
   verify a synthetic receipt and queue/DLQ behavior, then resume producers.
   If jobs were revised, restore each recorded prior schedule task ARN while
   preserving DISABLED state and verify scheduler IAM permits that revision.
6. Record healthy time, measured recovery, task/digest evidence and residual risks.
   Set canonical release_digest to the restored release and privately inspect
   Terraform reconciliation before any later infrastructure apply.

Never automatically roll back schema or restore a backup over the primary.
