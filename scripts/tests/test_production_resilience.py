import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def resilience():
    spec = importlib.util.spec_from_file_location(
        "resilience_gate", Path(__file__).parents[1] / "production-resilience-check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def evidence(tmp_path):
    record = {
        "status": "PASS", "at_utc": datetime.now(timezone.utc).isoformat(),
        "account": "123456789012", "region": "ap-southeast-1", "image_digest": "sha256:" + "b" * 64,
        "release": "a" * 40, "database_id": "current-db", "source_overwritten": False,
        "backup_lag_seconds": 120, "temporary_resources_cleaned": True,
        "restore": {k: {"application_ready": True, "tls_verified": True,
                         "schema_cleaned": True, "seconds": 1700} for k in ("pitr", "snapshot")},
        "drills": {k: {"pass": True} for k in (
            "api_task_replacement", "database_failover", "redis_failover", "api_rollback")},
    }
    path = tmp_path / "evidence.json"
    settings = {"resilience_evidence_path": str(path), "release": "a" * 40, "database_id": "current-db",
                "account": "123456789012", "region": "ap-southeast-1", "release_image_digest": "sha256:" + "b" * 64}
    return settings, path, record


def test_complete_dated_evidence_passes(resilience, evidence):
    settings, path, record = evidence
    path.write_text(json.dumps(record))
    assert resilience.recovery_evidence_valid(settings)


@pytest.mark.parametrize("case", ["missing", "stale", "future", "wrong_db", "wrong_release",
                                 "source_overwritten", "slow_restore", "app_unready", "tls_off",
                                 "unclean", "failed_drill", "backup_lag", "invalid_timestamp",
                                 "wrong_account", "wrong_region", "wrong_image"])
def test_incomplete_or_unscoped_evidence_fails(resilience, evidence, case):
    settings, path, record = evidence
    record = copy.deepcopy(record)
    if case == "missing":
        assert not resilience.recovery_evidence_valid(settings)
        return
    if case in {"stale", "future"}:
        delta = timedelta(days=-31 if case == "stale" else 1)
        record["at_utc"] = (datetime.now(timezone.utc) + delta).isoformat()
    elif case == "wrong_db": record["database_id"] = "other-db"
    elif case == "wrong_release": record["release"] = "b" * 40
    elif case == "source_overwritten": record["source_overwritten"] = True
    elif case == "slow_restore": record["restore"]["pitr"]["seconds"] = 3601
    elif case == "app_unready": record["restore"]["snapshot"]["application_ready"] = False
    elif case == "tls_off": record["restore"]["pitr"]["tls_verified"] = False
    elif case == "unclean": record["temporary_resources_cleaned"] = False
    elif case == "failed_drill": record["drills"]["database_failover"]["pass"] = False
    elif case == "backup_lag": record["backup_lag_seconds"] = 901
    elif case == "invalid_timestamp": record["at_utc"] = "unrecorded"
    elif case == "wrong_account": record["account"] = "999999999999"
    elif case == "wrong_region": record["region"] = "us-east-1"
    elif case == "wrong_image": record["image_digest"] = "sha256:" + "c" * 64
    path.write_text(json.dumps(record))
    assert not resilience.recovery_evidence_valid(settings)


def test_signoff_cannot_replace_live_inventory(resilience):
    session = Mock()
    checks = resilience.evaluate({"resilience_signoff": True}, session, {})
    assert checks == [{"gate": "resilience_inventory_complete", "pass": False}]
    session.client.assert_not_called()
