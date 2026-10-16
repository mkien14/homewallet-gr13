import jwt
import pytest

from app import auth
from app.errors import ApiError


def _code(r):
    return r.get_json()["error"]["code"]


def test_no_token(client):
    r = client.get("/api/me")
    assert r.status_code == 401 and _code(r) == "UNAUTHENTICATED"


def test_garbage_token(client):
    r = client.get("/api/me", headers={"Authorization": "Bearer abc.def.ghi"})
    assert r.status_code == 401 and _code(r) == "INVALID_TOKEN"


def test_expired_token(client, make_token):
    r = client.get("/api/me", headers={"Authorization": f"Bearer {make_token(exp=1)}"})
    assert r.status_code == 401 and _code(r) == "TOKEN_EXPIRED"


def test_wrong_issuer(client, make_token):
    r = client.get("/api/me", headers={"Authorization": f"Bearer {make_token(iss='https://evil.example')}"})
    assert r.status_code == 401


def test_wrong_client(client, make_token):
    r = client.get("/api/me", headers={"Authorization": f"Bearer {make_token(client_id='other')}"})
    assert r.status_code == 401


def test_id_token_rejected(client, make_token):
    r = client.get("/api/me", headers={"Authorization": f"Bearer {make_token(token_use='id')}"})
    assert r.status_code == 401


def test_hs256_token_rejected(client, make_token):
    token = make_token(key="x" * 40, algorithm="HS256")
    r = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_valid_token(app, make_token):
    claims = auth.verify_token(make_token(), app.config)
    assert claims["sub"] == "sub-a"


def test_unconfigured_server(make_token):
    with pytest.raises(ApiError) as e:
        auth.verify_token(make_token(), {"COGNITO_ISSUER": None, "COGNITO_CLIENT_IDS": []})
    assert e.value.status == 500