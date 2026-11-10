"""Inspect receipt 1 by default; optionally recover it once using a matching plan."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import boto3
from botocore.exceptions import ClientError

from app.config import load_config
from app.db import connect
from jobs import llm, pipeline


SAFE_GUARD_CODES = frozenset({
    "unexpected_recovery_target", "recovery_preconditions_not_met", "recovery_object_not_supported",
    "receipt_changed_after_inspection", "recovery_transaction_already_exists",
    "uploader_membership_changed", "preserve_existing_partial_extraction",
    "recovery_object_size_changed", "recovery_generation_limit_exceeded",
    "recovery_requires_readable_positive_total", "committed_recovery_requires_manual_verification",
    "historical_receipt_scope_mismatch", "missing_readiness_fingerprint",
    "historical_receipt_identity_mismatch", "readiness_fingerprint_changed",
})


def failure_fields(exc):
    fields = {"error_type": type(exc).__name__}
    # Record only locally defined guards or numeric HTTP status, never error text.
    if str(exc) in SAFE_GUARD_CODES:
        fields["guard_code"] = str(exc)
    code = getattr(exc, "code", None)
    if type(code) is int and 100 <= code <= 599:
        fields["http_code"] = code
    return fields


def digest(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def emit(event, **fields):
    print(json.dumps({"event": event, "at_utc": datetime.now(timezone.utc).isoformat(),
                      **fields}, ensure_ascii=True, default=str), flush=True)


def recover_one(config, receipt, meta, inspection):
    """Keep FAILED until a single, guarded draft transaction can be committed."""
    if (receipt["id"], receipt["household_id"], receipt["status"], receipt["error_code"]) != (
            1, 1, "FAILED", "WORKER_MAX_ATTEMPTS"):
        raise ValueError("unexpected_recovery_target")
    if (inspection["transaction_count"] != 0 or not inspection["uploader_is_current_member"]
            or not inspection["uncategorized_exists"]
            or inspection["provider_metadata_probe"] != {"performed": True, "available": True}
            or not inspection["key_has_upload_prefix"]
            or not inspection["source_object"].get("exists")):
        raise ValueError("recovery_preconditions_not_met")
    max_bytes = min(config["MAX_RECEIPT_BYTES"], 5 * 1024 * 1024)
    if not 0 < meta["ContentLength"] <= max_bytes or meta.get("ContentType") not in pipeline.SUPPORTED_TYPES:
        raise ValueError("recovery_object_not_supported")
    db = connect(config)
    client = None
    calls = 0
    committed = False
    try:
        with db.cursor() as cur:
            cur.execute("SET SESSION innodb_lock_wait_timeout=5")
            cur.execute("SELECT id,household_id,uploader_id,s3_key,status,error_code,"
                        "created_at,processed_at,content_sha256 FROM receipts WHERE id=%s FOR UPDATE", (1,))
            if cur.fetchone() != receipt:
                raise ValueError("receipt_changed_after_inspection")
            cur.execute("SELECT id,status FROM transactions WHERE receipt_id=%s FOR UPDATE", (1,))
            if cur.fetchall():
                raise ValueError("recovery_transaction_already_exists")
            cur.execute("SELECT user_id FROM household_members WHERE household_id=%s "
                        "AND user_id=%s FOR SHARE", (1, receipt["uploader_id"]))
            if not cur.fetchone():
                raise ValueError("uploader_membership_changed")
            cur.execute("SELECT merchant_raw,warnings,ocr_confidence FROM receipts WHERE id=%s", (1,))
            partial = cur.fetchone()
            if (not partial or partial["merchant_raw"] is not None
                    or partial["warnings"] not in (None, "[]")
                    or partial["ocr_confidence"] is not None or receipt["content_sha256"] is not None):
                raise ValueError("preserve_existing_partial_extraction")

        s3 = boto3.client("s3", region_name=config["AWS_REGION"])
        response = s3.get_object(Bucket=config["S3_BUCKET"], Key=receipt["s3_key"], IfMatch=meta["ETag"])
        with response["Body"] as body:
            raw_bytes = body.read(max_bytes + 1)
        if len(raw_bytes) != meta["ContentLength"] or len(raw_bytes) > max_bytes:
            raise ValueError("recovery_object_size_changed")
        client = llm.genai.Client(api_key=config["GEMINI_API_KEY"], http_options=llm.types.HttpOptions(
            timeout=20_000, retry_options=llm.types.HttpRetryOptions(attempts=1)))
        original_normalize = pipeline.normalize_invoice

        def extract_once(image, mime, categories):
            nonlocal calls
            calls += 1
            if calls != 1:
                raise RuntimeError("recovery_generation_limit_exceeded")
            return llm.extract_invoice(image, mime, categories, client=client)

        def manual_review_only(raw, categories, uploaded_at):
            result = original_normalize(raw, categories, uploaded_at)
            if result["total_amount"] <= 0:
                raise ValueError("recovery_requires_readable_positive_total")
            result["status"] = "NEEDS_REVIEW"
            return result

        emit("RECEIPT_RECOVERY_ATTEMPT", receipt_id=1, household_id=1,
             generation_limit=1, sdk_retry_attempts=1, fallback_enabled=False,
             original_object_retained=True, original_dlq_message_retained=True)
        with patch.object(llm, "MAX_TRIES", 1), patch.object(llm, "MIN_INTERVAL", 0), \
                patch.object(llm, "_should_fallback", return_value=False), \
                patch.object(pipeline, "extract_invoice", side_effect=extract_once), \
                patch.object(pipeline, "normalize_invoice", side_effect=manual_review_only):
            result = pipeline._persist_receipt(db, receipt, raw_bytes, False)
        committed = True
        with db.cursor() as cur:
            cur.execute("SELECT status,error_code FROM receipts WHERE id=%s", (1,))
            after = cur.fetchone()
            cur.execute("SELECT id,status FROM transactions WHERE receipt_id=%s", (1,))
            transactions = cur.fetchall()
        if (after != {"status": "NEEDS_REVIEW", "error_code": None}
                or len(transactions) != 1 or transactions[0]["status"] != "DRAFT"
                or transactions[0]["id"] != result.get("transaction_id") or calls != 1):
            raise RuntimeError("committed_recovery_requires_manual_verification")
        emit("RECEIPT_RECOVERY_SUCCEEDED", receipt_id=1, household_id=1,
             receipt_status=after["status"], transaction_id=transactions[0]["id"],
             transaction_status="DRAFT", generation_calls=calls,
             original_object_retained=True, original_dlq_message_retained=True)
    except Exception:
        db.rollback()
        emit("RECEIPT_RECOVERY_ATTEMPT_FAILED", receipt_id=1, generation_calls=calls,
             persistence_returned=committed, reinspection_required=True)
        raise
    finally:
        db.close()
        if client is not None:
            client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt-id", type=int, required=True)
    parser.add_argument("--household-id", type=int, required=True)
    parser.add_argument("--check-model", action="store_true",
                        help="Check provider model metadata; no invoice or generation request")
    parser.add_argument("--execute", action="store_true",
                        help="Recover receipt 1 once; requires the matching readiness fingerprint")
    parser.add_argument("--expected-inspection-sha256")
    args = parser.parse_args()
    # This historical incident has a fixed scope, not a general receipt lookup.
    if (args.receipt_id, args.household_id) != (1, 1):
        raise ValueError("historical_receipt_scope_mismatch")
    if args.execute and not args.expected_inspection_sha256:
        raise ValueError("missing_readiness_fingerprint")
    config = load_config()
    db = connect(config)
    try:
        with db.cursor() as cur:
            cur.execute("START TRANSACTION READ ONLY")
            cur.execute("SELECT id,household_id,uploader_id,s3_key,status,error_code,"
                        "created_at,processed_at,content_sha256 FROM receipts WHERE id=%s",
                        (args.receipt_id,))
            receipt = cur.fetchone()
            if not receipt or receipt["household_id"] != args.household_id:
                raise ValueError("historical_receipt_identity_mismatch")
            cur.execute("SELECT id,status FROM transactions WHERE receipt_id=%s ORDER BY id",
                        (args.receipt_id,))
            transactions = cur.fetchall()
            cur.execute("SELECT COUNT(*) AS n FROM household_members "
                        "WHERE household_id=%s AND user_id=%s",
                        (receipt["household_id"], receipt["uploader_id"]))
            uploader_is_member = cur.fetchone()["n"] == 1
            categories = pipeline._load_categories(cur, receipt["household_id"])
        db.rollback()
    finally:
        db.close()

    object_info = {"exists": False}
    bucket = config.get("S3_BUCKET")
    if bucket:
        try:
            meta = boto3.client("s3", region_name=config["AWS_REGION"]).head_object(
                Bucket=bucket, Key=receipt["s3_key"])
            object_info = {"exists": True, "bytes": meta["ContentLength"],
                           "content_type": meta.get("ContentType"),
                           "last_modified": meta["LastModified"].isoformat(),
                           "etag_sha256": digest(meta.get("ETag", "")),
                           "version_id_sha256": digest(meta.get("VersionId", ""))}
        except ClientError as exc:
            object_info["aws_error_code"] = exc.response["Error"]["Code"]
    else:
        object_info["error"] = "bucket_not_configured"
    result = {"receipt_id": receipt["id"], "household_id": receipt["household_id"],
              "status": receipt["status"], "error_code": receipt["error_code"],
              "created_at": str(receipt["created_at"]),
              "processed_at": str(receipt["processed_at"]),
              "key_sha256": digest(receipt["s3_key"]),
              "key_has_upload_prefix": receipt["s3_key"].startswith("receipts/uploads/"),
              "stored_content_sha256_present": bool(receipt["content_sha256"]),
              "transaction_count": len(transactions),
              "transaction_statuses": [x["status"] for x in transactions],
              "uploader_is_current_member": uploader_is_member,
              "uncategorized_exists": any(x["name"].casefold() == "chưa phân loại"
                                          for x in categories),
              "source_object": object_info,
              "gemini_key_configured": bool(config.get("GEMINI_API_KEY")),
              "gemini_model": config.get("GEMINI_MODEL"),
              "normal_gemini_max_tries": llm.MAX_TRIES,
              "pipeline_sha256": hashlib.sha256(Path(pipeline.__file__).read_bytes()).hexdigest(),
              "llm_sha256": hashlib.sha256(Path(llm.__file__).read_bytes()).hexdigest()}
    result["provider_metadata_probe"] = {"performed": False}
    if (args.check_model or args.execute) and config.get("GEMINI_API_KEY") and config.get("GEMINI_MODEL"):
        client = llm.genai.Client(api_key=config["GEMINI_API_KEY"],
                                 http_options=llm.types.HttpOptions(timeout=10_000))
        try:
            client.models.get(model=config["GEMINI_MODEL"])
            result["provider_metadata_probe"] = {"performed": True, "available": True}
        except Exception as exc:
            result["provider_metadata_probe"] = {"performed": True, "available": False,
                                                 "error_type": type(exc).__name__,
                                                 "http_code": getattr(exc, "code", None)}
        finally:
            client.close()
    result["inspection_sha256"] = digest(json.dumps(result, sort_keys=True))
    emit("RECEIPT_RECOVERY_INSPECTION", **result)
    if args.execute:
        if result["inspection_sha256"] != args.expected_inspection_sha256:
            raise ValueError("readiness_fingerprint_changed")
        recover_one(config, receipt, meta, result)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Exception text can contain DB credentials, S3 keys, or document details.
        emit("RECEIPT_RECOVERY_FAILED", **failure_fields(exc))
        raise SystemExit(1)
