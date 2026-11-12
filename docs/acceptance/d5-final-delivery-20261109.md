# D5 / #38 and #41 — final delivery working pack

Updated: 2026-11-11 (Asia/Saigon), based on the acceptance records available in
this checkout through the 11/11 update. This remains a draft: recorded PASS or
CLOSED applies only to the scope of the linked evidence. It does not replace a
clean-clone check, cost reconciliation, or the group's final delivery review.

## README and reproducibility

The root README documents local setup, tests/build, the dev helper, deployment,
security, and operational references. Frontend and backend `.env.example`
templates are present in this working tree and need to be included with the
README links. Verify the instructions on a clean clone before calling this
deliverable complete.

## Status report for issues #25–43

Statuses below summarize the latest identified records in this checkout; they
do not assert that a feature outside the recorded scope has been deployed or
independently retested. See also the [team status review](team-open-work-20261110.md).

| Issue | Current evidence-based status | Evidence / remaining check |
| --- | --- | --- |
| #25 | PASS within recorded acceptance scope | Budget API dev run had 57/57 expected HTTP results; LLM/fallback and job cases were tested on a separate fixture schema. See [`25-37-budget-20261110.md`](25-37-budget-20261110.md). |
| #26 | Recorded push/notification cases passed; full scope needs owner confirmation | API notification/read, push registration/removal and receive evidence are summarized in [team review](team-open-work-20261110.md), [runtime](43-runtime-20261110.md), and [delivery](43-delivery-20261110.md); this does not cover every browser or failure path. |
| #27 | Baseline reported; not newly retested | The [team review](team-open-work-20261110.md) records the week-10 guide's existing baseline, without issuing new acceptance. Confirm owner, PR and scope for the final report. |
| #28 | Baseline reported; not newly retested | The [team review](team-open-work-20261110.md) records the week-10 guide's existing baseline, without issuing new acceptance. Confirm owner, PR and scope for the final report. |
| #29 | CLOSED / PASS per Kiên | [Final acceptance](29-final-acceptance-20261110.md) records runtime, UI, and audit checks; detailed runtime evidence is privately retained by Kiên. It does not claim a separate sign-off from Thức. |
| #30 | Baseline reported; not newly retested | The [team review](team-open-work-20261110.md) records the week-10 guide's existing baseline, without issuing new acceptance. Confirm owner, PR and scope for the final report. |
| #31 | PASS within approved WAF `COUNT` scope | [Team review](team-open-work-20261110.md) records acceptance in `COUNT`. Do not describe the rule as deployed in `BLOCK` mode. |
| #32 | Done per recorded review | Runtime DB least-privilege phase 2 is recorded as accepted in [`chi-week10-status-20261109.md`](chi-week10-status-20261109.md). |
| #33 | Done for monitoring implementation; old DLQ item tracked separately | Eight alarms/widgets and SNS test are recorded; one legacy failed receipt remains. See [`33-monitoring-kien-20261109.md`](33-monitoring-kien-20261109.md). |
| #34 | PARTIAL / NO-GO for a new image benchmark | The two consumed pilots produced no schema-valid predictions; the later Bedrock text smoke does not establish OCR accuracy or a provider winner. A new runner, quota/cost confirmation and a newly approved run identity are still needed. See [remediation](34-bedrock-remediation-20261110.md) and [pilot history](../bedrock-benchmark.md). Do not rerun the consumed pilots. |
| #35 | Needs owner evidence | No issue-specific acceptance report located in this checkout. |
| #36 | Closed by team decision | AC3, Member authorization, and bounded read-load evidence are recorded in [`36-d4-evidence.md`](36-d4-evidence.md). Closure does not mean OCR passed. |
| #37 | PASS within recorded budget/job acceptance scope | A real D1 test email was confirmed, repeat delivery was skipped and cleanup passed. The job ran by CLI on a separate schema; recurring Scheduler jobs remained disabled. See [`25-37-budget-20261110.md`](25-37-budget-20261110.md). |
| #38 | In progress | README and this draft pack are prepared; clean-clone verification and team review remain. |
| #39 | SCOPE MISMATCH / disposition pending | The [receipt recovery record](33-receipt1-recovery-20261110.md) concerns an external household. Preserve the existing draft, original receipt and DLQ evidence; await the data owner or designated steward's decision. Do not review, confirm, delete or redrive as a group fixture. |
| #40 | Mobile acceptance confirmed by Kiên; detailed evidence private | The [team review](team-open-work-20261110.md) says Thức completed mobile acceptance and supplied evidence privately to Kiên. Do not claim independent inspection or request a rerun solely to recreate it. |
| #41 | In progress | Demo storyboard is below; safe screen recording and team review remain. |
| #42 | Locale/auth scope PASS per team review | [Team review](team-open-work-20261110.md) records locale and email E2E acceptance; an auth entrypoint cutover is a separate rollout decision. |
| #43 | PASS within agreed acceptance scope | [Final acceptance](43-final-acceptance-20261110.md) records CM01–12 and CM14–16 PASS; CM13 is N/A by decision. Job emails were tested through SES simulator; recurring schedules and auth cutover remain separate rollout decisions. |

Before release, issue owners should confirm each status against the merged PR,
deployment, acceptance criteria, and any evidence missing from this repository.
Replace “needs owner evidence” only with a linked source.

## Demo storyboard for #41

Target a short walkthrough using a synthetic household and test account. Do
not use production-like household fixtures or real receipts.

1. Sign in using the approved test environment; hide addresses and account IDs.
2. Upload a synthetic receipt, show OCR processing, and review/edit the draft.
3. Confirm the transaction and show it in the dashboard/budget view.
4. Show one recurring bill or report/notification only if that exact path is
   deployed and verified in the demo environment.
5. Show CloudWatch dashboard/logs with account IDs, emails, request headers,
   tokens, and receipt contents obscured.
6. End with measured scope and limitations. Label D3 Partial/Blocked; do not
   present an OCR provider as a winner.

Recording checklist: use test data; remove personal data from the desktop;
disable notifications; inspect the capture for email, Authorization, secrets,
receipt text, and identifying URLs; obtain team approval before publishing.
No video is included in this working pack.

## Remaining inputs before final approval

- Owners confirm #26's full acceptance scope, the #27/#28/#30 baseline, #35's
  status, and the associated PR/commit links where missing. For #40, Kiên retains
  the detailed evidence privately; do not require a rerun merely to recreate it.
- Keep #34 Partial/NO-GO until the new image benchmark is approved and performed
  under a new runner and run identity. For #39 and D4 receipt 28, retain the
  recorded limitations and await the respective owner's disposition decisions.
- Finance/admin provides a Cost Explorer or bill export for the selected
  period; a budget threshold or partial zero-valued response is not actual
  spend.
- Product owner names competitor applications and approves comparison claims;
  see [`d5-app-comparison-20261109.md`](d5-app-comparison-20261109.md).
- Use [`d5-slides-outline-20261109.md`](d5-slides-outline-20261109.md) to make
  the deck, then record and review the demo in an approved environment.
- Kiên and the team review the final report and slides/video before delivery.
