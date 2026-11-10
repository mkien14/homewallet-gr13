"""Bounded AWS runtime harness; email transport is intercepted, never sent.

Executed in the existing backend image by run-chi43-runtime-acceptance.py.
Only fixture selection and job-key namespaces are overridden; job bodies,
MySQL queries within each fixture, report rendering, notifications, and claims
use the deployed code. This is not Scheduler or SES delivery acceptance.
"""

import argparse
import contextlib
import io
import json
import os
import re
from datetime import date, datetime, timezone
from unittest.mock import patch


def emit(event, **fields):
    print(json.dumps({"event": event, "at_utc": datetime.now(timezone.utc).isoformat(),
                      **fields}, ensure_ascii=True), flush=True)


def require(condition, label):
    if not condition:
        raise RuntimeError(label)


def rows(db, query, params=()):
    with db.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()


def insert(db, query, params):
    with db.cursor() as cur:
        cur.execute(query, params)
        return int(cur.lastrowid)


def seed_browser_notification(db):
    target = rows(db, "SELECT u.id FROM users u JOIN household_members m ON m.user_id=u.id "
                  "WHERE u.id=16 AND m.household_id=12 AND m.role='owner'")
    require(len(target) == 1, "controlled_browser_user_mismatch")
    payload = {"title": "Thông báo nghiệm thu #43", "body":
               "Đây là thông báo thử nghiệm riêng. Bấm để kiểm tra trạng thái đã đọc.",
               "deep_link": "/notifications", "event_type": "acceptance_test"}
    key = "chi43:controlled-ui-read:20261110:user:16"
    insert(db, "INSERT INTO notifications (user_id,type,channel,payload_json,event_key) "
           "VALUES (16,'acceptance_test','in_app',%s,%s) ON DUPLICATE KEY UPDATE id=id",
           (json.dumps(payload, ensure_ascii=False), key))
    db.commit()
    notification = rows(db, "SELECT id,read_at FROM notifications WHERE user_id=16 AND event_key=%s", (key,))[0]
    return {"user_id": 16, "notification_id": notification["id"],
            "unread": notification["read_at"] is None, "event_key": key}


def scope_guard(db, args):
    require(re.fullmatch(r"[a-f0-9]{12}", args.run_id) is not None, "invalid_run_id")
    require(args.household_id > 0 and args.vi_user_id > 0 and args.en_user_id > 0,
            "invalid_fixture_ids")
    emit("CHI43_RUNTIME_PHASE", phase="scope_household")
    household = rows(db, "SELECT id,name,owner_user_id FROM households WHERE id=%s", (args.household_id,))
    require(len(household) == 1 and household[0]["name"] == "CHI43 runtime " + args.run_id,
            "fixture_household_mismatch")
    require(household[0]["owner_user_id"] == args.vi_user_id, "fixture_owner_mismatch")
    emit("CHI43_RUNTIME_PHASE", phase="scope_members")
    members = rows(db, "SELECT u.id,u.email,u.preferred_locale FROM users u "
                   "JOIN household_members m ON m.user_id=u.id WHERE m.household_id=%s ORDER BY u.id",
                   (args.household_id,))
    expected = {args.vi_user_id: ("vi", "chi43-" + args.run_id + ".vi@example.com"),
                args.en_user_id: ("en", "chi43-" + args.run_id + ".en@example.com")}
    require({x["id"] for x in members} == set(expected), "fixture_members_mismatch")
    for member in members:
        locale, email = expected[member["id"]]
        require(member["email"] == email and member["preferred_locale"] == locale,
                "fixture_identity_or_locale_mismatch")
    emit("CHI43_RUNTIME_PHASE", phase="scope_push")
    require(not rows(db, "SELECT id FROM push_subscriptions WHERE user_id IN (%s,%s)",
                     (args.vi_user_id, args.en_user_id)), "unexpected_fixture_push_subscription")
    return household[0], members


class EmailCapture:
    """An explicit transport boundary; no boto3 SES client is constructed."""

    def __init__(self, members):
        self.allowed = {m["email"]: m["preferred_locale"] for m in members}
        self.calls = []

    def send_email(self, **message):
        recipients = message["Destination"].get("BccAddresses", [])
        require(recipients and set(recipients) <= set(self.allowed), "unexpected_capture_recipient")
        locale = self.allowed[recipients[0]]
        require(all(self.allowed[x] == locale for x in recipients), "mixed_locale_delivery")
        require(set(message["Destination"]) == {"BccAddresses"}, "email_not_bcc_only")
        subject = message["Message"]["Subject"]
        body = message["Message"]["Body"]["Text"]
        require(subject["Charset"] == body["Charset"] == "UTF-8", "email_charset_mismatch")
        value = subject["Data"]
        expected = {
            "vi": ("HomeWallet: Báo cáo chi tiêu tuần", "Nhắc hạn hóa đơn:", "Cảnh báo ngân sách"),
            "en": ("HomeWallet: Weekly spending report", "Upcoming bill reminder:", "Budget alert"),
        }
        require(value.startswith(expected[locale]), "subject_locale_mismatch")
        self.calls.append({"locale": locale, "subject": value, "body": body["Data"]})
        return {"MessageId": "INTERCEPTED-NOT-SENT"}


def setup_financial_fixture(db, args):
    hh = args.household_id
    require(not rows(db, "SELECT id FROM transactions WHERE household_id=%s", (hh,)),
            "fixture_already_has_transactions")
    category = insert(db, "INSERT INTO categories (household_id,name,is_fixed) VALUES (%s,%s,0)",
                      (hh, "CHI43 synthetic category"))
    budget = insert(db, "INSERT INTO budgets (household_id,period,income_estimate,savings_goal,source,status) "
                    "VALUES (%s,'2026-11',1000000,0,'MANUAL','ACTIVE')", (hh,))
    insert(db, "INSERT INTO budget_lines (budget_id,category_id,amount) VALUES (%s,%s,1000000)",
           (budget, category))
    bill = insert(db, "INSERT INTO recurring_bills "
                  "(household_id,name,category_id,due_day,expected_amount,remind_days_before,active) "
                  "VALUES (%s,%s,%s,12,100000,2,1)", (hh, "CHI43 synthetic bill", category))
    transactions = []
    for user, occurred, amount, status in [
        (args.vi_user_id, "2026-11-03", 600000, "CONFIRMED"),
        (args.en_user_id, "2026-11-04", 300000, "CONFIRMED"),
        (args.vi_user_id, "2026-11-04", 9999999, "DRAFT"),
        (args.vi_user_id, "2026-11-09", 45000, "CONFIRMED"),
        (args.en_user_id, "2026-12-01", 222222, "CONFIRMED"),
    ]:
        transactions.append(insert(db, "INSERT INTO transactions "
            "(household_id,member_id,occurred_on,total_amount,category_id,status,source,note) "
            "VALUES (%s,%s,%s,%s,%s,%s,'MANUAL',%s)",
            (hh, user, occurred, amount, category, status, "CHI43 synthetic " + args.run_id)))
    db.commit()
    return category, bill, transactions


def prepare(db, config, args):
    require(config["DB_USER"] != "hw_runtime" and bool(os.getenv("RUNTIME_DB_PASSWORD")),
            "bootstrap_admin_required")
    scope_guard(db, args)
    expected = {"SELECT", "INSERT", "UPDATE", "DELETE"}
    privileges = rows(db, "SELECT PRIVILEGE_TYPE FROM information_schema.TABLE_PRIVILEGES "
                      "WHERE TABLE_SCHEMA='homewallet' AND TABLE_NAME='push_subscriptions' "
                      "AND GRANTEE=%s", ("'hw_runtime'@'%'",))
    missing = sorted(expected - {x["PRIVILEGE_TYPE"] for x in privileges})
    if missing:
        with db.cursor() as cur:
            cur.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON homewallet.push_subscriptions TO 'hw_runtime'@'%'")
    from app.db import connect
    runtime_config = dict(config, DB_USER="hw_runtime", DB_PASSWORD=os.environ["RUNTIME_DB_PASSWORD"])
    probe = connect(runtime_config)
    try:
        rows(probe, "SELECT 1 FROM push_subscriptions LIMIT 0")
    finally:
        probe.close()
    emit("CHI43_PUSH_GRANTS_RECONCILED", table="homewallet.push_subscriptions",
         account="hw_runtime", missing_privileges_before=missing, runtime_select_verified=True,
         contract="backend/db/bootstrap/runtime-grants.sql")
    category, bill, transactions = setup_financial_fixture(db, args)
    emit("CHI43_FIXTURE_PREPARED", run_id=args.run_id, household_id=args.household_id,
         category_id=category, bill_id=bill, transaction_count=len(transactions),
         browser_notification=seed_browser_notification(db))


def exercise(db, config, args):
    from jobs import recurring_alerts as alerts, weekly_report as weekly

    household, members = scope_guard(db, args)
    require(config["DB_USER"] == "hw_runtime", "runtime_account_required")
    category = rows(db, "SELECT id FROM categories WHERE household_id=%s AND name=%s",
                    (args.household_id, "CHI43 synthetic category"))
    txns = rows(db, "SELECT id FROM transactions WHERE household_id=%s ORDER BY id", (args.household_id,))
    require(len(category) == 1 and len(txns) == 5, "prepared_fixture_mismatch")
    txns = [x["id"] for x in txns]
    capture = EmailCapture(members)
    prefix = "CHI43_" + args.run_id + "_"

    def active_bills(conn):
        return rows(conn, "SELECT id,household_id,name,due_day,expected_amount,remind_days_before "
                    "FROM recurring_bills WHERE active=1 AND household_id=%s ORDER BY id", (args.household_id,))

    def active_budget_spending(conn, period):
        require(period == "2026-11", "unexpected_budget_period")
        return rows(conn, "SELECT b.household_id,bl.category_id,c.name AS category_name,bl.amount AS budget_amount,"
                    "COALESCE(SUM(t.total_amount),0) AS spent FROM budgets b "
                    "JOIN budget_lines bl ON bl.budget_id=b.id JOIN categories c ON c.id=bl.category_id "
                    "LEFT JOIN transactions t ON t.household_id=b.household_id AND t.category_id=bl.category_id "
                    "AND t.status='CONFIRMED' AND t.occurred_on>=%s AND t.occurred_on<%s "
                    "WHERE b.period=%s AND b.status='ACTIVE' AND b.household_id=%s "
                    "GROUP BY b.household_id,bl.category_id,c.name,bl.amount ORDER BY b.household_id,bl.category_id",
                    (date(2026, 11, 1), date(2026, 12, 1), period, args.household_id))

    from jobs.job_runs import claim_job_run, finish_job_run
    def claim(conn, name, key):
        return claim_job_run(conn, prefix + name, key)

    def finish(conn, name, key, status):
        return finish_job_run(conn, prefix + name, key, status)

    # Reject accidental external transport creation even if a code path changes.
    def no_aws_client(*_args, **_kwargs):
        raise RuntimeError("external_aws_client_creation_blocked")

    config = dict(config, SES_FROM_ADDRESS="homewallet26@gmail.com")
    checks = []
    report = weekly.build_weekly_report_data(db, args.household_id, date(2026, 11, 2), date(2026, 11, 9))
    require(report["transaction_count"] == 2 and report["total_amount"] == 900000,
            "report_totals_or_bounds_mismatch")
    require(len(report["by_category"]) == 1 and len(report["by_member"]) == 2,
            "report_breakdown_mismatch")
    checks.append("report_confirmed_only_week_bounds_category_member_totals")
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(alerts, "_list_active_bills", active_bills))
        stack.enter_context(patch.object(alerts, "_active_budget_spending", active_budget_spending))
        stack.enter_context(patch.object(weekly, "_list_households", lambda _db: [household]))
        for module, claim_name, finish_name in [(alerts, "_claim_job_run", "_finish_job_run"),
                                               (weekly, "claim_job_run", "finish_job_run")]:
            stack.enter_context(patch.object(module, claim_name, claim))
            stack.enter_context(patch.object(module, finish_name, finish))
        stack.enter_context(patch("boto3.client", no_aws_client))
        # Production logs may describe job outcomes; emit only the assertions below.
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
        first = weekly.run_weekly_reports(config=config, ses_client=capture, period_key="2026-11-02", db=db)
        second = weekly.run_weekly_reports(config=config, ses_client=capture, period_key="2026-11-02", db=db)
        require(first["sent"] == 1 and first["failed"] == 0 and second["sent"] == 0 and second["skipped"] == 1,
                "weekly_report_idempotency_failed")
        require(len(capture.calls) == 2 and all("900.000 VND" in x["body"] for x in capture.calls),
                "weekly_report_capture_mismatch")
        checks.append("weekly_report_vi_en_render_and_same_key_skip")
        reminder = alerts.run_recurring_reminders(config=config, ses_client=capture, period_key="2026-11-10", db=db)
        repeated = alerts.run_recurring_reminders(config=config, ses_client=capture, period_key="2026-11-10", db=db)
        require(reminder["sent"] == 1 and reminder["failed"] == 0 and repeated["sent"] == 0,
                "reminder_idempotency_failed")
        require(len(capture.calls) == 4, "reminder_capture_count_mismatch")
        checks.append("recurring_reminder_vi_en_due_date_and_same_key_skip")
        spending = active_budget_spending(db, "2026-11")
        require(len(spending) == 1 and int(spending[0]["spent"]) == 945000, "budget_confirmed_only_failed")
        budget80 = alerts.run_budget_alerts(config=config, ses_client=capture, period_key="2026-11-10", db=db)
        repeated80 = alerts.run_budget_alerts(config=config, ses_client=capture, period_key="2026-11-10", db=db)
        require(budget80["sent"] == 1 and budget80["failed"] == 0 and repeated80.get("skipped") is True,
                "budget_80_or_day_skip_failed")
        with db.cursor() as cur:
            cur.execute("UPDATE transactions SET total_amount=800000 WHERE id=%s AND household_id=%s",
                        (txns[0], args.household_id))
        db.commit()
        budget100 = alerts.run_budget_alerts(config=config, ses_client=capture, period_key="2026-11-11", db=db)
        require(budget100["sent"] == 1 and budget100["skipped"] == 1 and budget100["failed"] == 0,
                "budget_100_or_duplicate_80_failed")
        require(len(capture.calls) == 8, "unexpected_email_capture_count")
        checks.append("budget_80_100_vi_en_thresholds_duplicate_suppression")

    states = rows(db, "SELECT threshold FROM alert_state WHERE household_id=%s AND period='2026-11' ORDER BY threshold",
                  (args.household_id,))
    require([x["threshold"] for x in states] == [80, 100], "persisted_alert_state_mismatch")
    notifications = rows(db, "SELECT id,user_id,payload_json,read_at FROM notifications "
                         "WHERE user_id IN (%s,%s) ORDER BY id", (args.vi_user_id, args.en_user_id))
    require(len(notifications) == 6, "notification_event_idempotency_mismatch")
    counts = {args.vi_user_id: 0, args.en_user_id: 0}
    for note in notifications:
        counts[note["user_id"]] += 1
        payload = json.loads(note["payload_json"]) if isinstance(note["payload_json"], str) else note["payload_json"]
        expected = ("Cảnh báo ngân sách", "Hóa đơn sắp đến hạn") if note["user_id"] == args.vi_user_id else ("Budget alert", "Upcoming bill reminder")
        require(payload["title"] in expected and note["read_at"] is None, "notification_locale_or_read_state_failed")
    require(set(counts.values()) == {3}, "per_user_notification_count_mismatch")
    checks.append("six_localized_in_app_notifications_no_duplicates")
    job_names = (prefix + "WEEKLY_REPORT_HH_" + str(args.household_id),
                 prefix + "RECURRING_BILL_REMINDER", prefix + "BUDGET_ALERTS")
    job_states = rows(db, "SELECT status FROM job_runs WHERE job_name IN (%s,%s,%s)", job_names)
    require(len(job_states) == 4 and all(x["status"] == "SUCCEEDED" for x in job_states), "job_terminal_states_mismatch")
    checks.append("four_namespaced_job_runs_succeeded")
    browser = seed_browser_notification(db)
    emit("CHI43_RUNTIME_EXERCISE_PASS", run_id=args.run_id, household_id=args.household_id,
         fixture_user_ids=[args.vi_user_id, args.en_user_id], checks=checks,
         fixture_notification_ids={str(user): [x["id"] for x in notifications if x["user_id"] == user] for user in counts},
         email_transport="INTERCEPTED_NOT_SENT", email_capture_calls=len(capture.calls),
         email_locales={locale: sum(x["locale"] == locale for x in capture.calls) for locale in ("vi", "en")},
         real_ses_calls=0, real_push_sends=0, scheduler_invocations=0, browser_notification=browser)


def cleanup(db, args):
    scope_guard(db, args)
    hh = args.household_id
    prefix = "CHI43_" + args.run_id + "_"
    with db.cursor() as cur:
        cur.execute("DELETE FROM notifications WHERE user_id IN (%s,%s)", (args.vi_user_id, args.en_user_id))
        cur.execute("DELETE FROM alert_state WHERE household_id=%s", (hh,))
        cur.execute("DELETE FROM job_runs WHERE job_name IN (%s,%s,%s)",
                    (prefix + "WEEKLY_REPORT_HH_" + str(hh), prefix + "RECURRING_BILL_REMINDER", prefix + "BUDGET_ALERTS"))
        cur.execute("DELETE FROM transactions WHERE household_id=%s", (hh,))
        cur.execute("DELETE bl FROM budget_lines bl JOIN budgets b ON b.id=bl.budget_id WHERE b.household_id=%s", (hh,))
        cur.execute("DELETE FROM budgets WHERE household_id=%s", (hh,))
        cur.execute("DELETE FROM recurring_bills WHERE household_id=%s", (hh,))
        cur.execute("DELETE FROM categories WHERE household_id=%s", (hh,))
        cur.execute("DELETE FROM household_members WHERE household_id=%s", (hh,))
        cur.execute("DELETE FROM households WHERE id=%s AND name=%s", (hh, "CHI43 runtime " + args.run_id))
        require(cur.rowcount == 1, "fixture_household_cleanup_mismatch")
        cur.execute("DELETE FROM audit_logs WHERE actor_id IN (%s,%s)", (args.vi_user_id, args.en_user_id))
        cur.execute("DELETE FROM users WHERE id IN (%s,%s)", (args.vi_user_id, args.en_user_id))
        require(cur.rowcount == 2, "fixture_user_cleanup_mismatch")
    db.commit()
    emit("CHI43_RUNTIME_CLEANUP_PASS", run_id=args.run_id, household_id=hh,
         fixture_users_removed=2, controlled_browser_notification_retained=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "exercise", "cleanup", "seed-browser"))
    parser.add_argument("--run-id", default="")
    parser.add_argument("--household-id", type=int, default=0)
    parser.add_argument("--vi-user-id", type=int, default=0)
    parser.add_argument("--en-user-id", type=int, default=0)
    args = parser.parse_args()
    db = None
    try:
        from app.config import load_config
        from app.db import connect
        config = load_config()
        emit("CHI43_RUNTIME_PHASE", phase="connect")
        db = connect(config)
        emit("CHI43_RUNTIME_PHASE", phase="connected")
        if args.mode == "seed-browser":
            emit("CHI43_BROWSER_NOTIFICATION_READY", **seed_browser_notification(db))
        elif args.mode == "prepare":
            prepare(db, config, args)
        elif args.mode == "exercise":
            exercise(db, config, args)
        else:
            cleanup(db, args)
        return 0
    except Exception as exc:
        if db:
            db.rollback()
        # Labels raised by this harness contain no private data. Do not expose DB/provider messages.
        label = str(exc) if type(exc) is RuntimeError and re.fullmatch(r"[a-z0-9_]+", str(exc)) else None
        code = exc.args[0] if exc.args and isinstance(exc.args[0], int) else None
        emit("CHI43_RUNTIME_FAILED", mode=args.mode, error_type=type(exc).__name__, reason=label,
             database_error_code=code)
        return 1
    finally:
        if db:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
