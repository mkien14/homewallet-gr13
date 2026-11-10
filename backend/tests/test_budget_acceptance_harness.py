"""Offline bounds for the D1 runtime harness; no AWS/DB/provider access."""

import ast
import base64
import importlib.util
import json
import lzma
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


SOURCE = Path(__file__).resolve().parents[2] / "scripts" / "budget-acceptance-runtime.py"
spec = importlib.util.spec_from_file_location("d1_runtime", SOURCE)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
RUN = "0123456789ab"


@pytest.mark.parametrize("invalid", ["", "../homewallet", "A" * 12, "1" * 13, "0;DROP DB"])
def test_schema_name_rejects_unscoped_identifiers(invalid):
    with pytest.raises(RuntimeError, match="invalid_run_id"):
        runtime.schema_name(invalid)


def test_schema_name_is_always_disposable():
    assert runtime.schema_name(RUN) == "hw_d1_0123456789ab_test"


def test_runtime_payload_fits_ecs_limit_before_resources_are_created():
    tree = ast.parse(SOURCE.read_bytes())
    tree.body.pop(0)
    packed = base64.b64encode(lzma.compress(ast.unparse(tree).encode(), preset=9)).decode()
    boot = "import base64,lzma;exec(lzma.decompress(base64.b64decode('" + packed + "')))"
    command = ["python", "-c", boot, "exercise", "--run-id", "0" * 12]
    for flag in ("--household-id", "--vi-user-id", "--en-user-id"):
        command.extend([flag, str(2**63 - 1)])
    assert len(json.dumps({"containerOverrides": [{"name": "bootstrap", "command": command, "environment": []}]})) < 8192


def message(destination):
    return {"Destination": destination, "Message": {"Subject": {
        "Data": "Cảnh báo ngân sách 80%", "Charset": "UTF-8"}}}


def test_email_capture_accepts_only_scoped_bcc_and_stores_no_body():
    capture = runtime.EmailCapture(RUN)
    result = capture.send_email(**message({"BccAddresses": [f"d1-{RUN}-1@example.test"]}))
    assert result["MessageId"] == "CAPTURED-NOT-SENT"
    assert capture.calls == [{"locale": "vi"}]


@pytest.mark.parametrize("destination", [
    {"BccAddresses": ["someone@example.test"]},
    {"ToAddresses": [f"d1-{RUN}-1@example.test"]},
    {"BccAddresses": []},
])
def test_email_capture_rejects_other_users_and_public_or_empty_destinations(destination):
    capture = runtime.EmailCapture(RUN)
    with pytest.raises(RuntimeError):
        capture.send_email(**message(destination))
    assert capture.calls == []


def test_live_model_client_is_one_attempt_bounded_and_has_no_raw_text_metadata(monkeypatch):
    import google.genai
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(
        text='{"allocations":[]}', usage_metadata=None, candidates=[])
    factory = Mock(return_value=client)
    monkeypatch.setattr(google.genai, "Client", factory)
    live = runtime.LiveModel({"GEMINI_API_KEY": "fake-not-a-secret"})
    assert factory.call_args.kwargs["http_options"].retry_options.attempts == 1
    config = SimpleNamespace(max_output_tokens=None)
    live.generate_content(model="synthetic", contents=["synthetic"], config=config)
    assert config.max_output_tokens == 1024
    with pytest.raises(RuntimeError, match="live_model_second_call_forbidden"):
        live.generate_content(model="synthetic", contents=[], config=config)
    client.models.generate_content.assert_called_once()
    assert live.meta["attempts"] == 1
    assert "text" not in live.meta


def test_scope_marker_mismatch_stops_before_any_schema_mutation(monkeypatch):
    queries = []
    def query(_db, sql, params=()):
        queries.append(sql)
        return [{"SCHEMA_NAME": runtime.schema_name(RUN)}] if "SCHEMATA" in sql else [{"run_id": "other"}]
    mutate = Mock()
    monkeypatch.setattr(runtime, "query", query)
    monkeypatch.setattr(runtime, "execute", mutate)
    with pytest.raises(RuntimeError, match="schema_scope_mismatch"):
        runtime.cleanup(Mock(), SimpleNamespace(run_id=RUN))
    mutate.assert_not_called()


def test_synthetic_model_errors_are_deterministic_without_network():
    with pytest.raises(TimeoutError):
        runtime.FakeModel(fail=True).generate_content()
    assert runtime.FakeModel("invalid").generate_content().text == "invalid"


def test_literal_mysql_percent_is_not_interpreted_as_a_bind_placeholder():
    import pymysql
    connection = pymysql.connect(defer_connect=True)
    try:
        cursor = connection.cursor()
        fake = Mock()
        fake.cursor.return_value.__enter__ = Mock(return_value=cursor)
        fake.cursor.return_value.__exit__ = Mock(return_value=False)
        executed = []
        cursor.execute = lambda sql, params=None: executed.append(cursor.mogrify(sql, params))
        runtime.execute(fake, "GRANT SELECT ON synthetic.* TO 'hw_runtime'@'%'")
        assert executed == ["GRANT SELECT ON synthetic.* TO 'hw_runtime'@'%'"]
    finally:
        connection.close()
