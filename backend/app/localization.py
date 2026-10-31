"""Shared locale normalization and recipient grouping helpers."""

SUPPORTED_LOCALES = frozenset({"vi", "en"})
DEFAULT_LOCALE = "vi"


def normalize_locale(value):
    return value if isinstance(value, str) and value in SUPPORTED_LOCALES else DEFAULT_LOCALE


def group_recipients_by_locale(recipients):
    groups = {"vi": [], "en": []}
    for recipient in recipients:
        if isinstance(recipient, str):
            email = recipient
            locale = DEFAULT_LOCALE
        else:
            email = recipient.get("email")
            locale = normalize_locale(recipient.get("preferred_locale"))
        if email:
            groups[locale].append(email)
    return {locale: emails for locale, emails in groups.items() if emails}
