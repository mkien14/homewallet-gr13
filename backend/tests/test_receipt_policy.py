from datetime import datetime, timezone
import pytest
from jobs import receipt_policy as policy


class Cursor:
    def __init__(self, *, consent=True, used=0, attempts=0, latest=None, locked=True):
        self.consent, self.used, self.attempts, self.latest = consent, used, attempts, latest
        self.locked, self.result, self.inserts = locked, None, 0

    def __enter__(self): return self
    def __exit__(self, *_): return False
    def fetchone(self): return self.result
    def execute(self, sql, params=()):
        if "GET_LOCK" in sql: self.result = {"acquired": int(self.locked)}
        elif "RELEASE_LOCK" in sql: self.result = None
        elif "FROM household_members" in sql: self.result = {"ok": 1}
        elif "RECEIPT_PROCESSING_CONSENT_V1" in sql: self.result = {"ok": 1} if self.consent else None
        elif "MAX(`at`)" in sql: self.result = {"used": self.used, "latest": self.latest}
        elif "COUNT(*)" in sql: self.result = {"used": self.attempts}
        elif "INSERT INTO audit_logs" in sql: self.inserts += 1
        else: raise AssertionError(sql)


class Database:
    def __init__(self, cursor): self.c = cursor; self.commits = 0
    def cursor(self): return self.c
    def commit(self): self.commits += 1
    def rollback(self): pass


CFG = {"APP_ENV":"production", "OCR_ENABLED":True, "GEMINI_ENABLED":True,
       "PRODUCTION_ALLOWED_HOUSEHOLD_IDS":{3}, "S3_BUCKET":"approved", "OCR_PROVIDER_REQUESTS_PER_DAY":10}
RECEIPT = {"id":7, "household_id":3, "uploader_id":5, "s3_key":"receipts/production/3/new.jpg"}


def test_persisted_consent_required():
    with pytest.raises(policy.ReceiptRejected, match="CONSENT_REQUIRED"):
        policy.authorize(Cursor(consent=False), RECEIPT, CFG, bucket="approved")


def test_authorized_receipt():
    policy.authorize(Cursor(), RECEIPT, CFG, bucket="approved")


def test_public_ocr_admits_new_household_but_still_requires_consent():
    cfg = dict(CFG, PRODUCTION_PUBLIC_REGISTRATION=True)
    receipt = dict(RECEIPT, household_id=999, s3_key="receipts/production/999/new.jpg")
    policy.authorize(Cursor(), receipt, cfg, bucket="approved")
    with pytest.raises(policy.ReceiptRejected, match="CONSENT_REQUIRED"):
        policy.authorize(Cursor(consent=False), receipt, cfg, bucket="approved")
    with pytest.raises(policy.ReceiptRejected, match="HOUSEHOLD_NOT_APPROVED"):
        policy.authorize(Cursor(), dict(receipt, household_id=1), cfg, bucket="approved")


@pytest.mark.parametrize("kwargs", [dict(used=10), dict(attempts=2), dict(locked=False),
                                    dict(latest="now")])
def test_quota_denials_never_reserve(kwargs):
    if kwargs.get("latest") == "now":
        kwargs = dict(kwargs, latest=datetime.now(timezone.utc).replace(tzinfo=None))
    cursor = Cursor(**kwargs)
    with pytest.raises(policy.ReceiptQuotaExceeded): policy.reserve_attempt(Database(cursor), RECEIPT, CFG)
    assert cursor.inserts == 0


def test_attempt_is_committed_before_provider():
    cursor = Cursor(); db = Database(cursor)
    policy.reserve_attempt(db, RECEIPT, CFG)
    assert cursor.inserts == db.commits == 1


def test_bootstrap_grants_allow_persisted_consent_reads():
    from jobs.bootstrap_runtime_db import grant_statements
    audit_grants = [sql for sql, table in grant_statements() if table == 'audit_logs']
    assert len(audit_grants) == 1
    assert 'GRANT SELECT, INSERT' in audit_grants[0]
