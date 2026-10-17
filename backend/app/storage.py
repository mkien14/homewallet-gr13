import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from flask import current_app

from .errors import ApiError


def _client():
    ext = current_app.extensions
    if "s3_client" not in ext:
        region = current_app.config["AWS_REGION"]
        ext["s3_client"] = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=f"https://s3.{region}.amazonaws.com", 
            config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
        )
    return ext["s3_client"]


def _bucket():
    bucket = current_app.config.get("S3_BUCKET")
    if not bucket:
        raise ApiError(500, "STORAGE_NOT_CONFIGURED", "Máy chủ chưa cấu hình kho lưu trữ")
    return bucket


def presign_upload(key, content_type):
    cfg = current_app.config
    return _client().generate_presigned_post(
        Bucket=_bucket(),
        Key=key,
        Fields={"Content-Type": content_type},
        Conditions=[
            {"Content-Type": content_type},
            ["content-length-range", 1, cfg["MAX_RECEIPT_BYTES"]],  
        ],
        ExpiresIn=cfg["PRESIGN_EXPIRES"],
    )


def object_exists(key):
    try:
        _client().head_object(Bucket=_bucket(), Key=key)
        return True
    except ClientError as e:
        code = str(e.response.get("Error", {}).get("Code"))
        if code in ("404", "NoSuchKey", "NotFound"):
            return False
        if code in ("403", "Forbidden"):
            current_app.logger.warning("HeadObject trả 403 cho %s", key)
            return False
        raise