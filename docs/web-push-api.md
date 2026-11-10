# Web Push and in-app notification API (#26)

All endpoints below require the existing Cognito access token in `Authorization: Bearer <token>`. The API derives `user_id` from the token-backed user profile; clients must not send an owner or household ID.

## In-app notifications

### `GET /api/notifications?limit=50`

Returns the signed-in user's newest in-app notifications. `limit` defaults to 50 and must be from 1 to 100.

```json
{
  "items": [
    {
      "id": 41,
      "type": "budget_alert",
      "title": "Cảnh báo ngân sách",
      "body": "Một danh mục chi tiêu đã chạm ngưỡng thiết lập. Mở HomeWallet để xem chi tiết.",
      "deep_link": "/budgets",
      "created_at": "2026-10-31T10:20:00",
      "read_at": null,
      "read": false
    }
  ]
}
```

### `PATCH /api/notifications/{id}`

Marks a notification owned by the signed-in user as read. The operation is idempotent.

```json
{"read": true}
```

Returns `200 {"id":41,"read":true,"read_at":"..."}`. A notification belonging to another user is indistinguishable from a missing notification and returns `404 NOT_FOUND`.

## Push subscriptions

### `POST /api/push/subscriptions`

Store the browser's `PushSubscription.toJSON()` after the user explicitly grants notification permission. The API accepts either that object directly or wrapped as `{"subscription": ...}`. `user_id` and other extra properties are rejected.

```json
{
  "endpoint": "https://fcm.googleapis.com/fcm/send/example",
  "expirationTime": null,
  "keys": {
    "p256dh": "<base64url-public-key>",
    "auth": "<base64url-auth-secret>"
  }
}
```

The endpoint must use HTTPS on port 443 and a supported browser push service host (Google FCM, Mozilla Push, Apple Push, or Windows Push). Keys must decode to a 65-byte P-256 public key and a 16-byte auth secret. The endpoint is stored with a SHA-256 uniqueness key; registering the same browser again updates its existing row instead of duplicating it. The response contains only the subscription ID, never the endpoint or keys: new subscription `201`, existing subscription `200`. After reload, if the browser already has a subscription, the UI may POST that existing object again to reconcile it and recover the server-side ID without prompting again.

### `DELETE /api/push/subscriptions/{id}`

Unsubscribes the current user-owned browser subscription and returns `204`. Repeating the request is safe. The frontend should also call `PushSubscription.unsubscribe()` after the API request succeeds.

## Job delivery and privacy

Recurring bill reminders create `recurring_bill_reminder` in-app notifications and budget thresholds create `budget_alert` notifications. Both are idempotent per event and current household member. Web Push is sent only to users with an active subscription. Existing SES email behavior remains in place; weekly reports continue to use SES only.

The encrypted Web Push data is limited to:

```json
{"event_type":"budget_alert","deep_link":"/budgets"}
```

It must not contain an amount, member email, receipt text, or other household data. The in-app API returns generic copy in the user's `preferred_locale` and the internal link so the authenticated React app can display details after the user opens the page. Expired provider responses (`404`/`410`) mark a subscription `EXPIRED` and clear its endpoint and keys. A failure on one browser does not stop delivery to other browsers or fail the scheduled job.

## VAPID deployment configuration

- `VAPID_PRIVATE_KEY`: server-side VAPID private key as base64url-encoded DER, injected into the scheduled `hw-jobs` ECS task from Secrets Manager. Convert PEM text to DER before storing this environment-variable value: `pywebpush` interprets an inline string as an encoded key, not as PEM contents. Do not commit it or put it in any `VITE_*` variable.
- `VAPID_CLAIMS_SUB`: VAPID subject such as `mailto:homewallet26@gmail.com`. If omitted, backend config derives it from `SES_FROM_ADDRESS`.
- `VITE_VAPID_PUBLIC_KEY`: public key for the React app, configured separately by the UI branch. It is public and must match the private key above.

Terraform must grant `secretsmanager:GetSecretValue` only to the task role used by `hw-jobs` and inject the secret into that task. The API and receipt worker do not need the private key. Until the job-task secret and a matching public key are configured, in-app notifications still work and the existing SES path continues; Web Push is skipped.

Apply database migration `003_web_push_notifications.sql` before deploying the API or scheduled job code that uses these tables.
