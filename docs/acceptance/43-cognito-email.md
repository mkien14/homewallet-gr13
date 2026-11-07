# #43 — Cognito email locale acceptance (Chi)

Status: PREPARED / NOT RUN. Depends on reviewed and deployed #42. This document does not assert that #42 or #43 has passed on AWS.

## Contract to confirm with Kien, Thuc and Hoang

| Surface | Attribute / rule |
| --- | --- |
| Backend profile | preferred_locale; accepts vi/en |
| Cognito user | custom:preferred_locale; mutable String |
| Default / invalid value | vi |
| First signup email | Thuc supplies custom:preferred_locale in signup UserAttributes before Cognito sends verification |
| Later language change | UI coordinates backend profile and Cognito update; partial failure is shown and retried |
| Email template source | Stored Cognito attribute, not assumed ClientMetadata on every API |
| Sender / region | Existing verified homewallet26@gmail.com / ap-southeast-1 |
| Sandbox | Sender and all test recipients must be verified; do not change sandbox status |
| Money and business dates | VND / Asia/Ho_Chi_Minh; locale does not change business data |

Never use household, transaction or receipt data in auth email tests. Do not delete existing Cognito users to create signup fixtures. Hoang/Kien select the accounts and verified recipients. Code placeholders stay in template source; real codes and tokens never go into evidence.

## Draft terminology — pending Hoang review

| vi | en |
| --- | --- |
| Xác minh tài khoản | Verify your account |
| Gửi lại mã xác minh | New verification code |
| Đặt lại mật khẩu | Reset your password |
| Mã xác thực | Authentication code |
| Xác minh thông tin | Verify your details |
| Lời mời HomeWallet | HomeWallet invitation |

These strings reflect the proposed #42 handler, not an approved final glossary.

## Dev test matrix

All rows start NOT_RUN. Replace status only after executing the case; record expected/actual, sanitized evidence reference, UTC timestamp and deployed commit. Never mark an email pass based only on a unit test.

| ID | Locale | Case | Expected | Status |
| --- | --- | --- | --- | --- |
| CM01 | vi | New signup, then confirm | Vietnamese subject/body, received code confirms account | NOT_RUN |
| CM02 | en | New signup, then confirm | English subject/body, received code confirms account | NOT_RUN |
| CM03 | vi | Resend signup verification | Vietnamese, new code works | NOT_RUN |
| CM04 | en | Resend signup verification | English, new code works | NOT_RUN |
| CM05 | vi | Forgot password, then confirm reset | Vietnamese reset email; login with changed password works | NOT_RUN |
| CM06 | en | Forgot password, then confirm reset | English reset email; login with changed password works | NOT_RUN |
| CM07 | absent | Message for user without locale | Vietnamese fallback; existing accounts remain usable | NOT_RUN |
| CM08 | vi→en | Change backend and Cognito locale, then request message | Both stores consistent, subsequent message English | NOT_RUN |
| CM09 | en→vi | Change backend and Cognito locale, then request message | Both stores consistent, subsequent message Vietnamese | NOT_RUN |
| CM10 | both | One locale update destination fails | UI reports partial failure and retries; no false synchronized state | NOT_RUN |
| CM11 | both | SRP login, refresh, session persistence | Existing behavior preserved | NOT_RUN |
| CM12 | both | Hosted UI/PKCE login and callback | Existing entrypoint works; no cutover | NOT_RUN |
| CM13 | both | TOTP MFA challenge | Authenticator challenge works; no email MFA expected | NOT_RUN |
| CM14 | both | Review Lambda logs | No events, real codes, passwords or tokens | NOT_RUN |
| CM15 | both | Invitation if approved for testing | Both username and temporary-password placeholders replaced | NOT_RUN |
| CM16 | both | Verify a changed email if approved for testing | Correct locale and verification succeeds for verified sandbox recipient | NOT_RUN |

Invalid-locale fallback is verified locally by #42 handler tests; do not inject invalid profile values into shared dev simply to obtain an email. Record email MFA as N/A with TOTP configuration evidence and reviewer agreement, not PASS. ConfirmForgotPassword does not imply a separate second email.

## Deployment gates / handoff

1. #42 merged; plan reviewed, pool update in place, no callback/client regression.
2. Lambda/SES/log cost and apply approved separately from WAF allowance.
3. Kien applies from reviewed main; verify pool DEVELOPER email mode, Lambda trigger/invoke permission and locale schema together.
4. Check SPA client effective locale read/write permissions using the intended SRP SDK flow. If an explicit attribute list is needed, preserve existing permissions. OAuth tokens require appropriate Cognito scopes for self-service attribute APIs; do not assume PKCE scopes imply these permissions.
5. Hoang reviews glossary; Thuc supplies signup locale and error/retry UI; Kien owns backend preferred_locale persistence.
6. Run test matrix using approved verified recipients; redact evidence.
7. Report PASS/FAIL/N/A with owners. This email matrix alone does not establish whole-app #43 acceptance (jobs/reports/push/API/UI remain separate).
8. Auth cutover remains a separately reviewed change by Kien only after the complete #42–43 matrix passes.

## Rollback boundary

Keep Hosted UI/PKCE available. Review an email rollback that removes the custom trigger and restores COGNITO_DEFAULT together; never leave custom email responses attached to default email mode. Retain the added locale schema: custom attributes cannot simply be deleted. Do not replace or delete the pool.
