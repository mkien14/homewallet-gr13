# #42 Cognito SRP / Custom Message — dev review

## Scope and current status

Code and local tests are prepared. No apply, live auth test, or email delivery test was performed as part of this change. Existing OAuth code/PKCE, SRP/refresh, token settings, URLs and TOTP MFA are preserved. The handler includes the VI–EN foundation needed by #43; this does not establish end-to-end locale acceptance.

SES sender `homewallet26@gmail.com` was verified in ap-southeast-1; sending is enabled but the account remains in sandbox. Every test recipient must also be SES-verified. Do not request production access or change sender as part of this PR.

## Infrastructure

- Add mutable optional String schema `preferred_locale` (SDK name `custom:preferred_locale`). Two-character constraint does not enforce vi/en; UI/API must validate the enum, and handler falls back to vi.
- Use SES DEVELOPER email configuration with the existing verified identity; no new SES identity or SES stored template.
- Add Python 3.12 Custom Message Lambda, 14-day log group, execution role with log-stream permissions only, and invoke permission restricted to the pool/account.
- Zip only handler.py using the archive provider. Generated zip stays inside ignored `.terraform/`.
- Lambda returns email content to Cognito and never calls SES directly or logs events.
- Cognito may create its email service-linked role when configuring DEVELOPER; the apply principal needs the corresponding permission if that role does not exist. Do not add broad SES permissions to the Lambda as a workaround.

No explicit app-client read/write attribute list is introduced in this change. Verify the existing client's effective permissions after schema addition, including custom:preferred_locale; preserve all existing permissions if an explicit list becomes necessary.

## Local checks

```bash
python -B -m unittest discover -s infra/lambda/cognito_custom_message -p 'test_*.py' -v
terraform fmt -check -recursive infra
terraform -chdir=infra/envs/dev validate
git diff --check
```

Recorded plan on main baseline 877f56e plus this change: 6 add, 2 change, 0 destroy. Five added resources and one pool update belong to #42; one Web ACL and one CloudFront update belong to pending #31. Pool is updated in place and SPA client has no planned change. Replan after merge and immediately before deployment approval; do not treat this mixed plan as authorization to deploy #31.

Lambda, logs and SES costs need separate review; the WAF USD 10/month allowance does not cover this work. No auth UI cutover is included.

## Dev acceptance after separately approved deployment

Coordinate test accounts with Kien/Thuc/Hoang. Do not delete an existing user to recreate a signup case. Do not put passwords, tokens or real codes in screenshots, CLI arguments or logs.

| Case | Required result |
| --- | --- |
| Sign up with vi/en attribute | First verification email uses selected locale; confirmation works |
| Resend code | Subject/body use stored locale; placeholder replaced by Cognito |
| Forgot/reset password | Correct locale; reset and subsequent login succeed |
| Missing/invalid locale | Vietnamese fallback |
| Change locale | SDK update succeeds; subsequent message uses new value |
| Admin invitation, if tested | Username and temporary-password placeholders both replaced |
| TOTP MFA | Existing challenge works in both UI locales; no email-MFA claim |
| SRP/refresh/session | Existing sessions and refresh behavior remain valid |
| Hosted UI/PKCE | Existing login and callback still work |
| Log review | No event, password, code or token output |

The frontend signup and profile synchronization implementation is prepared on `feat/42-43-cognito-locale-sync` and awaits review, deployment and live acceptance. Apply the SPA client's additional self-service OAuth scope before deploying the frontend build, then sign in again for PKCE tests. The email glossary is approved in `docs/acceptance/43-cognito-email.md`. Stable API errors, jobs/reports/push localization and the remaining #43 acceptance work stay with the group. Test both locales using verified recipients before declaring completion.

## Rollback

The custom schema addition cannot simply be removed or undone; retain it during rollback. Review any future schema diff carefully and never replace the pool.

For an email regression, Kien prepares a reviewed Terraform change that detaches the custom_message trigger and restores the former COGNITO_DEFAULT email configuration together. Never leave a trigger returning custom email content attached to a COGNITO_DEFAULT pool. Keep Hosted UI/PKCE available, check signup/reset delivery after rollback, and only remove Lambda resources after detaching the trigger. Preserve Cognito users and existing attributes.
