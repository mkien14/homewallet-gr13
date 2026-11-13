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
