# Production incident response

1. Acknowledge the SNS/on-call event, name an incident commander and record UTC
   time, severity, scope, account and region. Confirm the alert against dashboard,
   ALB targets, ECS events/logs, RDS events and CloudWatch metric dimensions.
   Missing data may indicate telemetry failure. Use 30-day logs and avoid posting
   credentials, tokens, receipt contents or Terraform state in tickets.
2. Freeze releases and scheduled-job enabling. Preserve release record, previous
   task revision/digest, migration version and recent change ticket. Escalate
   according to the approved on-call roster; email subscriptions must be confirmed.
3. API failures: compare `/health`, `/ready`, target health, task counts, target
   5xx and DB connectivity. Inspect circuit breaker and AZ placement before using
   `ecs-rollback.md`. DB failures: check storage/memory/connections, maintenance,
   failover events and latest-restorable-time; follow `rds-restore.md` for recovery.
4. Queue/worker stall: inspect oldest age, visible/inflight/delayed counts, DLQ and
   worker logs. Pause producers if necessary. Do not purge queues or mass-redrive
   poison messages; inspect a controlled sample and verify idempotency first.
5. NAT failures: correlate same-AZ route mappings, NAT drops/port allocation errors
   and task egress errors. Do not reroute private data subnets to the Internet.
   Redis: inspect replica lag/CPU/failover, primary endpoint DNS and reconnects;
   assess cache degradation independently of DB readiness.
6. WAF/TLS: inspect blocked counts and legitimate request tests, certificate expiry,
   chain and origin hostname. A TLS mismatch can cause CloudFront 502. Scope an
   approved rule exception; never leave blanket count-only mode after resolution.
7. Confirm authenticated smoke, synthetic receipt, alarms cleared and notifications
   received. Record recovery time/data loss against approved RTO/RPO and any cost
   impact. Assign corrective actions and retain evidence under forensic policy.
