"""Offline checks for the optional one-mailbox acceptance; never sends mail."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


SOURCE = Path(__file__).resolve().parents[2] / "scripts" / "budget-mailbox-runtime.py"
spec = importlib.util.spec_from_file_location("d1_mail_runtime", SOURCE)
mail = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mail)
RUN = "0123456789ab"
DAY = "2026-11-10"


def queries(_db, sql, params=None):
    if "_d1_mail_scope" in sql:
        return [{"run_id": RUN, "period_key": DAY}]
    if sql == "SELECT * FROM job_runs":
        return []
    if "FROM users" in sql or "FROM notifications" in sql:
        return [{"id": 1}]
    if "FROM push_subscriptions" in sql:
        return []
    if "FROM job_runs WHERE status='SUCCEEDED'" in sql:
        return [{"status": "SUCCEEDED"}]
    if "FROM alert_state" in sql:
        return [{"threshold": 80}]
    raise AssertionError(sql)


def child(event, **extra):
    data = dict(event=event, job="budget-alerts", period_key=DAY, **extra)
    return SimpleNamespace(returncode=0, stdout=json.dumps(data) + "\n")


def test_real_mail_mode_runs_identical_cli_twice_and_second_is_skipped(monkeypatch):
    monkeypatch.setattr(mail, "query", queries)
    run = Mock(side_effect=[child("scheduled_job_finished", sent=1, failed=0),
                            child("scheduled_job_skipped", skipped=True)])
    monkeypatch.setattr(mail.subprocess, "run", run)
    mail.exercise(Mock(), SimpleNamespace(run_id=RUN))
    assert run.call_count == 2
    assert run.call_args_list[0].args == run.call_args_list[1].args
    assert run.call_args.kwargs["env"]["DB_NAME"] == "hw_d1_mail_0123456789ab_test"
    assert run.call_args.kwargs["env"]["VAPID_PRIVATE_KEY"] == ""
    assert run.call_args.kwargs["timeout"] == 45


def test_claimed_job_prevents_another_delivery_attempt(monkeypatch):
    def existing(db, sql, params=None):
        return [{"status": "SUCCEEDED"}] if sql == "SELECT * FROM job_runs" else queries(db, sql, params)
    monkeypatch.setattr(mail, "query", existing)
    run = Mock()
    monkeypatch.setattr(mail.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="mail_attempt_already_claimed"):
        mail.exercise(Mock(), SimpleNamespace(run_id=RUN))
    run.assert_not_called()


def test_failed_or_unknown_first_result_never_starts_second_cli(monkeypatch):
    monkeypatch.setattr(mail, "query", queries)
    run = Mock(return_value=SimpleNamespace(returncode=1, stdout=""))
    monkeypatch.setattr(mail.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="cli_failed_or_result_unknown"):
        mail.exercise(Mock(), SimpleNamespace(run_id=RUN))
    run.assert_called_once()


@pytest.mark.parametrize("recipient", ["", "two@example.test\nother@example.test", "not-an-email"])
def test_invalid_recipient_stops_before_schema_creation(monkeypatch, recipient):
    mutate = Mock()
    monkeypatch.setattr(mail, "execute", mutate)
    with pytest.raises(RuntimeError, match="invalid_recipient"):
        mail.prepare(Mock(), SimpleNamespace(run_id=RUN, recipient=recipient))
    mutate.assert_not_called()


@pytest.mark.parametrize("run", ["", "../homewallet", "ABCDEF123456"])
def test_mail_schema_rejects_unscoped_names(run):
    with pytest.raises(RuntimeError, match="invalid_run_id"):
        mail.schema(run)


def test_mail_cleanup_requires_its_scope_marker(monkeypatch):
    def foreign(_db, sql, params=None):
        return [{"SCHEMA_NAME": "present"}] if "SCHEMATA" in sql else [{"run_id": "other", "period_key": DAY}]
    mutate = Mock()
    monkeypatch.setattr(mail, "query", foreign)
    monkeypatch.setattr(mail, "execute", mutate)
    with pytest.raises(RuntimeError, match="scope_mismatch"):
        mail.cleanup(Mock(), SimpleNamespace(run_id=RUN))
    mutate.assert_not_called()


def test_existing_mail_evidence_refuses_another_run_before_aws_or_recipient_prompt(monkeypatch, tmp_path):
    driver_spec = importlib.util.spec_from_file_location("d1_mail_driver", SOURCE.with_name("run-budget-mailbox-acceptance.py"))
    driver = importlib.util.module_from_spec(driver_spec)
    driver_spec.loader.exec_module(driver)
    output = tmp_path / "evidence.json"
    output.write_text("original", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["mail", "--output", str(output)])
    runner, prompt = Mock(), Mock()
    monkeypatch.setattr(driver.shared, "Runner", runner)
    monkeypatch.setattr(driver.getpass, "getpass", prompt)
    with pytest.raises(FileExistsError):
        driver.main()
    runner.assert_not_called()
    prompt.assert_not_called()
    assert output.read_text(encoding="utf-8") == "original"
