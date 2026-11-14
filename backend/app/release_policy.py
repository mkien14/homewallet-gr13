"""Validate security-critical settings before a production process serves traffic."""
import re
from .household_policy import public_registration


def validate_release_config(config):
    if config.get("APP_ENV") != "production":
        return
    approved = config.get("PRODUCTION_ALLOWED_HOUSEHOLD_IDS", set())
    if (not approved and not public_registration(config)) or any(type(value) is not int or value <= 1 for value in approved):
        raise RuntimeError("Production requires explicit approved household IDs; retained household 1 is excluded")
    missing = [key for key in (
        "COGNITO_ISSUER", "COGNITO_JWKS_URI", "COGNITO_CLIENT_IDS", "DB_SSL_CA",
        "REDIS_HOST", "REDIS_AUTH_TOKEN", "ORIGIN_VERIFY_HEADER",
    ) if not config.get(key)]
    if missing:
        raise RuntimeError("Production settings missing: " + ", ".join(missing))
    if not config["COGNITO_ISSUER"].startswith("https://") or not config["COGNITO_JWKS_URI"].startswith("https://"):
        raise RuntimeError("Production Cognito endpoints must use HTTPS")
    if not re.fullmatch(r"[a-f0-9]{40}", config.get("APP_RELEASE", "")):
        raise RuntimeError("APP_RELEASE must identify the reviewed 40-character Git SHA")
    if config.get("DB_USER") in {"root", "admin"}:
        raise RuntimeError("Production requires a restricted runtime DB user")
    if len(config["ORIGIN_VERIFY_HEADER"]) < 32:
        raise RuntimeError("Production origin verification secret must have at least 32 characters")
    if not config.get("RATE_LIMIT_ENABLED") or not config.get("OCR_REQUIRE_CONSENT"):
        raise RuntimeError("Production requires admission limits and receipt processing consent")
    for key in (
        "API_REQUESTS_PER_MINUTE", "API_WRITES_PER_MINUTE", "RECEIPTS_PER_USER_DAY",
        "RECEIPTS_PER_HOUSEHOLD_DAY", "RECEIPTS_GLOBAL_DAY", "AI_SUGGESTIONS_PER_USER_DAY",
        "AI_SUGGESTIONS_PER_HOUSEHOLD_DAY", "AI_SUGGESTIONS_GLOBAL_DAY",
    ):
        if not isinstance(config.get(key), int) or config[key] < 1:
            raise RuntimeError(f"{key} must be a positive integer")
    if config.get("GEMINI_ENABLED") and not config.get("GEMINI_ROTATION_CONFIRMED"):
        raise RuntimeError("Gemini stays disabled until provider key rotation is confirmed")
    if config.get("GEMINI_ENABLED") and not config.get("GEMINI_API_KEY"):
        raise RuntimeError("Enabled Gemini requires a server-side key")
