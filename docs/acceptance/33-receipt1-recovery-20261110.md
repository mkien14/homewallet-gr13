# Receipt 1 — controlled recovery

Decision date: 2026-11-10 (Asia/Bangkok). Operator: Kiên.

Status: **SCOPE MISMATCH — EXTERNAL HOUSEHOLD DATA; DO NOT REVIEW OR CONFIRM**.
Kiên later clarified that household `1` belongs to a person outside the group.
The controlled attempt described below sent the receipt image to Gemini once and
created transaction `39` as `DRAFT`. It was not confirmed. Do not use this record
as a group test fixture, access it through another account, or process it further
until the data owner and group decide how to handle it.

Kiên selected retaining the original receipt and recovering it through a controlled
workflow. The scope is receipt `1`, household `1`; this does not reopen the D3 pilot
or authorize batch OCR, Bedrock, Textract, queue purge, or automatic confirmation.

## Readiness evidence

- [Read-only DB/S3 inspection](33-receipt1-inspection-20261110.json).
- [Provider metadata readiness](33-receipt1-readiness-20261110.json).
- Receipt is `FAILED / WORKER_MAX_ATTEMPTS`, with no linked transaction. The uploader
  is still a household member and the default uncategorized category exists.
- Original S3 object exists: JPEG, 97503 bytes. Object-key, ETag and version
  fingerprints are recorded; document contents and raw keys are omitted.
- Configured Gemini model metadata is accessible. This check did not generate
  content or send the invoice.
- Worker definition `hw-worker:3`, image digest
  `sha256:28e13fd5bcf16e1663be2e9b03ebe8ac21cbc52469f91d6211096a71700ff264`.
  Deployed pipeline and LLM source hashes match the reviewed local source.

## Execution bounds

The runner uses one temporary task from the existing worker definition. It repeats
readiness checks and requires the same saved fingerprint. It then locks the single
receipt row, checks membership, rejects any existing transaction or partial
extraction, and fetches only the object matching the inspected ETag.

The task allows one Gemini generation request (SDK attempts and application tries
both set to one) with Textract fallback disabled. These settings affect this task
only. A positive readable total is required. A successful result is stored as one
`DRAFT` transaction and receipt `NEEDS_REVIEW`; it is never auto-confirmed.

The original receipt ID, S3 object and DLQ message are retained. No queue receive,
delete, redrive or visibility change is part of this workflow. SQS retention still
applies naturally; recovery relies on the retained DB record and S3 object rather
than depending on the old queue message remaining available.

S3 control-plane checks confirmed versioning is enabled. For the `receipts/`
prefix, the current object transitions to `GLACIER_IR` after 90 days; there is no
current-version expiration in the configured rules. Noncurrent versions expire
after 30 days. The original object remains current because this workflow does not
overwrite it. No bucket lifecycle or versioning setting was changed.

Before persistence commits, any error rolls back DB changes and leaves the original
failed state. If the task is interrupted or post-commit verification fails, inspect
again before any retry: a transaction may already have committed. Do not delete a
draft or reset status merely to rerun the tool.

## Commands

From the repository root, using the existing dev operator credentials:

```powershell
python scripts/run-receipt-recovery.py --check-model --output docs/acceptance/NEW-readiness.json
python scripts/run-receipt-recovery.py --execute --plan-file docs/acceptance/NEW-readiness.json --output docs/acceptance/NEW-recovery.json
```

The runner refuses to overwrite evidence. Do not execute a second time after any
uncertain result. A read-only reinspection is safe and reports the current state.
The execute mode rejects a changed receipt or an existing transaction.

## Validation and outcome

- `tests/test_receipt_recovery.py` and `tests/test_worker.py`: **26 passed**;
  one dependency deprecation warning. No provider, S3 or DB calls in these tests.
- Runtime payload syntax and ECS override size checked locally.
- [Controlled attempt](33-receipt1-recovery-attempt-20261110.json): task
  `3936fa1ac177411ab29d9a60e5b117f1`, one generation call at
  `2026-11-10T11:10:07Z` (18:10 Asia/Bangkok), stopped with provider `ServerError`
  before persistence returned. No fallback or automatic retry was used. That
  attempt captured the error class, not its numeric HTTP status; the utility now
  records numeric HTTP status and locally allowlisted guard codes without logging
  exception text. This new provider error does not establish the October root cause.
- [Read-only postcheck](33-receipt1-postcheck-20261110.json): receipt remains
  `FAILED / WORKER_MAX_ATTEMPTS`, original timestamps and object metadata unchanged,
  zero linked transactions. The original object still exists and DLQ has 1 visible,
  0 in-flight messages. No queue message body was received.
- [Combined verification](33-receipt1-recovery-verification-20261110.json): all four
  temporary ECS tasks stopped. The follow-up inspection sent no invoice to a provider.

The retain-and-recover disposition is now recorded. Recovery succeeded on the
second guarded attempt. Any further action requires a fresh inspection and the same
duplicate/transaction guards; no recovery is scheduled or automatically retried.

## Successful controlled recovery — run 2

- Fresh [readiness inspection](33-receipt1-readiness-20261110-run2.json) completed
  at `2026-11-10T13:58:28Z`. Receipt state, membership, S3 fingerprints and Gemini
  model metadata matched the guarded preconditions; no invoice was sent during this
  check.
- [Recovery result](33-receipt1-recovery-run2-20261110.json): exactly one Gemini
  generation call, no SDK retry, no Textract fallback. At `2026-11-10T13:59:08Z`,
  receipt `1` changed to `NEEDS_REVIEW` and transaction `39` was created as `DRAFT`.
  The original object and DLQ message were retained.
- Read-only [postcheck](33-receipt1-postcheck-run2-20261110.json) completed at
  `2026-11-10T14:00:41Z`: one linked transaction, status `DRAFT`; receipt remains
  `NEEDS_REVIEW`; original S3 size, ETag fingerprint and version fingerprint match.
- All three ECS tasks stopped successfully. No second recovery was attempted.

The postcheck showed draft `39` exists, but the group has no confirmed authority to
review or confirm the outside person's transaction. Keep it unconfirmed. The old
DLQ message remains retained; this recovery did not receive, delete, redrive or
purge it. The group must decide, with appropriate authority, whether to remove the
mis-scoped data and how to handle the retained queue message. No further reads or
mutations should be made for acceptance purposes.

The DLQ alarm remains a separate operational follow-up until the stale message is
handled under a subsequent decision. A restored draft does not prove the original
October failure's root cause or establish an OCR benchmark result.
