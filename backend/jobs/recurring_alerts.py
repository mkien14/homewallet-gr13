import argparse
import calendar
import json
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import boto3
import pymysql

from app.config import load_config
from app.db import connect
from app.localization import group_recipients_by_locale
from app.notifications import create_household_notifications, send_push_to_users
from jobs.household_scope import approved_households, household_filter
from jobs.job_runs import claim_job_run as _claim_job_run
from jobs.job_runs import finish_job_run as _finish_job_run

JOB_TIMEZONE = "Asia/Ho_Chi_Minh"
ALERT_THRESHOLDS = (80, 100)


def _log(event, **fields):
    print(json.dumps({"event": event, **fields}, ensure_ascii=False, default=str))


def _aws_error_fields(exc):
    """Return safe AWS diagnostics without logging provider messages or PII."""
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return {}

    error = response.get("Error") or {}
    metadata = response.get("ResponseMetadata") or {}
    fields = {}
    if error.get("Code"):
        fields["aws_error_code"] = error["Code"]
    message = error.get("Message") or error.get("message")
    if isinstance(message, str) and message:
        message = re.sub(
            r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
            "[redacted-email]",
            message,
            flags=re.IGNORECASE,
        )
        fields["aws_error_message"] = message[:1000]
    if metadata.get("RequestId"):
        fields["aws_request_id"] = metadata["RequestId"]
    return fields


def _execution_date(period_key=None, timezone=JOB_TIMEZONE):
    try:
        local_zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown job timezone: {timezone}") from exc
    if period_key is None:
        return datetime.now(local_zone).date()
    try:
        parsed = date.fromisoformat(period_key)
    except ValueError as exc:
        raise ValueError("period_key must use YYYY-MM-DD") from exc
    if parsed.isoformat() != period_key:
        raise ValueError("period_key must use YYYY-MM-DD")
    return parsed


def _household_recipients(db, household_id):
    with db.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT u.email, u.preferred_locale FROM household_members m "
            "JOIN users u ON u.id = m.user_id "
            "WHERE m.household_id = %s AND u.email IS NOT NULL AND u.email <> '' "
            "ORDER BY u.email",
            (household_id,),
        )
        return cur.fetchall()


def _ses_client(config, ses_client=None):
    if ses_client is not None:
        return ses_client
    return boto3.client("ses", region_name=config.get("AWS_REGION", "ap-southeast-1"))


def _send_email(db, config, ses_client, household_id, bill, due_date):
    recipient_groups = group_recipients_by_locale(
        _household_recipients(db, household_id)
    )
    if not recipient_groups:
        _log("email_skipped_no_recipients", household_id=household_id)
        return False
    sender = config.get("SES_FROM_ADDRESS")
    if not sender:
        raise RuntimeError("SES_FROM_ADDRESS is not configured")
    for locale, recipients in recipient_groups.items():
        subject, body = _reminder_message(bill, due_date, locale)
        ses_client.send_email(
            Source=sender,
            Destination={"BccAddresses": recipients},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            },
        )
    return True


def _due_date_for_month(year, month, due_day):
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(due_day, last_day))


def _bill_is_due_for_reminder(bill, run_date):
    reminder_lead = int(bill["remind_days_before"])
    due_target = run_date + timedelta(days=reminder_lead)
    due_date = _due_date_for_month(due_target.year, due_target.month, int(bill["due_day"]))
    return due_date == due_target, due_date


def _list_active_bills(db, household_ids=None):
    scope_sql, scope_params = household_filter(household_ids, "household_id")
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, household_id, name, due_day, expected_amount, "
            "remind_days_before FROM recurring_bills WHERE active = 1"
            + scope_sql + " ORDER BY id",
            scope_params,
        )
        return cur.fetchall()


def _reminder_message(bill, due_date, locale="vi"):
    amount = int(bill["expected_amount"]) if bill["expected_amount"] is not None else None
    date_text = due_date.strftime("%d/%m/%Y")
    if locale == "en":
        amount_text = f" Estimated amount: {amount:,} VND." if amount is not None else ""
        return (
            f"Upcoming bill reminder: {bill['name']}",
            f"Your recurring bill {bill['name']} is expected to be due on "
            f"{date_text}.{amount_text}\n"
            "Open HomeWallet to review it and record the expense after payment.",
        )

    amount_text = f" Số tiền dự kiến: {amount:,} VND." if amount is not None else ""
    return (
        f"Nhắc hạn hóa đơn: {bill['name']}",
        f"Hóa đơn {bill['name']} của hộ gia đình dự kiến đến hạn ngày "
        f"{date_text}.{amount_text}\n"
        "Mở HomeWallet để xem thông tin và ghi nhận khoản chi khi thanh toán.",
    )


def _budget_alert_message(row, period, threshold, locale):
    if locale == "en":
        return (
            f"Budget alert {threshold}%: {row['category_name']}",
            f"Spending in category {row['category_name']} for period {period} has "
            f"reached the {threshold}% budget threshold. Open HomeWallet to review details.",
        )
    return (
        f"Cảnh báo ngân sách {threshold}%: {row['category_name']}",
        f"Chi tiêu danh mục {row['category_name']} trong kỳ {period} "
        f"đã đạt ngưỡng {threshold}% ngân sách. Mở HomeWallet để xem chi tiết.",
    )


def run_recurring_reminders(
    *, config=None, ses_client=None, period_key=None, timezone=JOB_TIMEZONE, db=None
):
    config = config or load_config()
    household_ids = approved_households(config)
    run_date = _execution_date(period_key, timezone)
    own_db = db is None
    db = db or connect(config)
    ses = None
    sent = skipped = failed = 0
    try:
        for bill in _list_active_bills(db, household_ids):
            due, due_date = _bill_is_due_for_reminder(bill, run_date)
            if not due:
                continue
            job_key = f"{run_date.isoformat()}:bill:{bill['id']}"
            if not _claim_job_run(db, "RECURRING_BILL_REMINDER", job_key):
                skipped += 1
                continue
            try:
                event_type = "recurring_bill_reminder"
                notification_users = create_household_notifications(
                    db,
                    bill["household_id"],
                    event_key=f"recurring-bill:{bill['id']}:{due_date.isoformat()}",
                    event_type=event_type,
                    title={
                        "vi": "Hóa đơn sắp đến hạn",
                        "en": "Upcoming bill reminder",
                    },
                    body={
                        "vi": "Một hóa đơn định kỳ sắp đến hạn. Mở HomeWallet để xem chi tiết.",
                        "en": "A recurring bill is due soon. Open HomeWallet to review it.",
                    },
                    deep_link="/recurring-bills",
                )
                push_stats = send_push_to_users(
                    db,
                    notification_users,
                    event_type=event_type,
                    deep_link="/recurring-bills",
                    config=config,
                )
                _log(
                    "push_delivery_summary",
                    event_type=event_type,
                    notification_count=len(notification_users),
                    **push_stats,
                )
                if ses is None:
                    ses = _ses_client(config, ses_client)
                delivered = _send_email(
                    db,
                    config,
                    ses,
                    bill["household_id"],
                    bill,
                    due_date,
                )
                _finish_job_run(db, "RECURRING_BILL_REMINDER", job_key, "SUCCEEDED")
                sent += int(delivered)
                skipped += int(not delivered)
            except Exception as exc:
                db.rollback()
                _finish_job_run(db, "RECURRING_BILL_REMINDER", job_key, "FAILED")
                failed += 1
                _log(
                    "recurring_reminder_failed",
                    bill_id=bill["id"],
                    period_key=run_date.isoformat(),
                    error=type(exc).__name__,
                    **_aws_error_fields(exc),
                )
        result = {
            "job": "recurring-reminders",
            "period_key": run_date.isoformat(),
            "timezone": timezone,
            "sent": sent,
            "skipped": skipped,
            "failed": failed,
        }
        _log("scheduled_job_finished", **result)
        if failed:
            raise RuntimeError(f"{failed} recurring reminder(s) failed; retry is allowed")
        return result
    finally:
        if own_db:
            db.close()


def _active_budget_spending(db, period, household_ids=None):
    scope_sql, scope_params = household_filter(household_ids, "b.household_id")
    period_start = date.fromisoformat(f"{period}-01")
    if period_start.month == 12:
        period_end = date(period_start.year + 1, 1, 1)
    else:
        period_end = date(period_start.year, period_start.month + 1, 1)
    with db.cursor() as cur:
        cur.execute(
            "SELECT b.household_id, bl.category_id, c.name AS category_name, "
            "bl.amount AS budget_amount, COALESCE(SUM(t.total_amount), 0) AS spent "
            "FROM budgets b JOIN budget_lines bl ON bl.budget_id = b.id "
            "JOIN categories c ON c.id = bl.category_id "
            "LEFT JOIN transactions t ON t.household_id = b.household_id "
            "AND t.category_id = bl.category_id AND t.status = 'CONFIRMED' "
            "AND t.occurred_on >= %s AND t.occurred_on < %s "
            "WHERE b.period = %s AND b.status = 'ACTIVE'"
            + scope_sql + " GROUP BY b.household_id, bl.category_id, c.name, bl.amount "
            "ORDER BY b.household_id, bl.category_id",
            (period_start, period_end, period) + scope_params,
        )
        return cur.fetchall()


def _thresholds_reached(spent, budget_amount):
    if budget_amount <= 0:
        return []
    return [
        threshold
        for threshold in ALERT_THRESHOLDS
        if spent * 100 >= budget_amount * threshold
    ]


def _send_budget_alert(db, ses, config, row, period, threshold):
    try:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO alert_state (household_id, period, category_id, threshold) "
                "VALUES (%s, %s, %s, %s)",
                (row["household_id"], period, row["category_id"], threshold),
            )
        recipients = group_recipients_by_locale(
            _household_recipients(db, row["household_id"])
        )
        event_type = "budget_alert"
        notification_users = create_household_notifications(
            db,
            row["household_id"],
            event_key=(
                f"budget-alert:{row['household_id']}:{period}:"
                f"{row['category_id']}:{threshold}"
            ),
            event_type=event_type,
            title={
                "vi": "Cảnh báo ngân sách",
                "en": "Budget alert",
            },
            body={
                "vi": "Một danh mục chi tiêu đã chạm ngưỡng thiết lập. Mở HomeWallet để xem chi tiết.",
                "en": "A spending category has reached its configured threshold. Open HomeWallet to review it.",
            },
            deep_link="/budgets",
            commit=False,
        )
        if recipients:
            sender = config.get("SES_FROM_ADDRESS")
            if not sender:
                raise RuntimeError("SES_FROM_ADDRESS is not configured")
            for locale, addresses in recipients.items():
                subject, body = _budget_alert_message(
                    row, period, threshold, locale
                )
                ses.send_email(
                    Source=sender,
                    Destination={"BccAddresses": addresses},
                    Message={
                        "Subject": {"Data": subject, "Charset": "UTF-8"},
                        "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
                    },
                )
        else:
            _log(
                "budget_alert_email_skipped_no_recipients",
                household_id=row["household_id"],
                category_id=row["category_id"],
                threshold=threshold,
            )
        with db.cursor() as cur:
            cur.execute(
                "UPDATE alert_state SET sent_at = CURRENT_TIMESTAMP "
                "WHERE household_id = %s AND period = %s AND category_id = %s "
                "AND threshold = %s",
                (
                    row["household_id"],
                    period,
                    row["category_id"],
                    threshold,
                ),
            )
        db.commit()
        push_stats = send_push_to_users(
            db,
            notification_users,
            event_type=event_type,
            deep_link="/budgets",
            config=config,
        )
        _log(
            "push_delivery_summary",
            event_type=event_type,
            notification_count=len(notification_users),
            **push_stats,
        )
        return True
    except pymysql.err.IntegrityError as exc:
        db.rollback()
        if exc.args and exc.args[0] == 1062:
            return False
        raise
    except Exception:
        db.rollback()
        raise


def run_budget_alerts(
    *, config=None, ses_client=None, period_key=None, timezone=JOB_TIMEZONE, db=None
):
    config = config or load_config()
    household_ids = approved_households(config)
    run_date = _execution_date(period_key, timezone)
    period = run_date.strftime("%Y-%m")
    day_key = run_date.isoformat()
    job_name = "BUDGET_ALERTS"
    own_db = db is None
    db = db or connect(config)
    try:
        if not _claim_job_run(db, job_name, day_key):
            result = {"job": "budget-alerts", "period_key": day_key, "skipped": True}
            _log("scheduled_job_skipped", **result)
            return result

        sent = skipped = failed = 0
        try:
            rows = _active_budget_spending(db, period, household_ids)
            active_rows = [row for row in rows if int(row["budget_amount"]) > 0]
            if active_rows:
                ses = _ses_client(config, ses_client)
                for row in active_rows:
                    for threshold in _thresholds_reached(
                        int(row["spent"]), int(row["budget_amount"])
                    ):
                        try:
                            delivered = _send_budget_alert(
                                db, ses, config, row, period, threshold
                            )
                            sent += int(delivered)
                            skipped += int(not delivered)
                        except Exception as exc:
                            failed += 1
                            _log(
                                "budget_alert_failed",
                                household_id=row["household_id"],
                                category_id=row["category_id"],
                                threshold=threshold,
                                period_key=day_key,
                                error=type(exc).__name__,
                                **_aws_error_fields(exc),
                            )
            status = "FAILED" if failed else "SUCCEEDED"
            _finish_job_run(db, job_name, day_key, status)
        except Exception:
            db.rollback()
            _finish_job_run(db, job_name, day_key, "FAILED")
            raise

        result = {
            "job": "budget-alerts",
            "period_key": day_key,
            "timezone": timezone,
            "sent": sent,
            "skipped": skipped,
            "failed": failed,
        }
        _log("scheduled_job_finished", **result)
        if failed:
            raise RuntimeError(f"{failed} budget alert(s) failed; retry is allowed")
        return result
    finally:
        if own_db:
            db.close()


def main():
    parser = argparse.ArgumentParser(description="Run scheduled HomeWallet alert jobs")
    parser.add_argument("job", choices=("reminders", "budget-alerts"))
    parser.add_argument("--period-key", help="Local execution date as YYYY-MM-DD")
    parser.add_argument("--timezone", default=JOB_TIMEZONE)
    args = parser.parse_args()
    if args.job == "reminders":
        run_recurring_reminders(period_key=args.period_key, timezone=args.timezone)
    else:
        run_budget_alerts(period_key=args.period_key, timezone=args.timezone)


if __name__ == "__main__":
    main()
