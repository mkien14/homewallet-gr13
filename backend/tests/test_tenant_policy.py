from unittest.mock import MagicMock

import pytest
from flask import Flask

from app import tenant_policy, users
from app.errors import ApiError


@pytest.mark.parametrize("household,allowed,admitted", [
    (2, {2, 12}, True), (12, {2, 12}, True),
    (1, {1, 2}, False), (3, {2, 12}, False),
    (None, {2}, False), (2, set(), False),
])
def test_approved_current_membership_only(monkeypatch, household, allowed, admitted):
    app = Flask(__name__)
    app.config.update(APP_ENV="production", PRODUCTION_ALLOWED_HOUSEHOLD_IDS=allowed)
    db = MagicMock()
    cursor = db.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = {"household_id": household} if household is not None else None
    monkeypatch.setattr(tenant_policy, "get_db", lambda: db)
    with app.app_context():
        if admitted:
            tenant_policy.require_approved_subject({"sub": "test-subject"})
        else:
            with pytest.raises(ApiError) as error:
                tenant_policy.require_approved_subject({"sub": "test-subject"})
            assert error.value.status == 403
    assert cursor.execute.call_count == 1
    assert cursor.execute.call_args.args[1] == ("test-subject",)
    assert cursor.execute.call_args.args[0].startswith("SELECT ")


def test_dev_onboarding_preserved(monkeypatch):
    app = Flask(__name__)
    app.config["APP_ENV"] = "dev"
    db = MagicMock()
    monkeypatch.setattr(tenant_policy, "get_db", db)
    with app.app_context():
        tenant_policy.require_approved_subject({"sub": "test-subject"})
    db.assert_not_called()


@pytest.mark.parametrize("household,admitted", [(None, True), (2, True), (999, True), (1, False)])
def test_public_onboarding_preserves_retained_boundary(monkeypatch, household, admitted):
    app = Flask(__name__)
    app.config.update(APP_ENV="production", PRODUCTION_PUBLIC_REGISTRATION=True)
    db = MagicMock()
    db.cursor.return_value.__enter__.return_value.fetchone.return_value = {"household_id": household} if household else None
    monkeypatch.setattr(tenant_policy, "get_db", lambda: db)
    with app.app_context():
        if admitted:
            tenant_policy.require_approved_subject({"sub": "new-public-user"})
        else:
            with pytest.raises(ApiError) as error:
                tenant_policy.require_approved_subject({"sub": "retained-user"})
            assert error.value.status == 403


def test_public_registration_cannot_join_retained_household(app, client, make_token, monkeypatch):
    from app import households
    app.config.update(APP_ENV="production", PRODUCTION_PUBLIC_REGISTRATION=True)
    policy_db = MagicMock()
    policy_db.cursor.return_value.__enter__.return_value.fetchone.return_value = None
    monkeypatch.setattr(tenant_policy, "get_db", lambda: policy_db)
    monkeypatch.setattr(users, "get_or_create_user", lambda *_: {"id": 999})
    monkeypatch.setattr(households, "membership", lambda *_: None)
    db = MagicMock()
    cursor = db.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = {"id": 1}
    monkeypatch.setattr(households, "get_db", lambda: db)
    response = client.post("/api/households/join", json={"invite_code": "retained"}, headers={"Authorization": "Bearer " + make_token()})
    assert response.status_code == 404
    assert all("INSERT" not in call.args[0] for call in cursor.execute.call_args_list)
    db.rollback.assert_called_once()


def test_excluded_identity_cannot_create_user(app, client, make_token, monkeypatch):
    app.config.update(APP_ENV="production", PRODUCTION_ALLOWED_HOUSEHOLD_IDS={2})
    db = MagicMock()
    db.cursor.return_value.__enter__.return_value.fetchone.return_value = {"household_id": 1}
    monkeypatch.setattr(tenant_policy, "get_db", lambda: db)
    create = MagicMock()
    monkeypatch.setattr(users, "get_or_create_user", create)
    response = client.get("/api/me", headers={"Authorization": "Bearer " + make_token()})
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "PRODUCTION_ACCESS_RESTRICTED"
    create.assert_not_called()
