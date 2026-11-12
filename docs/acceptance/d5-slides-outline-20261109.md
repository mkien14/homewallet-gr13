# D5 — slide outline for final delivery

Drafted: 2026-11-09; updated: 2026-11-11. This is slide-ready content, not a
rendered slide deck.
Use screenshots from an approved test environment and cite the linked evidence
in speaker notes or a final references slide.

## Slide 1 — HomeWallet

- Shared household expense tracking with receipt review, budgets, recurring
  bills, reports, and notifications.
- Audience: household members managing shared spending.
- Show: synthetic account/dashboard screenshot only after a fresh capture.
- Claim limit: describe only flows verified in the deployed environment.

## Slide 2 — Application and AWS dev architecture

- React/Vite frontend served from S3 through CloudFront.
- CloudFront routes API requests to ALB and ECS/Fargate Flask services.
- RDS MySQL stores application data; S3 and SQS support receipt processing;
  Redis is an API dashboard cache; Cognito handles authentication.
- CloudWatch collects service logs/metrics; WAF is currently recorded in
  `COUNT` mode.
- Source: Terraform under `infra/`; deployment status and exceptions in
  `chi-week10-status-20261109.md`.

## Slide 3 — User flow

- Sign in → upload a synthetic receipt → inspect/edit OCR draft → confirm
  transaction → review dashboard and budget.
- Add recurring bills/report/notification only if the exact path is available
  and verified at recording time.
- Presenter note: do not show a real receipt, email, token, household ID, or
  invite code.

## Slide 4 — Access control and reliability evidence

- D4 / #36 closed by group decision on 2026-11-09.
- Member evidence: `/api/me` role `member`; same-household member list GET 200;
  owner-only invite-code POST 403.
- Independent read-load run: 5 clients, 2 minutes, 279/279 HTTP 200, p95
  339.11 ms; no p95 SLA was set.
- Cite `36-d4-evidence.md` and PR #91 evidence; keep the run attribution clear.

## Slide 5 — Operations and cost

- Show the CloudWatch dashboard/alarms from an approved console session.
- Eight alarms and widgets are recorded; SNS test email was received.
- One legacy failed receipt remains in DLQ; do not present its alarm as cleared.
- Show a cost slide only after adding the period-specific bill/Cost Explorer
  totals to `d5-cost-appendix-20261109.md`; the USD 50/month threshold is a
  budget, not actual spend.

## Slide 6 — Limits and next work

- D3 / #34 remains Partial/Blocked: no schema-valid pilot predictions, no
  accuracy comparison, and no provider winner. Do not rerun consumed pilots.
- #43 locale/email acceptance passed within the agreed scope; auth cutover and
  enabling recurring schedules remain separate rollout decisions. See
  `43-final-acceptance-20261110.md`.
- Clearly separate deployed features, measured results, and planned work.
- Link the full status and cost appendix; ask the team to confirm the remaining
  issue statuses before final submission.

## Capture checklist

- Use only synthetic data and an approved test account/environment.
- Turn off desktop notifications and close unrelated tabs/windows.
- Hide account IDs, email, authorization headers, token values, invite codes,
  and receipt text in every frame.
- Review the final video from beginning to end before sharing; add captions and
  source references. No recording or screenshots are included in this draft.
