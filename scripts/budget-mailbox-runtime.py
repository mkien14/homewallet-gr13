"""One real budget alert from an isolated schema, followed by the identical CLI."""

import argparse
import json
import os
import re
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def emit(event, **fields):
    print(json.dumps(dict(event="D1MAIL_" + event, **fields)), flush=True)


def query(db, sql, params=None):
    with db.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def execute(db, sql, params=None):
    with db.cursor() as cursor:
        cursor.execute(sql, params)


def schema(run):
    require(re.fullmatch(r"[0-9a-f]{12}", run) is not None, "invalid_run_id")
    return "hw_d1_mail_" + run + "_test"


def marker(db, name, run):
    result = query(db, f"SELECT run_id,period_key FROM `{name}`._d1_mail_scope")
    require(len(result) == 1 and result[0]["run_id"] == run, "scope_mismatch")
    return result[0]


def prepare(db, args):
    name = schema(args.run_id)
    require(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", args.recipient or "") is not None, "invalid_recipient")
    require(not query(db, "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s", (name,)), "schema_exists")
    execute(db, f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    execute(db, f"USE `{name}`")
    day = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
    execute(db, "CREATE TABLE _d1_mail_scope (run_id CHAR(12) PRIMARY KEY,period_key CHAR(10))")
    execute(db, "INSERT INTO _d1_mail_scope VALUES (%s,%s)", (args.run_id, day))
    db.commit()
    for table in ("users", "households", "household_members", "categories", "budgets", "budget_lines", "transactions",
                  "notifications", "push_subscriptions", "alert_state", "job_runs"):
        execute(db, f"CREATE TABLE `{table}` LIKE homewallet.`{table}`")
    execute(db, "INSERT INTO users (id,cognito_sub,email,display_name,preferred_locale) VALUES (1,%s,%s,'D1 acceptance','vi')",
            ("d1-mail-" + args.run_id, args.recipient))
    execute(db, "INSERT INTO households (id,name,owner_user_id,invite_code) VALUES (1,'D1 isolated acceptance',1,%s)", (args.run_id,))
    execute(db, "INSERT INTO household_members (household_id,user_id,role) VALUES (1,1,'owner')")
    execute(db, "INSERT INTO categories (id,household_id,name) VALUES (1,1,%s)", ("D1 Acceptance " + args.run_id[:6],))
    execute(db, "INSERT INTO budgets (id,household_id,period,income_estimate,savings_goal,source,status) VALUES (1,1,%s,1000000,0,'MANUAL','ACTIVE')", (day[:7],))
    execute(db, "INSERT INTO budget_lines (budget_id,category_id,amount) VALUES (1,1,1000000)")
    execute(db, "INSERT INTO transactions (household_id,member_id,occurred_on,total_amount,category_id,status,source) VALUES (1,1,%s,800000,1,'CONFIRMED','MANUAL')", (day,))
    db.commit()
    execute(db, f"GRANT SELECT,INSERT,UPDATE,DELETE ON `{name}`.* TO 'hw_runtime'@'%'")
    emit("PREPARED", schema=name, recipient_count=1, period_key=day, title_marker="D1 Acceptance " + args.run_id[:6])


def exercise(db, args):
    name = schema(args.run_id)
    day = marker(db, name, args.run_id)["period_key"]
    require(not query(db, "SELECT * FROM job_runs"), "mail_attempt_already_claimed")
    require(len(query(db, "SELECT id FROM users")) == 1 and not query(db, "SELECT id FROM push_subscriptions"), "unexpected_recipient_or_push")
    command = ["python", "-m", "jobs.recurring_alerts", "budget-alerts", "--period-key", day]
    environment = dict(os.environ, DB_NAME=name, VAPID_PRIVATE_KEY="")
    results = []
    for attempt in (1, 2):
        emit("CLI_STARTED", invocation=attempt, period_key=day, delivery_attempt=attempt == 1)
        child = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=45)
        events = []
        for line in child.stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("event") in {"scheduled_job_finished", "scheduled_job_skipped"}:
                events.append({key: event[key] for key in ("event", "job", "period_key", "sent", "skipped", "failed") if key in event})
        require(child.returncode == 0 and len(events) == 1, "cli_failed_or_result_unknown")
        if attempt == 1:
            require(events[0].get("sent") == 1 and events[0].get("failed") == 0, "email_not_accepted_once")
        else:
            require(events[0].get("skipped") is True, "repeat_not_skipped")
        results.append(dict(command=command, exit_code=child.returncode, result=events[0]))
    db.commit()
    require(len(query(db, "SELECT * FROM job_runs WHERE status='SUCCEEDED'")) == 1, "job_state_count_failed")
    require(query(db, "SELECT threshold FROM alert_state") == [{"threshold": 80}], "alert_state_count_failed")
    require(len(query(db, "SELECT id FROM notifications")) == 1, "notification_count_failed")
    emit("SEND_PASS", real_email_sends_accepted=1, duplicate_cli_skipped=True, period_key=day,
         cli_results=results, push_sends=0, schema=name)


def cleanup(db, args):
    name = schema(args.run_id)
    if query(db, "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s", (name,)):
        marker(db, name, args.run_id)
        if query(db, "SELECT PRIVILEGE_TYPE FROM information_schema.SCHEMA_PRIVILEGES WHERE TABLE_SCHEMA=%s AND GRANTEE=%s", (name, "'hw_runtime'@'%'")):
            execute(db, f"REVOKE SELECT,INSERT,UPDATE,DELETE ON `{name}`.* FROM 'hw_runtime'@'%'")
        execute(db, f"DROP DATABASE `{name}`")
    require(not query(db, "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s", (name,)), "schema_cleanup_failed")
    require(not query(db, "SELECT PRIVILEGE_TYPE FROM information_schema.SCHEMA_PRIVILEGES WHERE TABLE_SCHEMA=%s", (name,)), "grants_cleanup_failed")
    emit("CLEANUP_PASS", schema_removed=True, grants_removed=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "exercise", "cleanup"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--recipient")
    for name in ("household-id", "vi-user-id", "en-user-id"):
        parser.add_argument("--" + name, type=int, default=0)
    args = parser.parse_args()
    from app.config import load_config
    from app.db import connect
    config, db = load_config(), None
    try:
        require(config["DB_NAME"] == "homewallet", "unexpected_source_database")
        require((config["DB_USER"] == "hw_runtime") == (args.mode == "exercise"), "wrong_database_role")
        if args.mode == "exercise":
            config["DB_NAME"] = schema(args.run_id)
        db = connect(config)
        {"prepare": prepare, "exercise": exercise, "cleanup": cleanup}[args.mode](db, args)
        return 0
    except Exception as exc:
        if db:
            db.rollback()
        label = str(exc) if type(exc) is RuntimeError and re.fullmatch(r"[a-z0-9_]+", str(exc)) else None
        emit("FAILED", error_type=type(exc).__name__, reason=label)
        return 1
    finally:
        if db:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
