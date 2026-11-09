# D4 / #36 — Evidence and status

Updated: 2026-11-09 (Asia/Saigon). Owner: Hoàng. Reviewer and load monitor:
Kiên; Chi can assist monitoring.

This report separates Hoàng's earlier AC3 run from Kiên's independent dev run
recorded in PR #91. It does not claim that the runs used the same users,
fixtures, or deployment. The independent AC3 baseline and read-load evidence is
merged in [PR #91](https://github.com/mkien14/homewallet-gr13/pull/91), with
the run details in [`36-d4-kien-run-20261109.md`](36-d4-kien-run-20261109.md)
and its sanitized JSON companion.

## Status

| Area | Status | Evidence and remaining work |
| --- | --- | --- |
| AC3 baseline cases | PASS within the four recorded checks; Hoang's request IDs unavailable | Hoang's access log matched the four calls, but neither the script nor access log exposed request IDs. Kien's independent baseline run and its request IDs are documented in PR #91. |
| Member authorization | PASS in the supplied live dev evidence | Kien-provided UI/Console/Network evidence confirms `/api/me` role `member`, `GET /api/households/12/members` = 200, and `POST /api/households/12/invite-code` = 403. Request IDs are recorded below. The new Cognito Member account remains a fixture and must not be exposed by email. |
| Read-only load | PASS within measured scope | Kien's PR #91 run: max 5 clients, dashboard GET only, 279/279 HTTP 200, p50 133.62 ms, p95 339.11 ms, no timeout/network error, and no early stop. No team p95 SLA was set. |
| OCR / D3 | PARTIAL / BLOCKED | Both original pilot report/lock pairs were found locally. Neither provider produced a schema-valid prediction; no OCR accuracy comparison is available. No rerun or expansion is authorized. |
| Hoang run logs and fixtures | Server-side log review recorded; receipt 28 disposition pending | Admin reviewed `/ecs/hw-api` and `/ecs/hw-worker`; no sensitive patterns were found in those logs or the two PR #91 artifacts. Receipt 28 belongs to household 12 and is `UPLOADING`; its origin and team-approved handling remain to be established. Hoang's local terminal/capture was outside the review. |
| Overall D4 / #36 | CLOSED by team decision (2026-11-09) | AC3 baseline, Member authorization, and bounded read load have evidence. The team has decided to close #36 with the D3 limitation documented. This is not an OCR success or model-comparison claim. No separate D3 follow-up issue link was provided for this report. Receipt 28 handling and local terminal review remain recorded limitations, not resolved actions. |

## Hoàng's AC3 run

- Date/time: 2026-11-08, approximately 23:17 ICT, matched by admin to access
  logs in the 23:16:30–23:18:30 ICT window.
- Environment: dev CloudFront endpoint `https://daoedidcrnf1f.cloudfront.net`.
- Evidence source: PowerShell output provided by Hoàng in the conversation;
  not independently captured from the workstation.
- Deployed task definition, image digest, and commit at execution time: not
  recorded. Do not assume they match either Kiên's run or an earlier handoff
  snapshot.
- The two dedicated test accounts both logged in successfully. User names,
  emails, passwords, and access tokens are intentionally omitted.
- `GET /api/ping` returned `{"message":"pong"}`.

| Check | Expected | Observed |
| --- | --- | --- |
| `GET /api/me` without token | 401 | PASS |
| User B reads household A members | 404 | PASS |
| User B reads household A receipt | 404 | PASS |
| User A reads own household members | 200 | PASS |

The script printed `AC3 verification PASSED`. Admin identified household 12
(`Hộ A`, owned by `d4-hoang-20261108.test1`) and household 13 (owned by
`d4-hoang-20261108.test2`); receipt 28 belongs to household 12 and remains in
`UPLOADING`. These fixture IDs are from admin's lookup, not from the script.
The access log matched all four calls, but neither source contains
`X-Request-Id`; record request IDs as **not retrievable**, not as guessed
values. Preserve receipt 28 until this report is recorded and the cleanup
method is confirmed. Do not rerun the script or delete by guess.

These four cases do not test a member role, token expiry, or every authorization
path. The live Member checks are separate evidence and are recorded in the
Member section below. Neither evidence set covers every authorization path.

## Read-only load evidence from PR #91

Kiên's separate run is documented in
[`36-d4-kien-run-20261109.md`](36-d4-kien-run-20261109.md). It used API task
`hw-api:20` and worker task `hw-worker:3`; its report records the serving image
and run configuration. The run used at most five clients for a 120-second
request window, making only `GET /api/dashboard?period=2026-11`; measured wall
time including shutdown/queue check was 122.24 seconds.

- 279/279 responses were HTTP 200; there were no 5xx responses, network errors,
  timeouts, or early stop.
- Client latency: p50 133.62 ms, p95 339.11 ms, mean 163.31 ms, n=279.
- Main SQS visible/in-flight stayed 0/0. DLQ visible/in-flight stayed 1/0;
  the one visible DLQ message predated the test.
- API CPU average was 9.2943% and 7.5004% during the two measured minutes;
  API memory average was 18.2617% in both. Worker CPU was 0%; worker memory
  average was 7.7148%.
- CloudWatch ALB/target 5xx metrics had no datapoints in the queried window;
  absence is not interpreted as a measured zero. The report also records the
  `homewallet-dev-alb-5xx` alarm as OK and zero `ERROR` log events in the
  expanded query window.

This supports a bounded read-load result only. Household data was empty and
dashboard caching may affect latency. No p95 acceptance threshold was set, so
these measurements do not establish an SLA or OCR/LLM capacity.

## OCR / D3 artifact reconciliation

The two reports and one-shot locks are present locally under ignored
`ocr-lab/out/`; they were not added to Git. These summaries are read from those
artifacts and agree with [`bedrock-benchmark.md`](../bedrock-benchmark.md).
Raw model/receipt text is not included here.

| Pilot | Gemini | Bedrock | Valid-prediction accuracy |
| --- | --- | --- | --- |
| Original pilot, 2026-11-07, `021`–`030` | 7 attempts: 6 responses, all 6 schema-invalid; 1 request rejected with 429; 0 retries. Usage 7,200 input / 41 output tokens; estimated cost USD 0.005554. | 0 attempts. | No schema-valid predictions; accuracy is not measurable. |
| Approved v2 pilot, 2026-11-08, `021`–`030` | 3 attempts: 2 responses with invalid JSON, 1 call error (503), 7 skipped; 0 retries. Usage 2,396 input / 9 output tokens; estimated cost USD 0.001831. | 1 attempt failed with `AccessDeniedException`, 9 skipped; 0 retries and no usage returned. | No schema-valid predictions from either provider; accuracy is not measurable. The report's 0/10 end-to-end flags count errors/skips as incorrect and are not OCR accuracy on valid outputs. |

Both runs used the approved ten-image pilot only. Do not rerun, send more
images, add Textract, or infer a 42-image result. Keep OCR Partial/Blocked;
the artifacts support a record of attempts and failures, not provider ranking.

## Member authorization evidence

Kien supplied UI, Console, and Network evidence from the dev session on
2026-11-09. The response headers timestamp the two authorization requests at
05:40:29 GMT (12:40:29 Asia/Saigon) through
`https://daoedidcrnf1f.cloudfront.net`. This is Kien-provided evidence; it is
not attributed to Hoang's earlier AC3 run or to the PR #91 baseline run. Only
sanitized status and request-ID values are transcribed here; raw captures,
email, credentials, token, and invite code are not included.

| Member check | Expected | Actual | X-Request-Id | Result |
| --- | ---: | ---: | --- | --- |
| `GET /api/me` confirms household 12, role `member` | 200 | 200 | Full ID not captured | PASS |
| `GET /api/households/12/members` | 200 | 200 | `18956e89-80aa-46ae-bb5a-4281d7ef8461` | PASS |
| `POST /api/households/12/invite-code` | 403 | 403 | `c1837d20-3fa5-41d2-893d-6f374ed9cf97` | PASS |

The 403 is the expected authorization denial. There is no evidence that the
invite code changed. The Member Cognito account remains a test fixture in
household 12; its personal email is intentionally omitted. Do not reuse test2
as the Member identity: test2 owns household 13.

## Logs, fixture inventory, and closure

- Admin reviewed Hoàng's server logs for 2026-11-08 23:16:30–23:18:30 ICT:
  26 `/ecs/hw-api` events and no Authorization/Bearer/JWT strings, secret names,
  personal emails, or receipt-text indicators; `/ecs/hw-worker` had no events.
  The two PR #91 artifacts were also checked for these patterns. This is a
  sanitized review summary; raw logs are not included here.
- The server-side review does not cover Hoàng's terminal/local capture.
  `New-TestUsers` may print a password. Do not attach terminal captures or logs
  until they have been checked and redacted for Authorization, secrets, email,
  and receipt text.

| Fixture | Last known state | Handling |
| --- | --- | --- |
| Household 12 | Exists; owner is Hoàng's test1 account | Retain for the Member evidence; do not delete by assumption. |
| Household 13 | Exists; owner is Hoàng's test2 account | Not the Member fixture; no cleanup evidence recorded here. |
| Receipt 28 | Belongs to household 12; `UPLOADING`; source/origin not established | Keep unchanged until Hoàng identifies its origin and the team agrees on handling. |
| New Cognito Member account | Joined household 12; account remains a test fixture | Email omitted. Track for cleanup; no deletion evidence recorded. |
| Households 14–15 and receipt 29 | Cleaned according to the PR #91 record | This is Kiên's run and cleanup; do not attribute it to Hoàng. |

The old Hoàng script did not record request IDs for its four baseline cases; the
admin could match those calls in access logs but could not retrieve the IDs.
Record them as **not retrievable**, not as guessed values. The Member request
IDs above belong to Kiên-provided evidence, and PR #91 IDs/fixtures belong only
to Kiên's run.

The group confirmed #36 closed on 2026-11-09. This records the team's closure
decision; it does not change the D3 result from `PARTIAL / BLOCKED`, establish
valid OCR accuracy, or identify a winning model. No separate D3 follow-up issue
ID/link was supplied. If the team opened one, add its link here. Receipt 28's
origin/disposition and the local terminal/capture review remain limitations in
the evidence record; closure does not imply those actions were completed.
