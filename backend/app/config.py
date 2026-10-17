import os

try:  
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def load_config():
    ids = [x.strip() for x in os.getenv("COGNITO_CLIENT_IDS", "").split(",") if x.strip()]
    return {
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
        "S3_BUCKET": os.getenv("S3_BUCKET"),
        "AWS_REGION": os.getenv("AWS_REGION", "ap-southeast-1"),
        "MAX_RECEIPT_BYTES": int(os.getenv("MAX_RECEIPT_BYTES", str(5 * 1024 * 1024))),
        "PRESIGN_EXPIRES": int(os.getenv("PRESIGN_EXPIRES", "300")),
    }