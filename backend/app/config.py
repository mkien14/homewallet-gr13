import os

try:  
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _boolean(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    if value.strip().lower() not in {"true", "false", "1", "0"}:
        raise ValueError(f"{name} must be true or false")
    return value.strip().lower() in {"true", "1"}


def load_config():
    ids = [x.strip() for x in os.getenv("COGNITO_CLIENT_IDS", "").split(",") if x.strip()]
    ses_from_address = os.getenv("SES_FROM_ADDRESS")
    production = os.getenv("APP_ENV", "dev").strip().lower() == "production"
    return {
        "APP_ENV": os.getenv("APP_ENV", "dev").strip().lower(),
        "APP_RELEASE": os.getenv("APP_RELEASE", "local"),
        "PRODUCTION_ALLOWED_HOUSEHOLD_IDS": {
            int(value.strip()) for value in os.getenv("PRODUCTION_ALLOWED_HOUSEHOLD_IDS", "").split(",") if value.strip()
        },
        "ORIGIN_VERIFY_HEADER": os.getenv("ORIGIN_VERIFY_HEADER"),
        "GEMINI_ENABLED": _boolean("GEMINI_ENABLED", not production),
        "GEMINI_ROTATION_CONFIRMED": _boolean("GEMINI_ROTATION_CONFIRMED", False),
        "OCR_ENABLED": _boolean("OCR_ENABLED", not production),
        "OCR_REQUIRE_CONSENT": _boolean("OCR_REQUIRE_CONSENT", production),
        "RATE_LIMIT_ENABLED": _boolean("RATE_LIMIT_ENABLED", production),
        "API_REQUESTS_PER_MINUTE": int(os.getenv("API_REQUESTS_PER_MINUTE", "120")),
        "API_WRITES_PER_MINUTE": int(os.getenv("API_WRITES_PER_MINUTE", "30")),
        "RECEIPTS_PER_USER_DAY": int(os.getenv("RECEIPTS_PER_USER_DAY", "10")),
        "RECEIPTS_PER_HOUSEHOLD_DAY": int(os.getenv("RECEIPTS_PER_HOUSEHOLD_DAY", "30")),
        "RECEIPTS_GLOBAL_DAY": int(os.getenv("RECEIPTS_GLOBAL_DAY", "200")),
        "AI_SUGGESTIONS_PER_USER_DAY": int(os.getenv("AI_SUGGESTIONS_PER_USER_DAY", "10")),
        "AI_SUGGESTIONS_PER_HOUSEHOLD_DAY": int(os.getenv("AI_SUGGESTIONS_PER_HOUSEHOLD_DAY", "20")),
        "AI_SUGGESTIONS_GLOBAL_DAY": int(os.getenv("AI_SUGGESTIONS_GLOBAL_DAY", "100")),
        "MAX_CONTENT_LENGTH": 1024 * 1024,
        "COGNITO_ISSUER": os.getenv("COGNITO_ISSUER"),
        "COGNITO_JWKS_URI": os.getenv("COGNITO_JWKS_URI"),
        "COGNITO_CLIENT_IDS": ids,
        "COGNITO_HOSTED_UI": os.getenv("COGNITO_HOSTED_UI"),
        "DB_HOST": os.getenv("DB_HOST", "localhost"),
        "DB_PORT": int(os.getenv("DB_PORT", "3306")),
        "DB_USER": os.getenv("DB_USER", "root"),
        "DB_PASSWORD": os.getenv("DB_PASSWORD", ""),
        "DB_NAME": os.getenv("DB_NAME", "homewallet"),
        "DB_SSL_CA": os.getenv("DB_SSL_CA"),
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
        "GEMINI_MODEL": os.getenv("GEMINI_MODEL"),
        "REDIS_HOST": os.getenv("REDIS_HOST"),
        "REDIS_PORT": int(os.getenv("REDIS_PORT", "6379")),
        "REDIS_USERNAME": os.getenv("REDIS_USERNAME"),
        "REDIS_AUTH_TOKEN": os.getenv("REDIS_AUTH_TOKEN"),
        "REDIS_SSL_CA": os.getenv("REDIS_SSL_CA"),
        "REDIS_SOCKET_TIMEOUT": float(os.getenv("REDIS_SOCKET_TIMEOUT", "0.5")),
        "DASHBOARD_CACHE_TTL": int(os.getenv("DASHBOARD_CACHE_TTL", "300")),
        "SES_FROM_ADDRESS": ses_from_address,
        "VAPID_PRIVATE_KEY": os.getenv("VAPID_PRIVATE_KEY"),
        "VAPID_CLAIMS_SUB": os.getenv("VAPID_CLAIMS_SUB")
        or (f"mailto:{ses_from_address}" if ses_from_address else None),
        "S3_BUCKET": os.getenv("S3_BUCKET"),
        "AWS_REGION": os.getenv("AWS_REGION", "ap-southeast-1"),
        "MAX_RECEIPT_BYTES": int(os.getenv("MAX_RECEIPT_BYTES", str(5 * 1024 * 1024))),
        "PRESIGN_EXPIRES": int(os.getenv("PRESIGN_EXPIRES", "300")),
    }
