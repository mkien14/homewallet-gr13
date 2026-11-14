"""Production receipt authorization and a shared, fail-closed provider budget."""
from datetime import datetime, timezone
from app.household_policy import household_admitted


class ReceiptRejected(ValueError):
    pass


class ReceiptQuotaExceeded(RuntimeError):
    pass


def authorize(cursor, receipt, config, *, bucket=None):
    if config.get("APP_ENV") != "production":
        return
    if not config.get("OCR_ENABLED") or not config.get("GEMINI_ENABLED"):
        raise ReceiptRejected("OCR_DISABLED")
    household = receipt["household_id"]
    if not household_admitted(config, household):
        raise ReceiptRejected("HOUSEHOLD_NOT_APPROVED")
    if bucket is not None and bucket != config.get("S3_BUCKET"):
        raise ReceiptRejected("UNEXPECTED_BUCKET")
    if not receipt["s3_key"].startswith(f"receipts/production/{household}/"):
        raise ReceiptRejected("LEGACY_RECEIPT_RETAINED")
    cursor.execute(
        "SELECT 1 FROM household_members WHERE household_id = %s AND user_id = %s",
        (household, receipt["uploader_id"]),
    )
    if cursor.fetchone() is None:
        raise ReceiptRejected("UPLOADER_NO_LONGER_MEMBER")
    cursor.execute(
        "SELECT 1 FROM audit_logs WHERE action = 'RECEIPT_PROCESSING_CONSENT_V1' "
        "AND entity = 'receipt' AND entity_id = %s AND actor_id = %s LIMIT 1",
        (receipt["id"], receipt["uploader_id"]),
    )
    if cursor.fetchone() is None:
        raise ReceiptRejected("CONSENT_REQUIRED")


def reserve_attempt(db, receipt, config):
    """Charge every actual attempt, including retries, before calling Google.

    MySQL named lock serializes reservations across worker processes. Audit rows
    survive retries/restarts. Rejected reservations do not spend provider quota.
    """
    if config.get("APP_ENV") != "production":
        return
    lock_name = "hw.production.ocr.provider"
    # Drop earlier category/status read snapshots before the serialized count.
    db.rollback()
    with db.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK(%s, 0) AS acquired", (lock_name,))
        row = cursor.fetchone()
        if not row or row["acquired"] != 1:
            raise ReceiptQuotaExceeded("PROVIDER_BUSY")
        try:
            authorize(cursor, receipt, config, bucket=config.get("S3_BUCKET"))
            cursor.execute(
                "SELECT COUNT(*) AS used, MAX(`at`) AS latest FROM audit_logs "
                "WHERE action = 'OCR_PROVIDER_ATTEMPT_V1' AND `at` >= UTC_DATE()"
            )
            row = cursor.fetchone()
            cap = config.get("OCR_PROVIDER_REQUESTS_PER_DAY", 10)
            if not isinstance(cap, int) or not 1 <= cap <= 15 or row["used"] >= cap:
                raise ReceiptQuotaExceeded("PROVIDER_DAILY_LIMIT")
            latest = row.get("latest")
            if latest:
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                if (now - latest.replace(tzinfo=None)).total_seconds() < 30:
                    raise ReceiptQuotaExceeded("PROVIDER_MINUTE_LIMIT")
            cursor.execute(
                "SELECT COUNT(*) AS used FROM audit_logs "
                "WHERE action = 'OCR_PROVIDER_ATTEMPT_V1' AND entity = 'receipt' AND entity_id = %s",
                (receipt["id"],),
            )
            if cursor.fetchone()["used"] >= 2:
                raise ReceiptQuotaExceeded("RECEIPT_ATTEMPT_LIMIT")
            cursor.execute(
                "INSERT INTO audit_logs (actor_id, action, entity, entity_id) "
                "VALUES (%s, 'OCR_PROVIDER_ATTEMPT_V1', 'receipt', %s)",
                (receipt["uploader_id"], receipt["id"]),
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))
