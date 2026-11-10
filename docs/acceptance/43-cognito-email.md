# #43 — Cognito email locale acceptance (Chi)

Status as of 2026-11-10: **#43 PARTIAL**. The user explicitly approved SES
production-access submission, superseding the earlier shared-account sandbox
decision. AWS granted access in `ap-southeast-1` (case `179429386000476`);
`ProductionAccessEnabled=true`. Cognito email is no longer blocked by sandbox.

An isolated pool/client now exercises the deployed Custom Message Lambda.
Labeled SES simulator requests passed for signup/resend/forgot, fallback,
locale changes and invitation. Controlled inbox/content/code evidence remains
pending. CM16 needs a second controlled address. CM14 PASS is scoped to the
controlled email-trigger window: 11 invocations, 33 lifecycle log lines, no
application payload lines. Six temporary simulator users were deleted.

Three one-time Scheduler schedules ran unmodified `hw-jobs:3` CLIs against two
isolated schemas: all three jobs succeeded in vi/en, six SES simulator sends
completed and four pushes were provider-accepted. Repeated keys skipped without
duplicate sends. Temporary schedules, schemas and schema grants were removed;
the original recurring schedules remain DISABLED. The user confirmed receipt
of a new job notification in the 14:08–14:10 Asia/Bangkok window on 2026-11-10:
job-push send/receive smoke PASS, without claiming observation of every push.
Controlled inbox/code acceptance remains pending. See [delivery report](43-delivery-20261110.md).

#42 remains accepted for live Hosted UI/PKCE locale sync. The active pool uses
SES `DEVELOPER`, the verified sender and `custom:preferred_locale`. Its client,
auth entrypoints and users were not modified for the isolated email test.

After the approved glossary was merged, the current local Lambda handler suite
passed 4/4 tests on 2026-11-09 using `python -m unittest -v test_handler.py`
from `infra/lambda/cognito_custom_message`. It covers all configured trigger
subjects in both locales, missing/invalid-locale fallback, code/username
placeholders, and no stdout/stderr. It did not invoke Cognito or send email.
The earlier direct Lambda invocation smoke used fake placeholders and likewise
did not send email.

An isolated Cognito user created with `MessageAction=SUPPRESS` also signed in
through the SPA client using SRP, updated `custom:preferred_locale=en`, and read
back `en`; the user was deleted immediately. This confirms the current app
client's effective locale read/write permissions for that flow, without
testing signup email delivery.

The frontend integration is deployed to the dev CloudFront site. The fresh
PKCE session and live locale changes were accepted using a controlled dev
account. Sanitized evidence from the user's browser screenshots was reviewed
on 2026-11-09; screenshots are not committed because they expose account and
household details. A previously issued PKCE session must sign in again to
receive the new scope. The approved glossary below is used by the Lambda
handler.

## Agreed locale and email contract

| Surface | Attribute / rule |
| --- | --- |
| Backend profile | preferred_locale; accepts vi/en |
| Cognito user | custom:preferred_locale; mutable String |
| Default / invalid value | vi |
| Locale source | Cognito `custom:preferred_locale` is canonical; backend profile mirrors it |
| First signup email | React client supplies custom:preferred_locale in signup UserAttributes before Cognito sends verification |
| Later language change | UI updates Cognito and backend profile; partial failure is shown and retried |
| Email template source | Stored Cognito attribute, not assumed ClientMetadata on every API |
| Sender / region | Existing verified homewallet26@gmail.com / ap-southeast-1 |
| SES access | User approved production access on 2026-11-10; AWS GRANTED in Singapore. Use the isolated test pool and controlled recipients for inbox/code acceptance |
| Money and business dates | VND / Asia/Ho_Chi_Minh; locale does not change business data |

Never use household, transaction or receipt data in auth email tests. Do not delete existing Cognito users to create signup fixtures. Hoang/Kien select the accounts and verified recipients. Code placeholders stay in template source; real codes and tokens never go into evidence.

## Approved email terminology (Kiên, 09/11/2026)

| vi | en |
| --- | --- |
| Xác minh tài khoản | Verify your account |
| Mã xác minh mới | New verification code |
| Đặt lại mật khẩu | Reset your password |
| Mã xác thực | Authentication code |
| Xác minh thông tin tài khoản | Verify your account information |
| Lời mời HomeWallet | HomeWallet invitation |

Use these exact subject pairs in #42/#43 evidence. Hoàng can flag a product terminology conflict during review.

## Dev test matrix

All rows start NOT_RUN. Replace status only after executing the case; record expected/actual, sanitized evidence reference, UTC timestamp and deployed commit. Never mark an email pass based only on a unit test.

| ID | Locale | Case | Expected | Status |
| --- | --- | --- | --- | --- |
| CM01 | vi | New signup, then confirm | Vietnamese subject/body, received code confirms account | PARTIAL — labeled simulator send accepted; controlled inbox and received code pending |
| CM02 | en | New signup, then confirm | English subject/body, received code confirms account | PARTIAL — labeled simulator send accepted; controlled inbox and received code pending |
| CM03 | vi | Resend signup verification | Vietnamese, new code works | PARTIAL — labeled simulator send accepted; controlled inbox and received code pending |
| CM04 | en | Resend signup verification | English, new code works | PARTIAL — labeled simulator send accepted; controlled inbox and received code pending |
| CM05 | vi | Forgot password, then confirm reset | Vietnamese reset email; login with changed password works | PARTIAL — labeled simulator send accepted; controlled inbox and received code pending |
| CM06 | en | Forgot password, then confirm reset | English reset email; login with changed password works | PARTIAL — labeled simulator send accepted; controlled inbox and received code pending |
| CM07 | absent | Message for user without locale | Vietnamese fallback; existing accounts remain usable | PARTIAL — local fallback and simulator request accepted; inbox content pending |
| CM08 | vi→en | Change backend and Cognito locale, then request message | Both stores consistent, subsequent message English | PARTIAL — stores verified; simulator request accepted, inbox content/code pending |
| CM09 | en→vi | Change backend and Cognito locale, then request message | Both stores consistent, subsequent message Vietnamese | PARTIAL — stores verified; simulator request accepted, inbox content/code pending |
| CM10 | both | One locale update destination fails | UI reports partial failure and retries; no false synchronized state | PASS — simulated Cognito request blocking showed the partial-save alert; after unblocking, retry cleared the alert, Cognito returned 200, and `/api/me` confirmed `preferred_locale=en` |
| CM11 | both | SRP login, refresh, session persistence | Existing behavior preserved | PASS — after access-token expiry, Cognito `GetTokensFromRefreshToken` returned 200; the app remained signed in and `GET /api/me` returned 200 |
| CM12 | both | Hosted UI/PKCE login and callback | Existing entrypoint works; no cutover | PASS — fresh login/callback verified |
| CM13 | both | TOTP MFA challenge | Authenticator challenge works; no email MFA expected | N/A — user approved N/A; pool is OPTIONAL and software-token MFA is not configured |
| CM14 | both | Review Lambda logs | No events, real codes, passwords or tokens | PASS — controlled Cognito email-request window on 2026-11-10: 11 invocations, 33 lifecycle-only lines, zero application payload lines; no per-trigger payload logging |
| CM15 | both | Invitation if approved for testing | Both username and temporary-password placeholders replaced | PARTIAL — invitation request accepted; inbox placeholders and temporary-password login pending |
| CM16 | both | Verify a changed email if approved for testing | Correct locale and verification succeeds for controlled recipient | NOT_RUN — second controlled recipient and received code required |

The locale-store portions of CM08 and CM09 are supported by the live browser
evidence: changing each locale caused a successful Cognito attribute update and
the matching locale in `/api/me`. Isolated simulator requests now pass; controlled
inbox/content/code checks remain pending.
CM10 was exercised in the deployed browser on 2026-11-09 (Asia/Bangkok):
DevTools Network request blocking was enabled for the Cognito IdP domain; the UI
showed "Your language was saved only in part. Please try again." After the rule
was unchecked and retry was clicked, the alert disappeared and the selected
Cognito request showed HTTP 200; the user then confirmed that `/api/me` had
`preferred_locale=en`, matching the selected English locale. This is a simulated
client-side destination failure, not an AWS service failure. Evidence is the
user's browser screenshots and confirmation; no tokens or request headers are
recorded here.
For CM11, the user confirmed the app loaded and `GET /api/me` returned HTTP 200;
after reloading the same tab, the session remained active and `GET /api/me`
returned HTTP 200 again. After the configured 60-minute access-token lifetime,
the browser issued Cognito `GetTokensFromRefreshToken` and received HTTP 200; the
app remained signed in and `GET /api/me` returned HTTP 200. This verifies refresh
and same-tab session persistence. Read-only inspection of the SPA app client
showed a 30-day refresh-token lifetime.
CM13 was recorded N/A with the user's approval after read-only pool inspection
returned `MfaConfiguration=OPTIONAL` and no configured
`SoftwareTokenMfaConfiguration`.
For CM14, read-only CloudWatch review of `/aws/lambda/homewallet-dev-cognito-custom-message`
found 10 invocations from 2026-11-07 through 2026-11-09 UTC. All 33 log events
were Lambda platform `INIT_START`, `START`, `END`, or `REPORT` messages; there
were no application payload log lines, email/code/password/token/authorization
pattern hits, or error/exception lines. The logs do not identify whether any
invocation was caused by a real Cognito email event, so real-event log review
remains unverified. The shared account's
`ProductionAccessEnabled=false` was also verified read-only on that date.

Web Push prerequisites were deployed to dev on 2026-11-10: a VAPID key pair
was generated, the private key is held in Secrets Manager and injected into API
task definition revision 21, and the frontend was rebuilt with the public key.
CloudFront invalidation completed and `/api/ping` returned HTTP 200 after the
API rollout. The user's browser showed `GET /api/notifications?limit=50`
returning HTTP 200 and no notifications; PATCH was skipped.

Browser evidence supplied on 2026-11-10 (Asia/Bangkok) confirms the following
Web Push subscription behavior on the deployed `/notifications` page. Times
below are the HTTP response `Date` values, in UTC; these are separate observed
requests, not a claim that creation preceded reconciliation in the captured log.

| Case | Observed HTTP result | Response Date (UTC) | X-Request-Id | UI evidence | Status |
| --- | --- | --- | --- | --- | --- |
| Reconcile an existing browser subscription | `POST /api/push/subscriptions` → `200 OK` | 2026-11-09 17:34:22 | `fc64690b-fa7a-4d87-a0be-d9fc5e60ed09` | Permission allowed; Web Push enabled | PASS |
| Create a browser subscription | `POST /api/push/subscriptions` → `201 Created` | 2026-11-09 17:35:12 | `36c8b09a-b1eb-45af-a8b6-2afaefad6f11` | Web Push enabled; disable control available | PASS |
| Remove the current browser subscription | `DELETE /api/push/subscriptions/{id}` → `204 No Content` | 2026-11-09 17:35:50 | `7a880440-0e7f-4018-8be6-4e3f5fdc867f` | Web Push disabled; enable control available | PASS |

Follow-up response-header screenshots supplied on 2026-11-10 at 00:45
(Asia/Bangkok) show all three `X-Request-Id` values above. Each was matched to
the same selected request in the earlier status screenshots. Subscription
creation, reconciliation, and removal are accepted. Browser permission remains
allowed after disabling the subscription, which is consistent with the UI.
The original in-app list was empty. Mark-as-read API acceptance subsequently
passed with the isolated fixture below; the controlled user's browser read/click
step also passed for test notification `41`. A follow-up screenshot confirms
reload preserves its read state. Subscription management and the targeted delivery probe below are
accepted from provider and device evidence. Screenshots were reviewed in the
conversation and are not committed. No subscription endpoint, subscription
keys, token, or VAPID key material is recorded here.

### Targeted Web Push delivery probe — 2026-11-10

The user supplied active subscription ID `6` and browser `/api/me` evidence
showing user ID `16`. A one-off ECS task based on `hw-api:21` executed
[scripts/push-delivery-smoke.py](../../scripts/push-delivery-smoke.py). Its
parameterized query required `id=6`, `user_id=16`, and `status='ACTIVE'` before
selecting exactly one delivery target. It called the deployed `pywebpush`
library directly with the same generic payload shape used by the job helper:
`{"event_type":"budget_alert","deep_link":"/notifications"}`. It did not run
a scheduled job, send SES email, insert an in-app notification, or write to the
database. Scheduled job integration remains NOT_RUN.

- Accepted task: `arn:aws:ecs:ap-southeast-1:179923444714:task/homewallet/ea095c3894ce4d3fb354f316dc1924a8`.
- CloudWatch log group/stream: `/ecs/hw-api` / `api/api/ea095c3894ce4d3fb354f316dc1924a8`.
- `PUSH_TARGET_VALIDATED`: 2026-11-09T18:02:32.468110Z, one target.
- `PUSH_PROVIDER_ACCEPTED`: 2026-11-09T18:02:32.690648Z (2026-11-10 01:02:32 Asia/Bangkok), provider HTTP `201`.
- Container exit code: `0`.
- Probe source SHA-256: `2a180c2e44a1cb6b2350b174d6d0b4884339a9d454973d1c241bc1918a0b2f64`.
- Device notification display and manual click-through evidence: PASS — user supplied the Windows notification screenshot and the follow-up browser screenshot at the expected `/notifications` destination.

The device screenshot supplied on 2026-11-10 shows the notification in Windows
Notification Center through Microsoft Edge from the deployed CloudFront origin.
It displays the Vietnamese title "Cảnh báo ngân sách" and body "Mở HomeWallet
để xem chi tiết.", with notification time 01:02 and screenshot clock 01:03
(Asia/Bangkok), consistent with the provider acceptance time. In response to
the requested notification-click check, the user also supplied a browser
screenshot at `https://daoedidcrnf1f.cloudfront.net/notifications`. This is
manual device/display and destination evidence; no click-event trace was
collected. The in-app list remains empty because this probe did not insert an
in-app notification. The targeted Web Push send/receive smoke is PASS; the
scheduled job flow remains separate.

The first attempt, task `07877df93b89428284568e167492ebed`, validated the
same target but failed at key decoding with `ValueError` at
2026-11-09T18:00:09.621740Z, before obtaining a provider HTTP response. The
secret held inline PEM, which the library's string-key path does not parse as
PEM. The existing P-256 key was converted in memory to base64url-encoded PKCS8
DER and saved as the current Secrets Manager value after verifying that its
derived public key matched the frontend. The successful retry loaded that
value at task startup. No private key was printed or written to a local file.
The existing long-running API task was not restarted by this probe; future
consumers must load the current secret value. This does not establish that
the scheduled jobs have received their required VAPID configuration. A later
jobs configuration deployment and probe is recorded below.

### Deployed notification API and bounded jobs/reports runtime — 2026-11-10

See [43-runtime-20261110.md](43-runtime-20261110.md) and the
[successful runtime artifact](43-runtime-fixture-20261110-retry.json).
All 20 HTTP cases passed with request IDs: authenticated notification lists in
both locales, mark-as-read, repeat-call idempotency, persisted read state,
invalid-input validation, missing-token rejection, and cross-user denial.
Temporary Cognito users used the existing dev client's password flow; this
does not replace the SPA SRP/PKCE or signup-email cases.

Six checks of the deployed jobs/reports code passed on an isolated household
fixture: confirmed-only weekly totals and boundaries, locale-specific report
rendering and duplicate suppression, reminder due dates and duplicate
suppression, budget 80/100 thresholds, six localized in-app notifications, and
four successful namespaced job runs. Household/data selectors were scoped by
the harness; eight email calls were intercepted in memory. No SES email,
Web Push, or Scheduler invocation was performed by this fixture. The two
temporary Cognito users and all isolated household/database fixture rows were
removed. The initial permissions-related fixture setup/cleanup failure was
recovered using the dedicated bootstrap role; verification found the push
grants already sufficient and no grants were changed.

Controlled UI fixture: user `16`, notification `41`, title
"Thông báo nghiệm thu #43". User-supplied screenshots confirm the browser
read/click step **PASS**: `PATCH /api/notifications/41` returned `200 OK`, with
`id=41`, `read=true`, and `read_at=2026-11-10T06:44:17`. HTTP Date is
`Tue, 10 Nov 2026 06:44:17 GMT` (13:44:17 Asia/Bangkok); response
`X-Request-Id=9389bdb0-83bc-40ee-b129-1e3bbf92de34`. The UI shows the read marker.
A subsequent screenshot shows GET after PATCH with the read marker retained
after reload: browser persistence is also PASS.
Notification `41` is retained pending agreed cleanup. Screenshots were reviewed
in the conversation and are not committed.

The jobs task's missing VAPID secret reference was added after reviewing the
saved Terraform plan. Apply created `hw-jobs:3` and updated only its scoped
Scheduler policy/target references; all three schedules remain DISABLED.
A one-off configuration probe using the jobs task role and Scheduler network
confirmed key loading/parsing, configured subject, and DB read access with exit
code 0. See [jobs configuration evidence](43-jobs-vapid-configuration-20261110.json).
The subsequent [one-time Scheduler delivery run](43-delivery-20261110.md) passed
CLI execution, simulator SES sends and push provider acceptance. Job-push device
receipt is now user-confirmed PASS for the send/receive smoke. Controlled
inbox/code acceptance remains pending; sandbox is no longer a block.

Local regression checks on 2026-11-09: Lambda handler 4 passed; frontend lint
passed, 72 frontend tests passed, and production build succeeded (Vite emitted
a non-blocking large-chunk warning); backend suite 161 passed and 50 skipped
because local MySQL was unavailable. These checks do not replace the live
email, database-backed, or browser acceptance cases above.

Invalid-locale fallback is verified locally by #42 handler tests; do not inject invalid profile values into shared dev simply to obtain an email. Record email MFA as N/A with TOTP configuration evidence and reviewer agreement, not PASS. ConfirmForgotPassword does not imply a separate second email.

## Deployment gates / handoff

1. #42 is deployed and accepted for fresh Hosted UI/PKCE locale synchronization; retain Hosted UI and SRP entrypoints.
2. SES production access is GRANTED under the user-approved decision change. Use the isolated pool and controlled recipients for inbox/code acceptance.
3. API/UI, Scheduler/CLI/provider checks and user-confirmed job-push receipt have their own evidence. Local tests alone do not establish runtime acceptance.
4. Complete the interactive controlled-mailbox cases, then remove the test pool and its scoped Lambda permission. Simulator acceptance does not establish received-code E2E.
5. Report PASS/PARTIAL/BLOCKED/N/A with owners and sanitized evidence. This email matrix alone does not establish whole-app #43 acceptance.
6. Auth cutover remains a separately reviewed change by Kien only after required #42–43 acceptance is complete.

## Rollback boundary

Keep Hosted UI/PKCE available. Review an email rollback that removes the custom trigger and restores COGNITO_DEFAULT together; never leave custom email responses attached to default email mode. Retain the added locale schema: custom attributes cannot simply be deleted. Do not replace or delete the pool.
