# Isolated RDS recovery drill

Requires an approved change ticket, named operator and restricted production role.
Restore creates billable resources. Do not execute merely to validate this code.

1. Record `homewallet-prod-mysql` instance ARN/ID, exact engine/version/class,
   Multi-AZ status, subnet/SG IDs, KMS ARN, backup/maintenance windows, retention,
   latest restorable time and current alarm state. Identify snapshot/PITR time and
   proposed unique restore ID, for example `homewallet-prod-restore-<ticket>`.
2. Create an approved manual snapshot and wait for available. Restore that
   snapshot and separately test PITR to **new isolated instances**. Explicitly
   supply private data subnet group, no public accessibility, encryption/KMS and
   a dedicated SG allowing only the drill validator. Never overwrite primary,
   reuse app SG ingress, change primary DNS, or connect production apps to drills.
   Verify restore API parameters, secret behavior and KMS grants before execution.
3. From an approved private validation task, verify TLS certificate/hostname,
   runtime credential grants, schema and migration version, table row counts,
   synthetic reads and a disposable synthetic transaction. No production data
   may be exported to DEV or logs. Recreate reviewed parameter/access controls
   rather than assuming snapshots restored every setting.
4. Record request time, available time and successful query time. Measure restore
   duration/RTO and actual recovery point/RPO including latest-restorable-time
   lag. Have the business owner approve targets after seeing measurements.
   Failover does not replace backup. Rehearse controlled cutover separately;
   coordinate writers, DNS/secret changes and prevention of split-brain writes.
5. Retain evidence and snapshot per policy. Remove only the explicitly identified
   drill resources under approved cleanup. Review retained snapshot/storage cost.

Primary deletion requires separate approval: verify a recoverable snapshot and
PITR first, choose an unused `homewallet-prod-final-<ticket>` identifier, update
the reviewed configuration, explicitly authorize deletion-protection override,
preserve automated backups and observe the final snapshot becoming available.
Do not disable S3/Secrets Manager prevent_destroy guards as a shortcut.
[AWS deletion and retained backup behavior](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_DeleteInstance.html).
