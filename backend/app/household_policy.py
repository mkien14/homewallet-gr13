"""Shared production boundary for API, OCR, and scheduled jobs."""


def public_registration(config):
    return config.get("PRODUCTION_PUBLIC_REGISTRATION") is True


def household_admitted(config, household_id):
    if config.get("APP_ENV") != "production":
        return True
    # The retained household is never reopened by public registration.
    if type(household_id) is not int or household_id <= 1:
        return False
    return public_registration(config) or household_id in config.get("PRODUCTION_ALLOWED_HOUSEHOLD_IDS", set())
