"""Recovery guards must stop before generating content or committing stale data."""

import copy
import importlib.util
import io
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError


SOURCE = Path(__file__).resolve().parents[2] / "scripts" / "receipt-recovery-runtime.py"
SPEC = importlib.util.spec_from_file_location("receipt_recovery_runtime", SOURCE)
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)


class Database:
    def __init__(self, receipt):
        self.receipt = copy.deepcopy(receipt)
        self.transactions = []
        self.partial = {"merchant_raw": None, "warnings": None, "ocr_confidence": None}
        self.member = True
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.staged_receipt = copy.deepcopy(receipt)
        self.staged_transactions = []

    def cursor(self):
        return Cursor(self)

    def commit(self):
        self.receipt = copy.deepcopy(self.staged_receipt)
        self.transactions = copy.deepcopy(self.staged_transactions)
        self.commits += 1

    def rollback(self):
        self.staged_receipt = copy.deepcopy(self.receipt)
        self.staged_transactions = copy.deepcopy(self.transactions)
        self.rollbacks += 1

    def close(self):
        self.closed = True


class Cursor:
    def __init__(self, db):
        self.db = db
        self.row = None
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=()):
        self.row, self.rows = None, []
        if sql.startswith("SET SESSION"):
            return
        if sql.startswith("SELECT id,household_id"):
            self.row = copy.deepcopy(self.db.staged_receipt)
        elif sql.startswith("SELECT id,status FROM transactions"):
            self.rows = copy.deepcopy(self.db.staged_transactions)
        elif sql.startswith("SELECT user_id FROM household_members"):
            self.row = {"user_id": 7} if self.db.member else None
        elif sql.startswith("SELECT merchant_raw"):
            self.row = dict(self.db.partial)
        elif sql.startswith("SELECT status,error_code"):
            self.row = {key: self.db.staged_receipt[key] for key in ("status", "error_code")}
        else:
            raise AssertionError(sql)

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


@pytest.fixture
def scenario(monkeypatch):
    receipt = {"id": 1, "household_id": 1, "uploader_id": 7, "s3_key": "receipts/uploads/a.jpg",
               "status": "FAILED", "error_code": "WORKER_MAX_ATTEMPTS",
               "created_at": datetime(2026, 10, 25), "processed_at": datetime(2026, 10, 25),
               "content_sha256": None}
    db = Database(receipt)
    s3_requests, clients, generations = [], [], []

    def get_object(**request):
        s3_requests.append(request)
        return {"Body": io.BytesIO(b"image")}

    def client(**kwargs):
        value = SimpleNamespace(close=lambda: None, kwargs=kwargs)
        clients.append(value)
        return value

    def extract(*args, **kwargs):
        generations.append((args, kwargs))
        assert recovery.llm.MAX_TRIES == 1
        assert not recovery.llm._should_fallback()
        return {"total": 100000, "date": "2026-10-25", "items": []}

    def persist(active_db, target, raw, duplicate):
        categories = [{"id": 1, "name": "Chưa phân loại"}]
        invoice = recovery.pipeline.extract_invoice(raw, "image/jpeg", ["Chưa phân loại"])
        normalized = recovery.pipeline.normalize_invoice(invoice, categories, target["created_at"])
        active_db.staged_receipt.update(status=normalized["status"], error_code=None)
        active_db.staged_transactions = [{"id": 99, "status": "DRAFT"}]
        active_db.commit()
        return {"transaction_id": 99}

    monkeypatch.setattr(recovery, "connect", lambda _: db)
    monkeypatch.setattr(recovery.boto3, "client", lambda *a, **k: SimpleNamespace(get_object=get_object))
    monkeypatch.setattr(recovery.llm.genai, "Client", client)
    monkeypatch.setattr(recovery.llm, "extract_invoice", extract)
    monkeypatch.setattr(recovery.pipeline, "_persist_receipt", persist)
    config = {"MAX_RECEIPT_BYTES": 5000000, "AWS_REGION": "ap-southeast-1",
              "S3_BUCKET": "test-bucket", "GEMINI_API_KEY": "unit-test-key"}
    meta = {"ContentLength": 5, "ContentType": "image/jpeg", "ETag": "expected-etag"}
    inspection = {"transaction_count": 0, "uploader_is_current_member": True,
                  "uncategorized_exists": True, "key_has_upload_prefix": True,
                  "source_object": {"exists": True},
                  "provider_metadata_probe": {"performed": True, "available": True}}
    return SimpleNamespace(receipt=receipt, db=db, config=config, meta=meta, inspection=inspection,
                           s3_requests=s3_requests, clients=clients, generations=generations,
                           persist=persist)


def run(scenario):
    recovery.recover_one(scenario.config, scenario.receipt, scenario.meta, scenario.inspection)


@pytest.mark.parametrize("change", ["receipt", "transaction", "membership", "partial_extraction"])
def test_stale_or_existing_data_stops_before_external_processing(scenario, change):
    if change == "receipt":
        scenario.db.staged_receipt["status"] = "CONFIRMED"
    elif change == "transaction":
        scenario.db.staged_transactions = [{"id": 88, "status": "CONFIRMED"}]
    elif change == "membership":
        scenario.db.member = False
    else:
        scenario.db.partial["merchant_raw"] = "existing private content"
    with pytest.raises(ValueError):
        run(scenario)
    assert not scenario.s3_requests and not scenario.generations
    assert scenario.db.commits == 0 and scenario.db.closed


def test_changed_object_stops_without_generation(scenario, monkeypatch):
    def changed(**kwargs):
        raise ClientError({"Error": {"Code": "PreconditionFailed", "Message": "private object key"}}, "GetObject")
    monkeypatch.setattr(recovery.boto3, "client", lambda *a, **k: SimpleNamespace(get_object=changed))
    with pytest.raises(ClientError):
        run(scenario)
    assert not scenario.generations and scenario.db.commits == 0
    assert scenario.db.receipt["status"] == "FAILED"


def test_extraction_failure_rolls_back_and_does_not_log_exception_data(scenario, monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise ValueError("private invoice contents and secret")
    monkeypatch.setattr(recovery.llm, "extract_invoice", fail)
    with pytest.raises(ValueError):
        run(scenario)
    assert scenario.db.receipt["status"] == "FAILED" and not scenario.db.transactions
    assert scenario.db.rollbacks == 1 and scenario.db.commits == 0
    assert "private invoice" not in capsys.readouterr().out


def test_success_is_one_draft_for_manual_review_and_pins_source(scenario, capsys):
    old_tries = recovery.llm.MAX_TRIES
    run(scenario)
    assert scenario.db.receipt["status"] == "NEEDS_REVIEW"
    assert scenario.db.transactions == [{"id": 99, "status": "DRAFT"}]
    assert scenario.db.commits == 1 and scenario.db.closed
    assert len(scenario.generations) == 1
    assert scenario.s3_requests[0]["IfMatch"] == "expected-etag"
    assert scenario.clients[0].kwargs["http_options"].retry_options.attempts == 1
    assert recovery.llm.MAX_TRIES == old_tries
    output = capsys.readouterr().out
    assert "RECEIPT_RECOVERY_SUCCEEDED" in output and "unit-test-key" not in output


def test_empty_total_keeps_original_failed_state(scenario, monkeypatch):
    monkeypatch.setattr(recovery.llm, "extract_invoice", lambda *a, **k: {"total": 0, "items": []})
    with pytest.raises(ValueError, match="readable_positive_total"):
        run(scenario)
    assert scenario.db.receipt["status"] == "FAILED" and scenario.db.commits == 0


def test_second_generation_is_refused_before_second_provider_call(scenario, monkeypatch):
    def twice(db, receipt, raw, duplicate):
        recovery.pipeline.extract_invoice(raw, "image/jpeg", [])
        recovery.pipeline.extract_invoice(raw, "image/jpeg", [])
    monkeypatch.setattr(recovery.pipeline, "_persist_receipt", twice)
    with pytest.raises(RuntimeError, match="generation_limit"):
        run(scenario)
    assert len(scenario.generations) == 1
    assert scenario.db.receipt["status"] == "FAILED" and scenario.db.commits == 0


def test_failure_metadata_redacts_exception_messages():
    error = recovery.llm.errors.ServerError(503, {"message": "private invoice and credentials"})
    assert recovery.failure_fields(error) == {"error_type": "ServerError", "http_code": 503}
    assert recovery.failure_fields(ValueError("private invoice and credentials")) == {"error_type": "ValueError"}
    assert recovery.failure_fields(ValueError("receipt_changed_after_inspection")) == {
        "error_type": "ValueError", "guard_code": "receipt_changed_after_inspection"}
