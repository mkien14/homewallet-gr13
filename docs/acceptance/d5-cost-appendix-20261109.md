# D5 — AWS cost appendix (working draft)

Updated: 2026-11-11 (Asia/Saigon). This is an infrastructure inventory and
calculation worksheet, not an invoice. Current spend is intentionally left
unreported until reconciled against the AWS bill/Cost Explorer for a defined
period. Terraform alone does not prove resource uptime during that period.

## Scope and source record

- Primary Region: `ap-southeast-1`; CloudFront-scoped WAF: `us-east-1`.
- Infrastructure source: `infra/envs/dev` and `infra/modules` in this repo.
- Deployment/status snapshot: [`chi-week10-status-20261109.md`](chi-week10-status-20261109.md).
- Cost period: **TBD by team**. Record exact start/end in UTC and currency USD.
- Price source/retrieval date: **TBD**. Record AWS Pricing Calculator inputs and
  retrieval date for each rate.
- Budget: the status snapshot records a team threshold of USD 50/month. This
  is a limit, not an estimate or actual charge.

## Resource inventory and cost drivers

| Service/resource | Configuration in code or recorded deployment | Cost treatment | Evidence / uncertainty |
| --- | --- | --- | --- |
| NAT Gateway + Elastic IP | One NAT Gateway in a public subnet; one EIP | Hourly allocation plus data processing/transfer | Terraform includes one; 2026-11-09 snapshot says one NAT was available. Get billed hours and GB processed. |
| ALB | One application load balancer | ALB hours plus capacity units and data processed | Dev traffic is recorded; obtain exact hours and LCU usage. |
| ECS Fargate API | Task default 0.5 vCPU / 1 GiB; desired count defaults to 1 | vCPU and memory per running task-second; include other billable task storage if applicable | Desired count is configurable; derive actual task-hours from ECS/Cost Explorer. |
| ECS Fargate worker/jobs | Separate worker and scheduled task definitions; schedules configurable | vCPU/memory task runtime | Worker 1/1 was observed; scheduled task count/runtime needs verification. |
| RDS MySQL | `db.t4g.micro`, 20 GiB gp3 allocated, 50 GiB autoscaling ceiling; single-AZ in the recorded snapshot | DB instance hours, allocated storage, backups/snapshots, and I/O if applicable | Actual hours, storage growth, and backup usage need billing data. |
| ElastiCache Redis | Redis 7.1, one `cache.t4g.micro`, no Multi-AZ/failover | Cache node-hours and any backup/transfer charges | Terraform configuration; reconcile deployed hours. |
| WAF for CloudFront | Web ACL and common managed rule in `COUNT` | Web ACL, rule, and request charges | Recorded deployed in `COUNT`; obtain request totals. |
| CloudFront | Distribution serves SPA and API | Data transfer, requests, invalidations if any | Distribution and D4 endpoint are recorded; obtain regional request/transfer totals. |
| S3 | Receipt and frontend buckets | Storage, requests, transfer, versions/lifecycle | Billed bytes/requests are not in this checkout. |
| SQS / DLQ | Main receipt queue and dead-letter queue | Requests and payload/retention storage | One legacy DLQ message was recorded; obtain request totals and retention. |
| CloudWatch | Log groups, metrics, dashboard and alarms | Log ingest/retention, custom metrics, alarms, dashboard/API requests | Eight alarms/widgets recorded; obtain billed quantities. |
| SNS / SES | SNS operations topic; SES used by auth/jobs | SNS requests/data; SES message charges under account/region terms | SNS test email received; [#43 final acceptance](43-final-acceptance-20261110.md) records SES production access granted as of 10/11. Reconcile actual sending and billed usage for the selected period. |
| Cognito | User pool, app clients, custom-message Lambda integration | Monthly active users and optional feature usage | Pool config exists; MAU and invocation counts are needed. |
| Lambda | Cognito custom-message function | Invocations and duration/memory | Direct smoke is recorded; exact usage is unknown. |
| S3 Gateway Endpoint | Gateway endpoint for S3 in app route table | No hourly endpoint charge expected for a gateway endpoint; data transfer/request charges still need review | Terraform shows Gateway type. Verify no interface endpoints in the billing period. |
| Interface VPC endpoints | None reported in the 2026-11-09 review | Hourly per endpoint/AZ plus data processing if added | Review says only S3 Gateway Endpoint; verify inventory. |
| CloudTrail | No new trail reported in review | Trail/data-event charges depend on configuration and volume | Confirm account-level trails/event selectors. |
| ECR / Secrets Manager / KMS | Image storage, managed secrets, AWS-managed encryption keys | Storage, API requests, and key/request costs where applicable | Usage, retained image, and secret counts need billing evidence. |

## Calculation format

For each line, record quantity and source. Example for a continuously running
resource: `unit rate × billable hours × count`. For metered services use
`unit rate × measured requests/GB/GB-month`. Split fixed and usage-based parts;
do not count planned resources as deployed charges.

| Period (UTC) | Service / line item | Region | Quantity | Unit rate | Fixed / usage | Estimated USD | Actual USD | Source and retrieval date |
| --- | --- | --- | ---: | ---: | --- | ---: | ---: | --- |
| TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | AWS bill / Cost Explorer export required |

Report estimate and actual separately. Reconcile with AWS bill/Cost Explorer
for the same account, services, and billing period; explain taxes, credits,
shared costs, and rounding. D3 provider usage estimates are separate from AWS
infrastructure charges; see [`bedrock-benchmark.md`](../bedrock-benchmark.md).

## Public pricing references

Record source and retrieval date when filling rates; public list prices are not
a substitute for account-specific billing.

- [AWS Pricing Calculator](https://calculator.aws/)
- [Amazon VPC pricing](https://aws.amazon.com/vpc/pricing/)
- [Elastic Load Balancing pricing](https://aws.amazon.com/elasticloadbalancing/pricing/)
- [AWS Fargate pricing](https://aws.amazon.com/fargate/pricing/)
- [Amazon RDS for MySQL pricing](https://aws.amazon.com/rds/mysql/pricing/)
- [Amazon ElastiCache pricing](https://aws.amazon.com/elasticache/pricing/)
- [AWS WAF pricing](https://aws.amazon.com/waf/pricing/)
- [Amazon CloudFront pricing](https://aws.amazon.com/cloudfront/pricing/)
- [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/)
- [Amazon CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/)
