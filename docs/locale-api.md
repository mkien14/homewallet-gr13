# Preferred locale profile API (#43)

The supported UI locales are `vi` and `en`; the default for existing and new users is `vi`. Locale changes presentation only. Monetary values remain VND, report periods continue to use `Asia/Ho_Chi_Minh`, and user-entered names/category labels are kept as stored.

## Read the current locale

`GET /api/me` returns the preferred locale as part of the authenticated user profile:

```json
{
  "user": {
    "id": 12,
    "email": "user@example.test",
    "display_name": "user",
    "preferred_locale": "vi"
  },
  "household": null
}
```

## Update the current locale

`PATCH /api/me` accepts only the locale field. The API derives the user from the verified Cognito access token; clients cannot select another profile.

```json
{"preferred_locale":"en"}
```

The response has the same shape as `GET /api/me` with the updated `user.preferred_locale`. A missing field, unsupported locale, or additional profile field returns `422` with the existing `VALIDATION` error code.

At sign-up, the React client sends Cognito's `custom:preferred_locale` attribute. After sign-in, and whenever the user changes language, it updates that Cognito attribute through Cognito and calls `PATCH /api/me` to synchronize the application profile. If the application profile is created before the client syncs, its default is Vietnamese.

## Locale in scheduled messages

Recurring bill reminders, budget alert emails, and weekly report emails are grouped by each member's `preferred_locale` and sent with that group's language. In-app reminder/alert copy is stored in each member's locale. Web Push continues to contain only the event type and internal deep link; the React/service-worker layer chooses display text from the user's locale.

English labels do not translate names entered by users. Both report templates retain the original VND amounts and the existing local date period. No transaction or budget data is sent to an external translation service.

Apply migration `004_user_preferred_locale.sql` before deploying the API or scheduled jobs from this branch.
