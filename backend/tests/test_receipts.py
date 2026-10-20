import uuid
from datetime import date, timedelta

import pytest
from botocore.exceptions import ClientError

from app import receipts, storage
from app.db import get_db


class FakeS3:
    def __init__(self):
        self.objects = set()
        self.posts = []
        self.gets = []

    def generate_presigned_post(self, Bucket, Key, Fields, Conditions, ExpiresIn):
        self.posts.append(dict(Bucket=Bucket, Key=Key, Fields=Fields,
                               Conditions=Conditions, ExpiresIn=ExpiresIn))
        return {"url": f"https://{Bucket}.s3.example/", "fields": {**Fields, "key": Key}}

    def generate_presigned_url(self, ClientMethod, Params, ExpiresIn):
        self.gets.append((ClientMethod, Params, ExpiresIn))
        return f"https://{Params['Bucket']}.s3.example/{Params['Key']}?signed"

    def head_object(self, Bucket, Key):
        if Key in self.objects:
            return {}
        raise ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject")


@pytest.fixture
def s3(db_app, monkeypatch):
    fake = FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)
    db_app.config.update(S3_BUCKET="test-bucket", MAX_RECEIPT_BYTES=5 * 1024 * 1024, PRESIGN_EXPIRES=300)
    return fake


def H(make_token, sub):
    return {"Authorization": f"Bearer {make_token(sub=sub)}"}


def with_household(c, make_token, sub, name="Nhà A"):
    return c.post("/api/households", json={"name": name}, headers=H(make_token, sub)).get_json()


def add_receipt(db_app, household_id, sub, *, status="DRAFT_READY", with_draft=False):
    with db_app.app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE cognito_sub = %s", (sub,))
            user_id = cur.fetchone()["id"]
            cur.execute(
                "INSERT INTO receipts "
                "(household_id, uploader_id, s3_key, status, warnings, merchant_raw) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (household_id, user_id, f"receipts/test/{uuid.uuid4().hex}.jpg",
                 status, '["TOTAL_MISMATCH"]', "Cửa hàng"),
            )
            receipt_id = cur.lastrowid
            transaction_id = None
            if with_draft:
                cur.execute(
                    "INSERT INTO transactions "
                    "(household_id, member_id, receipt_id, occurred_on, merchant, total_amount, "
                    "category_id, status, source) "
                    "VALUES (%s, %s, %s, '2026-10-12', 'Quán A', 147000, 1, 'DRAFT', 'OCR')",
                    (household_id, user_id, receipt_id),
                )
                transaction_id = cur.lastrowid
                cur.execute(
                    "INSERT INTO transaction_items "
                    "(transaction_id, description, quantity, unit_price, amount, category_id) "
                    "VALUES (%s, 'Cà phê', 1, 59000, 59000, 1)",
                    (transaction_id,),
                )
        db.commit()
        return receipt_id, transaction_id


def test_requires_household(db_app, s3, make_token):
    r = db_app.test_client().post("/api/receipts", json={"content_type": "image/jpeg", "size": 1000},
                                  headers=H(make_token, "sub-a"))
    assert r.status_code == 403 and r.get_json()["error"]["code"] == "NO_HOUSEHOLD"


@pytest.mark.parametrize("body", [
    {"content_type": "text/html", "size": 1000},
    {"content_type": "image/jpeg"},
    {"content_type": "image/jpeg", "size": 0},
    {"content_type": "image/jpeg", "size": 6 * 1024 * 1024},
    {"content_type": "image/jpeg", "size": "1000"},
    {"content_type": "image/jpeg", "size": True},
])
def test_validation(db_app, s3, make_token, body):
    c = db_app.test_client()
    with_household(c, make_token, "sub-a")
    r = c.post("/api/receipts", json=body, headers=H(make_token, "sub-a"))
    assert r.status_code == 422 and s3.posts == []


def test_create_ok(db_app, s3, make_token):
    c = db_app.test_client()
    hh = with_household(c, make_token, "sub-a")
    r = c.post("/api/receipts", json={"content_type": "image/jpeg", "size": 200000},
               headers=H(make_token, "sub-a"))
    assert r.status_code == 201
    body = r.get_json()
    assert body["receipt"]["status"] == "UPLOADING"

    post = s3.posts[-1]
    assert post["Key"].startswith(f"receipts/uploads/{hh['id']}/") and post["Key"].endswith(".jpg")
    assert ["content-length-range", 1, 5 * 1024 * 1024] in post["Conditions"]
    assert {"Content-Type": "image/jpeg"} in post["Conditions"]
    assert post["ExpiresIn"] == 300


def test_get_reconciles_uploaded(db_app, s3, make_token):
    c = db_app.test_client()
    with_household(c, make_token, "sub-a")
    rid = c.post("/api/receipts", json={"content_type": "image/png", "size": 1000},
                 headers=H(make_token, "sub-a")).get_json()["receipt"]["id"]

    assert c.get(f"/api/receipts/{rid}", headers=H(make_token, "sub-a")).get_json()["status"] == "UPLOADING"
    s3.objects.add(s3.posts[-1]["Key"])
    assert c.get(f"/api/receipts/{rid}", headers=H(make_token, "sub-a")).get_json()["status"] == "UPLOADED"


def test_list_receipts_paginates_and_filters_status(db_app, s3, make_token):
    c = db_app.test_client()
    household = with_household(c, make_token, "sub-a")
    first, _ = add_receipt(db_app, household["id"], "sub-a", status="FAILED")
    second, _ = add_receipt(db_app, household["id"], "sub-a")
    third, _ = add_receipt(db_app, household["id"], "sub-a")

    response = c.get(
        "/api/receipts?status=DRAFT_READY&limit=1",
        headers=H(make_token, "sub-a"),
    )
    assert response.status_code == 200
    assert response.get_json()["items"][0]["id"] == third
    assert response.get_json()["items"][0]["warnings"] == ["TOTAL_MISMATCH"]
    cursor = response.get_json()["next_cursor"]
    next_page = c.get(
        f"/api/receipts?status=DRAFT_READY&limit=1&cursor={cursor}",
        headers=H(make_token, "sub-a"),
    ).get_json()
    assert next_page["items"][0]["id"] == second
    assert next_page["next_cursor"] is None
    assert first not in [third, second]


def test_get_receipt_includes_signed_image_and_draft(db_app, s3, make_token):
    c = db_app.test_client()
    household = with_household(c, make_token, "sub-a")
    receipt_id, _ = add_receipt(db_app, household["id"], "sub-a", with_draft=True)

    response = c.get(f"/api/receipts/{receipt_id}", headers=H(make_token, "sub-a"))

    assert response.status_code == 200
    body = response.get_json()
    assert body["warnings"] == ["TOTAL_MISMATCH"]
    assert body["image_url"].endswith("?signed")
    assert body["draft"]["transaction_id"]
    assert body["draft"]["merchant"] == "Quán A"
    assert body["draft"]["items"][0]["amount"] == 59000
    assert s3.gets[-1][0] == "get_object"
    assert s3.gets[-1][1]["Key"].startswith("receipts/test/")
    assert s3.gets[-1][2] == 300


def test_confirm_receipt_updates_draft_and_invalidates_dashboard(
    db_app, s3, make_token, monkeypatch
):
    c = db_app.test_client()
    household = with_household(c, make_token, "sub-a")
    receipt_id, transaction_id = add_receipt(
        db_app, household["id"], "sub-a", with_draft=True
    )
    invalidated = []
    monkeypatch.setattr(receipts, "invalidate_dashboard", invalidated.append)
    body = {
        "merchant": "Quán đã sửa",
        "occurred_on": date.today().isoformat(),
        "total_amount": 150000,
        "category_id": 1,
        "items": [
            {"description": "Cà phê", "quantity": 2, "unit_price": 75000,
             "amount": 150000, "category_id": 1}
        ],
    }

    response = c.post(
        f"/api/receipts/{receipt_id}/confirm",
        json=body,
        headers=H(make_token, "sub-a"),
    )

    assert response.status_code == 200
    result = response.get_json()["transaction"]
    assert result["id"] == transaction_id
    assert result["status"] == "CONFIRMED"
    assert result["total_amount"] == 150000
    assert result["merchant"] == "Quán đã sửa"
    assert result["items"][0]["amount"] == 150000
    assert invalidated == [household["id"]]
    with db_app.app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT status FROM receipts WHERE id = %s", (receipt_id,))
            assert cur.fetchone()["status"] == "CONFIRMED"


@pytest.mark.parametrize(
    "body",
    [
        {"occurred_on": date.today().isoformat(), "total_amount": 0},
        {"occurred_on": date.today().isoformat(), "total_amount": True},
        {"occurred_on": (date.today() + timedelta(days=2)).isoformat(), "total_amount": 100},
        {"occurred_on": date.today().strftime("%Y%m%d"), "total_amount": 100},
    ],
)
def test_confirm_receipt_rejects_invalid_amount_or_date(
    db_app, s3, make_token, body
):
    c = db_app.test_client()
    household = with_household(c, make_token, "sub-a")
    receipt_id, _ = add_receipt(
        db_app, household["id"], "sub-a", with_draft=True
    )
    response = c.post(
        f"/api/receipts/{receipt_id}/confirm",
        json=body,
        headers=H(make_token, "sub-a"),
    )
    assert response.status_code == 422


def test_confirm_receipt_is_idempotently_rejected_after_success(db_app, s3, make_token):
    c = db_app.test_client()
    household = with_household(c, make_token, "sub-a")
    receipt_id, _ = add_receipt(
        db_app, household["id"], "sub-a", with_draft=True
    )
    body = {"occurred_on": date.today().isoformat(), "total_amount": 100}
    headers = H(make_token, "sub-a")

    assert c.post(f"/api/receipts/{receipt_id}/confirm", json=body, headers=headers).status_code == 200
    response = c.post(f"/api/receipts/{receipt_id}/confirm", json=body, headers=headers)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "ALREADY_CONFIRMED"


def test_confirm_receipt_rolls_back_both_statuses_on_failure(
    db_app, s3, make_token, monkeypatch
):
    c = db_app.test_client()
    household = with_household(c, make_token, "sub-a")
    receipt_id, transaction_id = add_receipt(
        db_app, household["id"], "sub-a", with_draft=True
    )
    monkeypatch.setitem(db_app.config, "PROPAGATE_EXCEPTIONS", False)

    def fail_payload(_db, _transaction_id):
        raise RuntimeError("forced failure before commit")

    monkeypatch.setattr(receipts, "_transaction_payload", fail_payload)
    response = c.post(
        f"/api/receipts/{receipt_id}/confirm",
        json={"occurred_on": date.today().isoformat(), "total_amount": 100},
        headers=H(make_token, "sub-a"),
    )

    assert response.status_code == 500
    with db_app.app_context():
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT status FROM receipts WHERE id = %s", (receipt_id,))
            assert cur.fetchone()["status"] == "DRAFT_READY"
            cur.execute("SELECT status FROM transactions WHERE id = %s", (transaction_id,))
            assert cur.fetchone()["status"] == "DRAFT"


def test_confirm_receipt_from_another_household_is_not_found(db_app, s3, make_token):
    c = db_app.test_client()
    household = with_household(c, make_token, "sub-a")
    receipt_id, _ = add_receipt(db_app, household["id"], "sub-a", with_draft=True)
    with_household(c, make_token, "sub-b", "Nhà B")

    response = c.post(
        f"/api/receipts/{receipt_id}/confirm",
        json={"occurred_on": date.today().isoformat(), "total_amount": 100},
        headers=H(make_token, "sub-b"),
    )
    assert response.status_code == 404


def test_cross_household_receipt_denied(db_app, s3, make_token):
    c = db_app.test_client()
    with_household(c, make_token, "sub-a", "Nhà A")
    rid = c.post("/api/receipts", json={"content_type": "image/jpeg", "size": 1000},
                 headers=H(make_token, "sub-a")).get_json()["receipt"]["id"]

    with_household(c, make_token, "sub-b", "Nhà B")
    assert c.get(f"/api/receipts/{rid}", headers=H(make_token, "sub-b")).status_code == 404
    assert c.get(f"/api/receipts/{rid}", headers=H(make_token, "sub-c")).status_code == 404