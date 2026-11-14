# Public production release — 16f87ea

**Status: released and accepted with documented limits.** Date: 14/11/2026.

- Website: https://daoedidcrnf1f.cloudfront.net
- Main source: `16f87ea10d4fc6c47afd198e3ee77274fa6c3013`
- [Build release candidate](https://github.com/mkien14/homewallet-gr13/actions/runs/43567562979); artifact `14102797171`
- Runtime: API `hw-api:38` (2/2), worker `hw-worker:14` (1/1), jobs `hw-jobs:12`; immutable image digest is recorded in the linked JSON.
- CloudFront publish and invalidation completed; deployed frontend and API release SHA match.
- Production preflight: **99/99 GO**; final Terraform plan: **No changes**.
- Three recurring schedules are ENABLED and target `hw-jobs:12`.

## Public user flow

The project admin directly confirmed testing the public signup button, email verification, login after verification, creating a new household and joining a household. This is recorded as an operator attestation; the acceptance file does not store the mailbox address, credentials, OTPs or screenshots. Separate application evidence records synthetic-user signup/confirmation/reset, TOTP, owner/member roles, cleanup and the retained-household-1 boundary.

## Recovery and limits

Current-release restore, task replacement, RDS/Redis failover and API rollback evidence is summarized in the JSON. An initial stale-image restore probe was excluded; both restore checks passed after repeating with API `:38`. The rollback test briefly used `:37`, where public registration was disabled; `:38` was restored and readiness verified. Temporary resources were cleaned.

**Live OCR submission for a newly registered public user was not tested.** The prior synthetic-image OCR canary remains evidence for its recorded release only. This release does not claim a dedicated AWS Cost Explorer/invoice amount, Google Gemini cost coverage, a broad OCR benchmark or long-duration SLA. Household 1 and its legacy data/images/queues/DLQ remain separately retained.

Detailed machine-readable record: [production-public-16f87ea-20261114.json](production-public-16f87ea-20261114.json). The earlier restricted-scope acceptance files remain historical records.
