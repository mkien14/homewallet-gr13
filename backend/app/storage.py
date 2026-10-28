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


def presign_download(key):
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": _bucket(), "Key": key},
        ExpiresIn=300,
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


def delete_s3_objects(keys):
    if not keys:
        return {"deleted": 0, "keys": []}

    unique_keys = []
    seen = set()
    for key in keys:
        if isinstance(key, str) and key.strip() and key not in seen:
            unique_keys.append(key)
            seen.add(key)

    if not unique_keys:
        return {"deleted": 0, "keys": []}

    bucket = _bucket()
    client = _client()
    deleted_count = 0
    errors = []

    for key in unique_keys:
        try:
            versions = []
            paginator = client.get_paginator("list_object_versions")
            for page in paginator.paginate(Bucket=bucket, Prefix=key):
                for item in page.get("Versions", []) or []:
                    if item.get("Key") == key:
                        versions.append({"Key": key, "VersionId": item["VersionId"]})
                for item in page.get("DeleteMarkers", []) or []:
                    if item.get("Key") == key:
                        versions.append({"Key": key, "VersionId": item["VersionId"]})

            if not versions:
                continue

            response = client.delete_objects(
                Bucket=bucket,
                Delete={
                    "Objects": [{"Key": item["Key"], "VersionId": item["VersionId"]} for item in versions],
                    "Quiet": True,
                },
            )
            failed = response.get("Errors") or []
            if failed:
                for item in failed:
                    errors.append(f"{key}: {item.get('Code', 'UNKNOWN')} {item.get('Message', '')}".strip())
                continue
            deleted_count += len(versions)
        except ClientError as exc:
            err = exc.response.get("Error", {})
            errors.append(f"{key}: {err.get('Code', 'S3_ERROR')} {err.get('Message', '')}".strip())
        except Exception as exc:  # pragma: no cover - defensive path for local mocks
            errors.append(f"{key}: {exc}")

    if errors:
        message = "; ".join(errors[:5])
        raise ApiError(502, "S3_DELETE_FAILED", f"Xóa file S3 thất bại cho một số đối tượng: {message}")

    return {"deleted": deleted_count, "keys": unique_keys}