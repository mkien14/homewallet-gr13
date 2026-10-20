import io
import hashlib
import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from google.genai import errors
from PIL import Image

from jobs import llm, pipeline, worker


class FakeState:
    def __init__(self):
        self.receipt = {
            "id": 12,
            "household_id": 3,
            "uploader_id": 7,
            "s3_key": "receipts/receipt one.jpg",
            "status": "UPLOADED",
            "created_at": datetime(2026, 10, 19, 9),
            "content_sha256": None,
        }
        self.transactions = []
        self.items = []
        self.categories = [
            {"id": 2, "name": "Ăn uống"},
            {"id": 9, "name": "Chưa phân loại"},
        ]
        self.members = {(3, 7)}
        self.failures = []
        self.duplicate_hashes = set()
        self.commits = 0


class FakeCursor:
    def __init__(self, state):
        self.state = state
        self.rows = []
        self.row = None
        self.rowcount = 0
        self.lastrowid = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=()):
        sql = " ".join(sql.split())
        self.row = None
        self.rows = []
        self.rowcount = 0
        if sql.startswith("SELECT id, household_id, uploader_id, s3_key, status, created_at"):
            key = params[0]
            self.row = self.state.receipt if self.state.receipt["s3_key"] == key else None
        elif sql.startswith("SELECT id FROM receipts WHERE household_id"):
            digest = params[1]
            self.row = {"id": 99} if digest in self.state.duplicate_hashes else None
        elif sql.startswith("SELECT id, name FROM categories"):
            self.rows = self.state.categories
        elif sql.startswith("SELECT id, status FROM transactions"):
            self.row = next(
                (row for row in self.state.transactions if row["receipt_id"] == params[0]),
                None,
            )
        elif sql.startswith("SELECT id FROM transactions"):
            self.row = next(
                (row for row in self.state.transactions if row["receipt_id"] == params[0]),
                None,
            )
        elif sql.startswith("SELECT status FROM receipts"):
            self.row = {"status": self.state.receipt["status"]}
        elif sql.startswith("SELECT 1 FROM household_members"):
            self.row = (1,) if tuple(params) in self.state.members else None
        elif sql.startswith("UPDATE receipts SET status = 'PROCESSING'"):
            if self.state.receipt["id"] == params[0] and self.state.receipt["status"] in (
                "UPLOADING", "UPLOADED", "PROCESSING",
            ):
                self.state.receipt["status"] = "PROCESSING"
                self.rowcount = 1
        elif sql.startswith("INSERT INTO transactions"):
            transaction_id = len(self.state.transactions) + 1
            self.lastrowid = transaction_id
            self.state.transactions.append({
                "id": transaction_id,
                "household_id": params[0],
                "member_id": params[1],
                "receipt_id": params[2],
                "occurred_on": params[3],
                "merchant": params[4],
                "total_amount": params[5],
                "category_id": params[6],
                "status": "DRAFT",
            })
        elif sql.startswith("UPDATE receipts SET status = %s"):
            status, merchant, warnings, digest, receipt_id = params
            if receipt_id == self.state.receipt["id"]:
                self.state.receipt.update({
                    "status": status,
                    "merchant_raw": merchant,
                    "warnings": json.loads(warnings),
                    "content_sha256": digest,
                    "error_code": None,
                })
                self.rowcount = 1
        elif sql.startswith("INSERT INTO receipts"):
            self.lastrowid = 20
            self.state.receipt = {
                "id": 20,
                "household_id": params[0],
                "uploader_id": params[1],
                "s3_key": params[2],
                "status": "PROCESSING",
                "created_at": datetime(2026, 10, 19, 9),
                "content_sha256": None,
            }
        elif sql.startswith("UPDATE receipts SET status = 'FAILED'"):
            code, receipt_ref = params
            self.state.failures.append((code, receipt_ref))
            if receipt_ref in (self.state.receipt["id"], self.state.receipt["s3_key"]):
                self.state.receipt.update(status="FAILED", error_code=code)
                self.rowcount = 1
        else:
            raise AssertionError(f"Unexpected SQL: {sql}")

    def executemany(self, sql, rows):
        assert "INSERT INTO transaction_items" in sql
        self.state.items.extend(rows)

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class FakeDatabase:
    def __init__(self, state):
        self.state = state

    def cursor(self):
        return FakeCursor(self.state)

    def commit(self):
        self.state.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


class FakeS3:
    def __init__(self, data):
        self.data = data
        self.requests = []

    def get_object(self, **kwargs):
        self.requests.append(kwargs)
        return {"Body": io.BytesIO(self.data)}


class FakeSqs:
    def __init__(self, body, receive_count=1):
        self.body = body
        self.receive_count = receive_count
        self.deletes = []

    def receive_message(self, **kwargs):
        assert kwargs == {
            "QueueUrl": "https://sqs.example.test/receipts",
            "MaxNumberOfMessages": 1,
            "WaitTimeSeconds": 20,
            "AttributeNames": ["ApproximateReceiveCount"],
        }
        return {"Messages": [{
            "MessageId": "message-1",
            "ReceiptHandle": "receipt-1",
            "Attributes": {"ApproximateReceiveCount": str(self.receive_count)},
            "Body": json.dumps(self.body),
        }]}

    def delete_message(self, **kwargs):
        self.deletes.append(kwargs)


@pytest.fixture
def worker_state(monkeypatch):
    monkeypatch.setattr(llm, "MIN_INTERVAL", 0)
    image = io.BytesIO()
    Image.new("RGB", (20, 10), "white").save(image, format="JPEG")
    state = FakeState()
    s3 = FakeS3(image.getvalue())
    config = {
        "DB_HOST": "localhost",
        "DB_PORT": 3307,
        "DB_USER": "root",
        "DB_PASSWORD": "devpass",
        "DB_NAME": "homewallet",
        "DB_SSL_CA": None,
        "AWS_REGION": "ap-southeast-1",
        "S3_BUCKET": "receipt-bucket",
    }
    monkeypatch.setattr(pipeline, "connect", lambda _config: FakeDatabase(state))
    monkeypatch.setattr(pipeline, "load_config", lambda: config)
    monkeypatch.setattr(
        pipeline.boto3,
        "client",
        lambda service, **_kwargs: s3 if service == "s3" else pytest.fail(service),
    )
    monkeypatch.setattr(pipeline, "invalidate_dashboard", lambda _household: None)
    return state, s3, config


def invoice(**overrides):
    result = {
        "merchant": "Tiệm ăn",
        "date": "19/10/2026",
        "total": "200.000",
        "items": [{
            "description": "Món ăn",
            "quantity": 2,
            "unit_price": "100.000",
            "amount": "200.000",
            "category": "Ăn uống",
        }],
    }
    result.update(overrides)
    return result


def fake_gemini(monkeypatch, response, *, failures=()):
    calls = []

    class Models:
        def generate_content(self, **kwargs):
            calls.append(kwargs)
            if len(calls) <= len(failures):
                raise failures[len(calls) - 1]
            return SimpleNamespace(text=response)

    fake_client = SimpleNamespace(models=Models())
    monkeypatch.setattr(llm.genai, "Client", lambda **_kwargs: fake_client)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    return calls


def run_sqs(body, *, receive_count=1):
    sqs = FakeSqs(body, receive_count)
    worker.poll_once(sqs, "https://sqs.example.test/receipts")
    return sqs


def s3_event(key="receipts%2Freceipt+one.jpg"):
    return {"Records": [{
        "s3": {
            "bucket": {"name": "receipt-bucket"},
            "object": {"key": key},
        },
    }]}


def test_valid_gemini_response_creates_draft_and_deletes_message(
    monkeypatch, worker_state, capsys
):
    state, s3, _ = worker_state
    invalidated = []
    monkeypatch.setattr(pipeline, "invalidate_dashboard", invalidated.append)
    calls = fake_gemini(monkeypatch, json.dumps(invoice()))

    sqs = run_sqs(s3_event())

    assert len(calls) == 1
    assert "Ăn uống, Chưa phân loại" in calls[0]["contents"][1]
    assert "household" not in calls[0]["contents"][1].lower()
    assert s3.requests == [{
        "Bucket": "receipt-bucket",
        "Key": "receipts/receipt one.jpg",
    }]
    assert state.transactions == [{
        "id": 1,
        "household_id": 3,
        "member_id": 7,
        "receipt_id": 12,
        "occurred_on": "2026-10-19",
        "merchant": "Tiệm ăn",
        "total_amount": 200000,
        "category_id": 2,
        "status": "DRAFT",
    }]
    assert state.items == [(1, "Món ăn", 2.0, 100000, 200000, 2)]
    assert state.receipt["status"] == "DRAFT_READY"
    assert invalidated == [3]
    assert json.loads(capsys.readouterr().out)["event"] == "sqs_message"
    assert len(sqs.deletes) == 1


def test_invalid_json_leaves_message_for_retry(monkeypatch, worker_state, capsys):
    state, _, _ = worker_state
    fake_gemini(monkeypatch, "{invalid")

    sqs = run_sqs(s3_event())

    assert sqs.deletes == []
    assert state.receipt["status"] == "PROCESSING"
    assert json.loads(capsys.readouterr().out)["event"] == "sqs_message_failed"


def test_gemini_429_retries_after_google_suggested_wait(monkeypatch, worker_state):
    waits = []
    response = json.dumps(invoice())
    error = errors.APIError(429, {"message": "Please retry in 0.01s"})
    calls = fake_gemini(monkeypatch, response, failures=(error,))
    monkeypatch.setattr(llm.time, "sleep", waits.append)

    result = llm.extract_invoice(
        b"image",
        "image/jpeg",
        ["Ăn uống"],
    )

    assert result == invoice()
    assert len(calls) == 2
    assert waits == pytest.approx([2.01])


def test_gemini_503_retries(monkeypatch, worker_state):
    response = json.dumps(invoice())
    error = errors.APIError(503, {"message": "Please retry in 0.01s"})
    calls = fake_gemini(monkeypatch, response, failures=(error,))
    monkeypatch.setattr(llm, "MIN_INTERVAL", 0)
    monkeypatch.setattr(llm.time, "sleep", lambda _delay: None)

    result = llm.extract_invoice(b"image", "image/jpeg", ["Ăn uống"])

    assert result == invoice()
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("raw", "expected_warning", "expected_status"),
    [
        (invoice(total="199.000"), None, "DRAFT_READY"),
        (invoice(total="190.000", items=[{
            "description": "Món ăn",
            "quantity": 1,
            "amount": "100.000",
            "category": "Ăn uống",
        }]), "TOTAL_MISMATCH", "NEEDS_REVIEW"),
        (invoice(date=None), "DATE_MISSING", "NEEDS_REVIEW"),
    ],
)
def test_br1_and_date_rules(monkeypatch, worker_state, raw, expected_warning, expected_status):
    state, _, _ = worker_state
    fake_gemini(monkeypatch, json.dumps(raw))

    run_sqs(s3_event())

    warnings = state.receipt["warnings"]
    if expected_warning:
        assert expected_warning in warnings
    else:
        assert "TOTAL_MISMATCH" not in warnings
    assert state.receipt["status"] == expected_status
    assert state.transactions[0]["occurred_on"] == "2026-10-19"


def test_unknown_category_uses_uncategorized_category(monkeypatch, worker_state):
    state, _, _ = worker_state
    raw = invoice(items=[{
        "description": "Món lạ",
        "quantity": 1,
        "unit_price": "200.000",
        "amount": "200.000",
        "category": "Danh mục không tồn tại",
    }])
    fake_gemini(monkeypatch, json.dumps(raw))

    run_sqs(s3_event())

    assert state.transactions[0]["category_id"] == 9
    assert state.items[0][-1] == 9


def test_invoice_date_more_than_one_day_ahead_uses_upload_date():
    result = pipeline.normalize_invoice(
        invoice(date="22/10/2026"),
        [
            {"id": 2, "name": "Ăn uống"},
            {"id": 9, "name": "Chưa phân loại"},
        ],
        datetime(2026, 10, 19, 9),
        today=datetime(2026, 10, 20).date(),
    )

    assert result["occurred_on"] == "2026-10-19"
    assert result["warnings"] == ["DATE_MISSING"]
    assert result["status"] == "NEEDS_REVIEW"


def test_duplicate_receipt_message_does_not_create_two_drafts(
    monkeypatch, worker_state
):
    state, _, _ = worker_state
    calls = fake_gemini(monkeypatch, json.dumps(invoice()))

    first = run_sqs(s3_event())
    second = run_sqs(s3_event())

    assert len(state.transactions) == 1
    assert len(calls) == 1
    assert len(first.deletes) == len(second.deletes) == 1


def test_duplicate_image_adds_only_duplicate_file_warning(monkeypatch, worker_state):
    state, s3, _ = worker_state
    state.duplicate_hashes.add(hashlib.sha256(s3.data).hexdigest())
    fake_gemini(monkeypatch, json.dumps(invoice()))

    run_sqs(s3_event())

    assert state.receipt["warnings"] == ["DUPLICATE_FILE"]


def test_s3_test_event_is_deleted_without_db_or_s3(monkeypatch, worker_state):
    state, s3, _ = worker_state
    monkeypatch.setattr(
        pipeline,
        "connect",
        lambda *_args, **_kwargs: pytest.fail("TestEvent must not connect to DB"),
    )

    sqs = run_sqs({"Service": "Amazon S3", "Event": "s3:TestEvent"})

    assert state.transactions == []
    assert s3.requests == []
    assert len(sqs.deletes) == 1


def test_missing_receipt_is_logged_and_message_deleted(monkeypatch, worker_state, capsys):
    _, _, _ = worker_state
    monkeypatch.setattr(pipeline, "_receipt_for_reference", lambda *_args: None)
    sqs = run_sqs(s3_event())

    event = json.loads(capsys.readouterr().out)
    assert event["result"]["results"][0]["not_found"] is True
    assert len(sqs.deletes) == 1


def test_third_failure_marks_receipt_failed_and_does_not_delete(
    monkeypatch, worker_state, capsys
):
    state, _, config = worker_state
    fake_gemini(monkeypatch, "{invalid")
    sqs = FakeSqs(s3_event(), receive_count=3)

    with pytest.raises(ValueError, match="invalid JSON"):
        worker.poll_once(sqs, "https://sqs.example.test/receipts", config=config)

    assert sqs.deletes == []
    assert state.receipt["status"] == "FAILED"
    assert state.receipt["error_code"] == "WORKER_MAX_ATTEMPTS"
    assert state.failures == [("WORKER_MAX_ATTEMPTS", "receipts/receipt one.jpg")]
    assert json.loads(capsys.readouterr().out)["receive_count"] == 3


def test_local_file_mode_processes_real_image_with_db_but_no_s3(
    monkeypatch, worker_state, tmp_path
):
    state, _, _ = worker_state
    path = tmp_path / "receipt.jpg"
    Image.new("RGB", (8, 8), "white").save(path)
    fake_gemini(monkeypatch, json.dumps(invoice()))
    monkeypatch.setattr(
        pipeline.boto3,
        "client",
        lambda *_args, **_kwargs: pytest.fail("local mode must not create S3 client"),
    )

    result = pipeline.process_file(path, household_id=3, user_id=7)

    assert result["status"] == "DRAFT_READY"
    assert state.transactions[0]["member_id"] == 7
    assert len(state.transactions) == 1


def test_local_file_gemini_error_marks_the_created_receipt_failed(
    monkeypatch, worker_state, tmp_path
):
    state, _, _ = worker_state
    path = tmp_path / "receipt.jpg"
    Image.new("RGB", (8, 8), "white").save(path)
    fake_gemini(monkeypatch, "{invalid")

    with pytest.raises(ValueError, match="invalid JSON"):
        pipeline.process_file(path, household_id=3, user_id=7)

    assert state.receipt["status"] == "FAILED"
    assert state.receipt["error_code"] == "LOCAL_PROCESSING_FAILED"
