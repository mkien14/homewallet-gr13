"""D2 authorization/validation: real signed JWTs, no AWS or database required."""

import base64
import json

import pytest

from app import community, users


POST = {"type": "tip", "title": "Save energy", "body": "Turn off unused lights."}
ROUTES = [
    ("GET", "/api/community/posts"),
    ("POST", "/api/community/posts"),
    ("GET", "/api/admin/community/posts"),
    ("PATCH", "/api/admin/community/posts/1"),
]


@pytest.fixture
def no_database(monkeypatch):
    def unexpected():
        pytest.fail("Rejected request must not access community data")

    monkeypatch.setattr(community, "get_db", unexpected)
    monkeypatch.setattr(
        users, "get_or_create_user",
        lambda claims, token: {"id": 1, "role": claims.get("role", "member")},
    )


def headers(make_token, *, admin=False, **claims):
    if admin:
        claims["cognito:groups"] = [community.ADMIN_GROUP]
    return {"Authorization": f"Bearer {make_token(**claims)}"}


def assert_error(response, status, code):
    assert response.status_code == status
    error = response.get_json()["error"]
    assert error["code"] == code
    assert error["request_id"] == response.headers["X-Request-Id"]
    assert error["request_id"]


@pytest.mark.parametrize("method,path", ROUTES)
def test_all_routes_require_auth(client, no_database, method, path):
    assert_error(client.open(path, method=method, json=POST), 401, "UNAUTHENTICATED")


@pytest.mark.parametrize("claims", [
    {}, {"role": "owner"}, {"role": "admin"}, {"custom:role": "admin"},
    {"cognito:groups": []}, {"cognito:groups": ["other-admins"]},
    {"cognito:groups": "homewallet-dev-admins"}, {"cognito:groups": None},
    {"cognito:groups": {"homewallet-dev-admins": True}},
])
@pytest.mark.parametrize("method,path", ROUTES[2:])
def test_only_exact_verified_group_grants_admin(
    client, no_database, make_token, claims, method, path,
):
    response = client.open(
        path, method=method, json={"status": "APPROVED"},
        headers=headers(make_token, **claims),
    )
    assert_error(response, 403, "FORBIDDEN")


@pytest.mark.parametrize("claims", [
    {"exp": 1}, {"iss": "https://untrusted.example"},
    {"client_id": "wrong-client"}, {"token_use": "id"},
])
@pytest.mark.parametrize("method,path", ROUTES[2:])
def test_admin_claim_cannot_bypass_token_verification(
    client, no_database, make_token, claims, method, path,
):
    response = client.open(path, method=method, json=POST,
                           headers=headers(make_token, admin=True, **claims))
    assert response.status_code == 401


@pytest.mark.parametrize("method,path", ROUTES[2:])
def test_editing_jwt_payload_does_not_grant_admin(
    client, no_database, make_token, method, path,
):
    head, payload, signature = make_token().split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims["cognito:groups"] = [community.ADMIN_GROUP]
    forged = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    response = client.open(path, method=method, json=POST,
                           headers={"Authorization": f"Bearer {head}.{forged}.{signature}"})
    assert_error(response, 401, "INVALID_TOKEN")


@pytest.mark.parametrize("extra", [
    {"status": "APPROVED"}, {"author_id": 99}, {"household_id": 99},
    {"role": "admin"}, {"cognito:groups": [community.ADMIN_GROUP]},
])
def test_create_rejects_privileged_or_unknown_fields(client, no_database, make_token, extra):
    response = client.post("/api/community/posts", json={**POST, **extra},
                           headers=headers(make_token))
    assert_error(response, 422, "VALIDATION")


@pytest.mark.parametrize("patch", [
    {"type": "unknown"}, {"type": []}, {"type": None},
    {"title": " "}, {"title": "x" * 121}, {"title": 123},
    {"body": "\n "}, {"body": "x" * 3001}, {"body": None},
])
def test_create_validates_content(client, no_database, make_token, patch):
    response = client.post("/api/community/posts", json={**POST, **patch},
                           headers=headers(make_token))
    assert_error(response, 422, "VALIDATION")


@pytest.mark.parametrize("field", ["type", "title", "body"])
def test_create_requires_all_fields(client, no_database, make_token, field):
    payload = {key: value for key, value in POST.items() if key != field}
    assert_error(client.post("/api/community/posts", json=payload,
                             headers=headers(make_token)), 422, "VALIDATION")


@pytest.mark.parametrize("payload", [
    {}, {"type": "tip"}, {"author_id": 2}, {"household_id": 1},
    {"title": " "}, {"title": "x" * 121}, {"title": False},
    {"body": ""}, {"body": "x" * 3001}, {"body": []},
    {"status": "approved"}, {"status": "DELETED"}, {"status": []},
    {"title": "Valid edit", "status": "INVALID"},
])
def test_admin_patch_validates_before_writing(client, no_database, make_token, payload):
    response = client.patch("/api/admin/community/posts/1", json=payload,
                            headers=headers(make_token, admin=True))
    assert_error(response, 422, "VALIDATION")


@pytest.mark.parametrize("raw", ["null", "[]", '"text"', "{broken"])
@pytest.mark.parametrize("method,path", [ROUTES[1], ROUTES[3]])
def test_writes_require_json_object(client, no_database, make_token, raw, method, path):
    response = client.open(path, method=method, data=raw, content_type="application/json",
                           headers=headers(make_token, admin=True))
    assert_error(response, 400, "BAD_REQUEST")


@pytest.mark.parametrize("status", ["", "DELETED", "ALL"])
def test_admin_filter_rejects_unknown_status(client, no_database, make_token, status):
    response = client.get("/api/admin/community/posts", query_string={"status": status},
                          headers=headers(make_token, admin=True))
    assert_error(response, 422, "VALIDATION")


@pytest.mark.parametrize("payload", [
    {"role": "admin"}, {"cognito:groups": [community.ADMIN_GROUP]},
    {"preferred_locale": "vi", "role": "admin"},
])
def test_profile_cannot_self_promote(client, no_database, make_token, payload):
    assert_error(client.patch("/api/me", json=payload, headers=headers(make_token)),
                 422, "VALIDATION")


def test_mock_role_switch_is_not_a_backend_endpoint(client, make_token, no_database):
    assert_error(client.post("/api/mock/community/admin", json={"enabled": True},
                             headers=headers(make_token)), 404, "NOT_FOUND")
