import hashlib
import io
import json
import mimetypes
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import unquote_plus

import boto3
from PIL import Image, ImageOps

from app.config import load_config
from app.cache import invalidate_dashboard
from app.db import connect
from app.parsing import parse_date, parse_vnd
from jobs.llm import extract_invoice


MAX_SIDE = 2000
MAX_IMAGE_BYTES = 2_000_000
SUPPORTED_TYPES = {"image/jpeg", "image/png", "application/pdf"}
RETRYABLE_RECEIPT_STATUSES = ("UPLOADING", "UPLOADED", "PROCESSING")
FINISHED_RECEIPT_STATUSES = ("DRAFT_READY", "NEEDS_REVIEW", "CONFIRMED")


class ReceiptNotFound(Exception):
    pass


def resolve_file(file_path):
    path = Path(file_path)
    if not path.is_absolute() and not path.exists():
        repo_path = Path(__file__).resolve().parents[2] / path
        if repo_path.exists():
            path = repo_path
    path = path.resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")
    return path


def prepare_file(filename, raw_bytes):
    content_type, _ = mimetypes.guess_type(str(filename))
    if content_type not in SUPPORTED_TYPES:
        raise ValueError(f"Unsupported receipt file type: {Path(filename).suffix}")

    if content_type == "application/pdf":
        return raw_bytes, content_type

    with Image.open(io.BytesIO(raw_bytes)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    image.thumbnail((MAX_SIDE, MAX_SIDE))

    quality = 88
    while True:
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=quality, optimize=True)
        image_bytes = output.getvalue()
        if len(image_bytes) <= MAX_IMAGE_BYTES or quality <= 50:
            return image_bytes, "image/jpeg"
        quality -= 8


def _date_value(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value:
        try:
            return datetime.fromisoformat(str(value)).date()
        except ValueError:
            return None
    return None


def normalize_invoice(raw, category_rows, uploaded_at, *, today=None):
    if not isinstance(raw, dict):
        raise ValueError("Gemini receipt response must be a JSON object")

    categories_by_name = {
        row["name"].casefold(): row for row in category_rows
    }
    uncategorized = categories_by_name.get("chưa phân loại")
    if uncategorized is None:
        raise ValueError('Household is missing the "Chưa phân loại" category')

    items = []
    for raw_item in raw.get("items") or []:
        if not isinstance(raw_item, dict):
            raise ValueError("Each receipt item must be a JSON object")
        amount = parse_vnd(raw_item.get("amount"))
        if amount is None:
            continue
        unit_price = parse_vnd(raw_item.get("unit_price"))
        quantity = raw_item.get("quantity")
        if quantity is not None:
            try:
                quantity = float(quantity)
            except (TypeError, ValueError) as exc:
                raise ValueError("Item quantity must be numeric or null") from exc
        category = categories_by_name.get(str(raw_item.get("category") or "").casefold())
        items.append({
            "description": (
                str(raw_item["description"])[:255]
                if raw_item.get("description") is not None else None
            ),
            "quantity": quantity,
            "unit_price": unit_price,
            "amount": amount,
            "category_id": (category or uncategorized)["id"],
        })

    uploaded_date = _date_value(uploaded_at)
    if uploaded_date is None:
        raise ValueError("Receipt has no valid upload timestamp")
    today = today or date.today()
    invoice_date = parse_date(raw.get("date"))
    parsed_date = date.fromisoformat(invoice_date) if invoice_date else None
    if parsed_date is None or parsed_date > today + timedelta(days=1):
        date_needs_review = True
        occurred_on = uploaded_date
    else:
        date_needs_review = False
        occurred_on = parsed_date

    total_amount = parse_vnd(raw.get("total"))
    total_missing = total_amount is None
    if total_missing:
        total_amount = sum(item["amount"] for item in items)

    default_category_id = (categories_by_name.get(
        str(raw.get("category") or "").casefold()
    ) or uncategorized)["id"]
    if raw.get("category") is None and items:
        category_amounts = {}
        for item in items:
            category_amounts[item["category_id"]] = (
                category_amounts.get(item["category_id"], 0) + item["amount"]
            )
        default_category_id = max(
            category_amounts,
            key=lambda category_id: (category_amounts[category_id], -category_id),
        )

    warnings = []
    if date_needs_review:
        warnings.append("DATE_MISSING")
    if total_amount > 0 and items:
        difference = abs(total_amount - sum(item["amount"] for item in items))
        if difference > 1000 and (total_amount <= 0 or difference * 100 > total_amount):
            warnings.append("TOTAL_MISMATCH")

    duplicate_file = bool(raw.get("_duplicate_file"))
    if duplicate_file:
        warnings.append("DUPLICATE_FILE")

    return {
        "merchant": raw.get("merchant"),
        "occurred_on": occurred_on.isoformat(),
        "total_amount": total_amount,
        "category_id": default_category_id,
        "items": items,
        "warnings": warnings,
        "status": (
            "NEEDS_REVIEW"
            if date_needs_review or total_missing or "TOTAL_MISMATCH" in warnings
            else "DRAFT_READY"
        ),
    }


def _load_categories(cursor, household_id):
    cursor.execute(
        "SELECT id, name FROM categories "
        "WHERE household_id IS NULL OR household_id = %s ORDER BY id",
        (household_id,),
    )
    return cursor.fetchall()


def _receipt_for_reference(cursor, reference):
    cursor.execute(
        "SELECT id, household_id, uploader_id, s3_key, status, created_at, content_sha256 "
        "FROM receipts WHERE s3_key = %s",
        (reference["key"],),
    )
    return cursor.fetchone()


def _mark_processing(cursor, receipt_id):
    cursor.execute(
        "UPDATE receipts SET status = 'PROCESSING' "
        "WHERE id = %s AND status IN ('UPLOADING','UPLOADED','PROCESSING')",
        (receipt_id,),
    )
    if cursor.rowcount == 1:
        return True
    cursor.execute("SELECT status FROM receipts WHERE id = %s", (receipt_id,))
    current = cursor.fetchone()
    return current is not None and current["status"] == "PROCESSING"


def _persist_receipt(db, receipt, raw_bytes, duplicate):
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM receipts WHERE household_id = %s "
            "AND content_sha256 = %s AND id <> %s LIMIT 1",
            (receipt["household_id"], sha256, receipt["id"]),
        )
        is_duplicate = duplicate or cursor.fetchone() is not None
        categories = _load_categories(cursor, receipt["household_id"])
        category_names = [row["name"] for row in categories]

    processed_bytes, processed_type = prepare_file(receipt["s3_key"], raw_bytes)
    raw = extract_invoice(processed_bytes, processed_type, category_names)
    raw["_duplicate_file"] = is_duplicate
    result = normalize_invoice(raw, categories, receipt["created_at"])

    with db.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM transactions WHERE receipt_id = %s",
            (receipt["id"],),
        )
        existing_transaction = cursor.fetchone()
        if existing_transaction:
            cursor.execute(
                "SELECT status FROM transactions WHERE id = %s",
                (existing_transaction["id"],),
            )
            transaction = cursor.fetchone()
            if transaction and transaction["status"] in ("DRAFT", "CONFIRMED"):
                cursor.execute(
                    "UPDATE receipts SET status = %s, content_sha256 = %s, "
                    "processed_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (
                        "CONFIRMED" if transaction["status"] == "CONFIRMED"
                        else result["status"],
                        sha256,
                        receipt["id"],
                    ),
                )
                db.commit()
                return {
                    "receipt_id": receipt["id"],
                    "status": result["status"],
                    "transaction_id": existing_transaction["id"],
                    "duplicate": True,
                }

        cursor.execute(
            "INSERT INTO transactions "
            "(household_id, member_id, receipt_id, occurred_on, merchant, "
            "total_amount, category_id, status, source) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, 'DRAFT', 'OCR')",
            (
                receipt["household_id"],
                receipt["uploader_id"],
                receipt["id"],
                result["occurred_on"],
                result["merchant"],
                result["total_amount"],
                result["category_id"],
            ),
        )
        transaction_id = cursor.lastrowid
        if result["items"]:
            cursor.executemany(
                "INSERT INTO transaction_items "
                "(transaction_id, description, quantity, unit_price, amount, category_id) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                [
                    (
                        transaction_id,
                        item["description"],
                        item["quantity"],
                        item["unit_price"],
                        item["amount"],
                        item["category_id"],
                    )
                    for item in result["items"]
                ],
            )
        cursor.execute(
            "UPDATE receipts SET status = %s, merchant_raw = %s, warnings = %s, "
            "content_sha256 = %s, processed_at = CURRENT_TIMESTAMP, error_code = NULL "
            "WHERE id = %s",
            (
                result["status"],
                result["merchant"],
                json.dumps(result["warnings"]),
                sha256,
                receipt["id"],
            ),
        )
    db.commit()
    invalidate_dashboard(receipt["household_id"])
    return {"receipt_id": receipt["id"], "transaction_id": transaction_id, **result}


def process_receipt(reference, *, config=None, s3_client=None, file_bytes=None):
    config = config or load_config()
    db = connect(config)
    try:
        with db.cursor() as cursor:
            receipt = _receipt_for_reference(cursor, reference)
            if receipt is None:
                raise ReceiptNotFound(reference["key"])
            if receipt["status"] in FINISHED_RECEIPT_STATUSES:
                return {
                    "receipt_id": receipt["id"],
                    "status": receipt["status"],
                    "skipped": True,
                }
            if receipt["status"] == "FAILED":
                raise RuntimeError("Receipt has already reached FAILED status")
            if receipt["status"] not in RETRYABLE_RECEIPT_STATUSES:
                return {
                    "receipt_id": receipt["id"],
                    "status": receipt["status"],
                    "skipped": True,
                }
            if not _mark_processing(cursor, receipt["id"]):
                return {
                    "receipt_id": receipt["id"],
                    "status": receipt["status"],
                    "skipped": True,
                }
        db.commit()

        if file_bytes is None:
            bucket = reference.get("bucket") or config.get("S3_BUCKET")
            if not bucket:
                raise ValueError("Set S3_BUCKET to process receipts from S3")
            s3_client = s3_client or boto3.client(
                "s3", region_name=config.get("AWS_REGION", "ap-southeast-1")
            )
            response = s3_client.get_object(Bucket=bucket, Key=receipt["s3_key"])
            file_bytes = response["Body"].read()

        return _persist_receipt(db, receipt, file_bytes, False)
    except ReceiptNotFound:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def process_s3_event(event, *, config=None, s3_client=None):
    if event.get("Event") == "s3:TestEvent":
        return {"test_event": True, "results": []}
    records = event.get("Records")
    if not isinstance(records, list):
        raise ValueError("S3 notification must contain Records")

    results = []
    for record in records:
        try:
            bucket = record["s3"]["bucket"]["name"]
            key = unquote_plus(record["s3"]["object"]["key"])
        except (KeyError, TypeError) as exc:
            raise ValueError("Malformed S3 notification record") from exc
        reference = {"bucket": bucket, "key": key}
        try:
            results.append(process_receipt(reference, config=config, s3_client=s3_client))
        except ReceiptNotFound:
            results.append({"key": key, "not_found": True})
    return {"test_event": False, "results": results}


def process_local_file(file_path, household_id, user_id, *, config=None):
    config = config or load_config()
    path = resolve_file(file_path)
    raw_bytes = path.read_bytes()
    db = connect(config)
    receipt_id = None
    try:
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM household_members WHERE household_id = %s AND user_id = %s",
                (household_id, user_id),
            )
            if cursor.fetchone() is None:
                raise ValueError("User is not a member of the household")
            local_key = f"local/{uuid.uuid4().hex}/{path.name}"
            cursor.execute(
                "INSERT INTO receipts (household_id, uploader_id, s3_key, status) "
                "VALUES (%s, %s, %s, 'PROCESSING')",
                (household_id, user_id, local_key),
            )
            receipt = {
                "id": cursor.lastrowid,
                "household_id": household_id,
                "uploader_id": user_id,
                "s3_key": local_key,
                "status": "PROCESSING",
                "created_at": datetime.now(),
            }
            receipt_id = receipt["id"]
            _mark_processing(cursor, receipt["id"])
        db.commit()
        return _persist_receipt(db, receipt, raw_bytes, False)
    except Exception:
        db.rollback()
        if receipt_id is not None:
            with db.cursor() as cursor:
                cursor.execute(
                    "UPDATE receipts SET status = 'FAILED', error_code = %s, "
                    "processed_at = CURRENT_TIMESTAMP WHERE id = %s",
                    ("LOCAL_PROCESSING_FAILED", receipt_id),
                )
            db.commit()
        raise
    finally:
        db.close()


def process_file(file_path, *, config=None, household_id=None, user_id=None):
    path = resolve_file(file_path)
    if household_id is not None or user_id is not None:
        if household_id is None or user_id is None:
            raise ValueError("--household-id and --user-id must be supplied together")
        return process_local_file(
            path,
            household_id,
            user_id,
            config=config,
        )

    raw_bytes = path.read_bytes()
    processed_bytes, mime_type = prepare_file(path, raw_bytes)
    raw = extract_invoice(processed_bytes, mime_type, [])
    category_rows = [{"id": None, "name": "Chưa phân loại"}]
    result = normalize_invoice(raw, category_rows, datetime.fromtimestamp(path.stat().st_mtime))
    return {"path": str(path), **result}


def mark_receipt_failed(receipt_key, error_code, *, config=None):
    db = connect(config or load_config())
    try:
        with db.cursor() as cursor:
            cursor.execute(
                "UPDATE receipts SET status = 'FAILED', error_code = %s, "
                "processed_at = CURRENT_TIMESTAMP WHERE s3_key = %s "
                "AND status IN ('UPLOADING','UPLOADED','PROCESSING')",
                (error_code[:50], receipt_key),
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
