import pytest
from botocore.exceptions import ClientError

from app import storage


class FakeS3:
    def __init__(self):
        self.objects = set()
        self.posts = []

    def generate_presigned_post(self, Bucket, Key, Fields, Conditions, ExpiresIn):
        self.posts.append(dict(Bucket=Bucket, Key=Key, Fields=Fields,
                               Conditions=Conditions, ExpiresIn=ExpiresIn))
        return {"url": f"https://{Bucket}.s3.example/", "fields": {**Fields, "key": Key}}

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


def test_cross_household_receipt_denied(db_app, s3, make_token):
    c = db_app.test_client()
    with_household(c, make_token, "sub-a", "Nhà A")
    rid = c.post("/api/receipts", json={"content_type": "image/jpeg", "size": 1000},
                 headers=H(make_token, "sub-a")).get_json()["receipt"]["id"]

    with_household(c, make_token, "sub-b", "Nhà B")
    assert c.get(f"/api/receipts/{rid}", headers=H(make_token, "sub-b")).status_code == 404
    assert c.get(f"/api/receipts/{rid}", headers=H(make_token, "sub-c")).status_code == 404