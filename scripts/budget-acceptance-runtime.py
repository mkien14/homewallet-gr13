"""D1 integration on one disposable MySQL schema; no real email/push transport."""

import argparse
import contextlib
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def emit(event, **fields):
    print(json.dumps(dict(event="D1_" + event, at_utc=datetime.now(timezone.utc).isoformat(),
                          **fields), ensure_ascii=True), flush=True)


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def query(db, sql, params=None):
    with db.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def execute(db, sql, params=None):
    with db.cursor() as cur:
        cur.execute(sql, params)


def schema_name(run_id):
    require(re.fullmatch(r"[a-f0-9]{12}", run_id) is not None, "invalid_run_id")
    return "hw_d1_" + run_id + "_test"


def scope(db, name, run_id):
    require(query(db, f"SELECT run_id FROM `{name}`._d1_scope") == [{"run_id": run_id}],
            "schema_scope_mismatch")


def prepare(db, args):
    from jobs.migrate import MIG, statements
    name = schema_name(args.run_id)
    require(not query(db, "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s", (name,)),
            "schema_already_exists")
    execute(db, f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    execute(db, f"USE `{name}`")
    execute(db, "CREATE TABLE _d1_scope (run_id CHAR(12) PRIMARY KEY)")
    execute(db, "INSERT INTO _d1_scope VALUES (%s)", (args.run_id,))
    db.commit()
    for migration in sorted(MIG.glob("*.sql")):
        for statement in statements(migration.read_text(encoding="utf-8-sig")):
            if not statement.upper().startswith(("CREATE DATABASE", "USE ")):
                execute(db, statement)
    for uid, locale in ((1, "vi"), (2, "en"), (3, "vi")):
        execute(db, "INSERT INTO users (id,cognito_sub,email,display_name,preferred_locale) VALUES (%s,%s,%s,'D1 synthetic',%s)",
                (uid, f"d1-{args.run_id}-{uid}", f"d1-{args.run_id}-{uid}@example.test", locale))
    for hid, owner in ((1, 1), (2, 3)):
        execute(db, "INSERT INTO households (id,name,owner_user_id,invite_code) VALUES (%s,'D1 synthetic',%s,%s)",
                (hid, owner, f"D1{hid}{args.run_id}"))
    for hid, uid, role in ((1, 1, "owner"), (1, 2, "member"), (2, 3, "owner")):
        execute(db, "INSERT INTO household_members (household_id,user_id,role) VALUES (%s,%s,%s)", (hid, uid, role))
    for cid, hid, label in ((101, 1, "D1 Food"), (102, 1, "D1 Transport"), (103, 2, "D1 Other household")):
        execute(db, "INSERT INTO categories (id,household_id,name) VALUES (%s,%s,%s)", (cid, hid, label))
    for hid, uid, day, amount, status, cid in (
        (1, 1, "2026-07-10", 900000, "CONFIRMED", 101),
        (1, 2, "2026-09-10", 300000, "CONFIRMED", 102),
        (1, 1, "2026-08-10", 9999999, "DRAFT", 101),
        (1, 1, "2026-11-02", 9999999, "DRAFT", 101),
        (1, 1, "2026-12-01", 9999999, "CONFIRMED", 101),
        (2, 3, "2026-11-02", 9999999, "CONFIRMED", 103),
    ):
        execute(db, "INSERT INTO transactions (household_id,member_id,occurred_on,total_amount,status,category_id,source) "
                "VALUES (%s,%s,%s,%s,%s,%s,'MANUAL')", (hid, uid, day, amount, status, cid))
    db.commit()
    execute(db, f"GRANT SELECT,INSERT,UPDATE,DELETE ON `{name}`.* TO 'hw_runtime'@'%'")
    emit("PREPARED", schema=name, migrations_applied=len(list(MIG.glob("*.sql"))),
         grants_scope="disposable_schema_only", production_grants_changed=False)


def snapshot(db):
    db.commit()
    result = [query(db, "SELECT * FROM budgets ORDER BY id"),
              query(db, "SELECT * FROM budget_lines ORDER BY budget_id,category_id")]
    return hashlib.sha256(json.dumps(result, sort_keys=True, default=str).encode()).hexdigest()


class FakeModel:
    def __init__(self, response=None, fail=False):
        self.models = self
        self.response, self.fail = response, fail

    def generate_content(self, **_kwargs):
        if self.fail:
            raise TimeoutError("synthetic failure")
        return SimpleNamespace(text=self.response)


class LiveModel:
    def __init__(self, config):
        from google import genai
        from google.genai import types
        self.models, self.meta = self, {"attempts": 0, "sdk_total_attempts": 1, "max_output_tokens": 1024}
        self.client = genai.Client(api_key=config["GEMINI_API_KEY"], http_options=types.HttpOptions(
            timeout=10000, retry_options=types.HttpRetryOptions(attempts=1)))

    def generate_content(self, **kwargs):
        require(self.meta["attempts"] == 0, "live_model_second_call_forbidden")
        self.meta["attempts"] = 1
        kwargs["config"].max_output_tokens = 1024
        emit("GEMINI_ATTEMPT_STARTED", attempts=1, synthetic_aggregates_only=True)
        try:
            response = self.client.models.generate_content(**kwargs)
            usage = response.usage_metadata
            self.meta.update(input_tokens=getattr(usage, "prompt_token_count", None),
                             output_tokens=getattr(usage, "candidates_token_count", None),
                             thought_tokens=getattr(usage, "thoughts_token_count", None),
                             finish_reason=str(response.candidates[0].finish_reason) if response.candidates else None)
            return response
        except Exception as exc:
            code = getattr(exc, "code", None)
            self.meta.update(error_type=type(exc).__name__, http_status=code if isinstance(code, int) else None)
            raise


class EmailCapture:
    def __init__(self, run_id):
        self.addresses = {f"d1-{run_id}-{uid}@example.test" for uid in (1, 2)}
        self.calls = []

    def send_email(self, **message):
        recipients = message["Destination"]
        require(set(recipients) == {"BccAddresses"} and set(recipients["BccAddresses"]) <= self.addresses,
                "email_recipient_scope_failed")
        require(len(recipients["BccAddresses"]) == 1, "email_locale_group_mismatch")
        subject = message["Message"]["Subject"]
        require(subject["Charset"] == "UTF-8", "email_charset_failed")
        require(subject["Data"].startswith(("Cảnh báo ngân sách", "Budget alert")), "email_subject_failed")
        self.calls.append({"locale": "vi" if subject["Data"].startswith("Cảnh báo") else "en"})
        return {"MessageId": "CAPTURED-NOT-SENT"}


def exercise(db, config, args):
    from flask import g
    from app import budgets
    from app.budget_suggestions import suggest_with_gemini
    from app.main import create_app
    from jobs import recurring_alerts as alerts

    scope(db, config["DB_NAME"], args.run_id)
    app = create_app(dict(config, TESTING=True))
    checks = []
    def record(case, **fields):
        checks.append(dict(case=case, status="PASS", **fields))

    def suggest(case, period, model, expected, income=1000000, savings=200000, allocations=None):
        before = snapshot(db)
        def invoke(**kwargs):
            return suggest_with_gemini(**kwargs, client=model)
        with app.test_request_context("/api/budgets/" + period + "/suggest", method="POST",
                                      json={"income_estimate": income, "savings_goal": savings}):
            g.user = {"id": 1}
            with patch.object(budgets, "get_db", lambda: db), patch.object(budgets, "suggest_with_gemini", invoke):
                response = budgets.suggest_budget_for_period.__wrapped__(period)
            value = response.get_json()["suggestion"]
        require(value["source"] == expected and value["status"] == "DRAFT", "suggestion_source_or_status_failed")
        require(sum(x["amount"] for x in value["allocations"]) <= income - savings, "suggestion_budget_exceeded")
        require(snapshot(db) == before, "suggestion_persisted_without_save")
        if allocations is not None:
            require({x["category_id"]: x["amount"] for x in value["allocations"]} == allocations,
                    "fallback_allocations_failed")
        record(case, source=expected, draft_only=True, saved_state_unchanged=True)
        return value

    history = budgets._historical_spending(db, 1, "2026-10")
    require(history == [{101: 900000}, {}, {102: 300000}], "three_month_history_scope_failed")
    record("HISTORY-three-months-confirmed-only-missing-month-zero")
    fake_config = dict(app.config)
    app.config["GEMINI_API_KEY"] = "synthetic-not-a-real-key"
    app.config["GEMINI_MODEL"] = config.get("GEMINI_MODEL") or "synthetic-model"
    suggest("SUG-valid-llm-output", "2026-10", FakeModel('{"allocations":[{"category_id":101,"amount":300000}]}'), "LLM")
    for case, model in (
        ("SUG-timeout-fallback", FakeModel(fail=True)),
        ("SUG-invalid-json-fallback", FakeModel("invalid")),
        ("SUG-unknown-category-fallback", FakeModel('{"allocations":[{"category_id":99999,"amount":1}]}')),
        ("SUG-foreign-category-fallback", FakeModel('{"allocations":[{"category_id":103,"amount":1}]}')),
        ("SUG-duplicate-category-fallback", FakeModel('{"allocations":[{"category_id":101,"amount":1},{"category_id":101,"amount":2}]}')),
        ("SUG-negative-amount-fallback", FakeModel('{"allocations":[{"category_id":101,"amount":-1}]}')),
        ("SUG-overallocation-fallback", FakeModel('{"allocations":[{"category_id":101,"amount":800001}]}')),
        ("SUG-empty-response-fallback", FakeModel("")),
    ):
        suggest(case, "2026-10", model, "RULE", allocations={101: 300000, 102: 100000})
    suggest("SUG-fallback-scales-to-income", "2026-10", FakeModel(fail=True), "RULE",
            income=300000, savings=100000, allocations={101: 150000, 102: 50000})
    suggest("SUG-no-history-empty-draft", "2027-04", FakeModel(fail=True), "RULE", allocations={})
    app.config.update(fake_config)
    live_meta = {"status": "NOT_CONFIGURED", "attempts": 0}
    if config.get("GEMINI_API_KEY") and config.get("GEMINI_MODEL"):
        live = LiveModel(config)
        try:
            before = snapshot(db)
            # Use the actual route body and its normal fallback, with one bounded client.
            def invoke_live(**kwargs):
                return suggest_with_gemini(**kwargs, client=live)
            with app.test_request_context("/api/budgets/2026-10/suggest", method="POST",
                                          json={"income_estimate": 1000000, "savings_goal": 200000}):
                g.user = {"id": 1}
                with patch.object(budgets, "get_db", lambda: db), patch.object(budgets, "suggest_with_gemini", invoke_live):
                    value = budgets.suggest_budget_for_period.__wrapped__("2026-10").get_json()["suggestion"]
            require(value["status"] == "DRAFT" and snapshot(db) == before, "live_suggestion_persisted")
            live_meta = dict(live.meta, status="PASS" if value["source"] == "LLM" else "PROVIDER_OR_OUTPUT_BLOCKED",
                             response_source=value["source"], model=config["GEMINI_MODEL"], raw_text_saved=False)
        finally:
            live.client.close()
    emit("LIVE_LLM_RESULT", **live_meta)
    record("SUG-fallback-and-draft-contract", branch_cases=11)
    capture = EmailCapture(args.run_id)
    execute(db, "INSERT INTO budgets (household_id,period,income_estimate,savings_goal,source,status) "
            "VALUES (1,'2026-11',1000000,0,'MANUAL','ACTIVE')")
    bid = query(db, "SELECT id FROM budgets WHERE household_id=1 AND period='2026-11'")[0]["id"]
    execute(db, "INSERT INTO budget_lines (budget_id,category_id,amount) VALUES (%s,101,1000000),(%s,102,0)", (bid, bid))
    execute(db, "INSERT INTO transactions (household_id,member_id,occurred_on,total_amount,status,category_id,source,note) "
            "VALUES (1,1,'2026-11-05',0,'CONFIRMED',101,'MANUAL','D1 threshold')")
    db.commit()
    job_cases = []
    def no_aws(*_args, **_kwargs):
        raise RuntimeError("unexpected_aws_transport")
    with patch("boto3.client", no_aws), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        for index, (amount, count) in enumerate(((799999, 0), (800000, 1), (999999, 1), (1000000, 2), (1000001, 2))):
            day = f"2026-11-{10 + index}"
            execute(db, "UPDATE transactions SET total_amount=%s WHERE household_id=1 AND note='D1 threshold'", (amount,))
            db.commit()
            spending = alerts._active_budget_spending(db, "2026-11")
            require(next(x["spent"] for x in spending if x["category_id"] == 101) == amount, "job_confirmed_or_period_scope_failed")
            first = alerts.run_budget_alerts(config=dict(config, VAPID_PRIVATE_KEY=None,
                SES_FROM_ADDRESS="d1-synthetic@example.test"), ses_client=capture, period_key=day, db=db)
            second = alerts.run_budget_alerts(config=config, ses_client=capture, period_key=day, db=db)
            require(first["failed"] == 0 and second.get("skipped") is True, "job_repeat_not_skipped")
            states = query(db, "SELECT threshold FROM alert_state WHERE household_id=1 ORDER BY threshold")
            require(len(states) == count and len(capture.calls) == count * 2, "threshold_or_email_duplicate_failed")
            require(len(query(db, "SELECT id FROM notifications")) == count * 2, "notification_duplicate_failed")
            job_cases.append(dict(period_key=day, spent=amount, thresholds=[x["threshold"] for x in states],
                                  cumulative_captured_emails=len(capture.calls), repeat_skipped=True))
    require(not query(db, "SELECT id FROM notifications WHERE user_id=3"), "foreign_user_notified")
    require(len(query(db, "SELECT * FROM job_runs WHERE status='SUCCEEDED'")) == 5, "job_runs_terminal_count_failed")
    require({x["locale"] for x in capture.calls} == {"vi", "en"}, "job_email_locales_failed")
    record("JOB-five-threshold-boundaries-and-repeat", period_keys=[x["period_key"] for x in job_cases])
    sources = {str(p): hashlib.sha256(Path(p).read_bytes().replace(b"\r\n", b"\n")).hexdigest() for p in (
        "app/budgets.py", "app/budget_suggestions.py", "app/budget_rules.py", "jobs/recurring_alerts.py", "jobs/job_runs.py")}
    emit("EXERCISE_PASS", checks=checks, live_llm=live_meta, job_cases=job_cases, deployed_source_sha256=sources,
         email_capture_count=len(capture.calls), real_ses_calls=0, real_push_sends=0,
         schema=config["DB_NAME"], database_user=config["DB_USER"],
         auth_scope="route-body integration; signed Cognito HTTP authorization checked separately")


def cleanup(db, args):
    name = schema_name(args.run_id)
    if query(db, "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s", (name,)):
        scope(db, name, args.run_id)
        if query(db, "SELECT PRIVILEGE_TYPE FROM information_schema.SCHEMA_PRIVILEGES WHERE TABLE_SCHEMA=%s AND GRANTEE=%s",
                 (name, "'hw_runtime'@'%'")):
            execute(db, f"REVOKE SELECT,INSERT,UPDATE,DELETE ON `{name}`.* FROM 'hw_runtime'@'%'")
        execute(db, f"DROP DATABASE `{name}`")
    require(not query(db, "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s", (name,)), "schema_cleanup_failed")
    require(not query(db, "SELECT PRIVILEGE_TYPE FROM information_schema.SCHEMA_PRIVILEGES WHERE TABLE_SCHEMA=%s", (name,)),
            "temporary_grants_not_removed")
    emails = [f"d1-{args.run_id}.{role}@example.com" for role in ("owner", "member", "outsider")]
    users = query(db, "SELECT id FROM homewallet.users WHERE email IN (%s,%s,%s)", tuple(emails))
    ids = [x["id"] for x in users]
    households = []
    if ids:
        slots = ",".join(["%s"] * len(ids))
        households = query(db, f"SELECT id,name FROM homewallet.households WHERE owner_user_id IN ({slots})", tuple(ids))
        for hh in households:
            require(hh["name"] in {"D1 runtime " + args.run_id, "D1 outsider " + args.run_id}, "api_fixture_scope_mismatch")
            for table in ("transactions", "receipts", "recurring_bills", "categories"):
                require(not query(db, f"SELECT id FROM homewallet.{table} WHERE household_id=%s LIMIT 1", (hh["id"],)),
                        "unexpected_api_fixture_data")
            require(not query(db, "SELECT user_id FROM homewallet.household_members WHERE household_id=%s AND user_id NOT IN (" + slots + ")",
                              (hh["id"], *ids)), "unexpected_api_fixture_member")
        for hh in households:
            execute(db, "DELETE bl FROM homewallet.budget_lines bl JOIN homewallet.budgets b ON b.id=bl.budget_id WHERE b.household_id=%s", (hh["id"],))
            for table in ("budgets", "household_members"):
                execute(db, f"DELETE FROM homewallet.{table} WHERE household_id=%s", (hh["id"],))
            execute(db, "DELETE FROM homewallet.households WHERE id=%s", (hh["id"],))
        execute(db, f"DELETE FROM homewallet.audit_logs WHERE actor_id IN ({slots})", tuple(ids))
        execute(db, f"DELETE FROM homewallet.users WHERE id IN ({slots})", tuple(ids))
        db.commit()
    emit("CLEANUP_PASS", schema_removed=True, temporary_grants_removed=True,
         api_fixture_users_removed=len(ids), api_fixture_households_removed=len(households))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "exercise", "cleanup"))
    parser.add_argument("--run-id", required=True)
    for option in ("household-id", "vi-user-id", "en-user-id"):
        parser.add_argument("--" + option, type=int, default=0)
    args = parser.parse_args()
    schema_name(args.run_id)
    from app.config import load_config
    from app.db import connect
    config, db = load_config(), None
    try:
        require(config["DB_NAME"] == "homewallet", "unexpected_source_database")
        require((config["DB_USER"] == "hw_runtime") == (args.mode == "exercise"), "wrong_database_role")
        if args.mode == "exercise":
            config["DB_NAME"] = schema_name(args.run_id)
        db = connect(config)
        {"prepare": prepare, "exercise": lambda conn, opts: exercise(conn, config, opts), "cleanup": cleanup}[args.mode](db, args)
        return 0
    except Exception as exc:
        if db:
            db.rollback()
        label = str(exc) if type(exc) is RuntimeError and re.fullmatch(r"[a-z0-9_]+", str(exc)) else None
        emit("FAILED", mode=args.mode, error_type=type(exc).__name__, reason=label,
             numeric_error_code=exc.args[0] if exc.args and isinstance(exc.args[0], int) else None)
        return 1
    finally:
        if db:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
