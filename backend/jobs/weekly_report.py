"""Send one household spending summary for the previous complete week."""

import argparse
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import boto3
from botocore.exceptions import ClientError

from app.config import load_config
from app.db import connect
from app.localization import group_recipients_by_locale
from jobs.job_runs import claim_job_run, finish_job_run

JOB_TIMEZONE = "Asia/Ho_Chi_Minh"
JOB_NAME_PREFIX = "WEEKLY_REPORT_HH_"


def _log(event, **fields):
    print(json.dumps({"event": event, **fields}, ensure_ascii=False, default=str))


def _week_bounds(period_key=None, timezone=JOB_TIMEZONE):
    """Return [Monday, next Monday); period_key names the report week's Monday."""
    try:
        local_zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown job timezone: {timezone}") from exc

    if period_key is None:
        today = datetime.now(local_zone).date()
        current_monday = today - timedelta(days=today.weekday())
        start = current_monday - timedelta(days=7)
    else:
        try:
            start = date.fromisoformat(period_key)
        except (TypeError, ValueError) as exc:
            raise ValueError("period_key must use YYYY-MM-DD") from exc
        if start.isoformat() != period_key:
            raise ValueError("period_key must use YYYY-MM-DD")
        if start.weekday() != 0:
            raise ValueError("period_key must be the Monday starting the report week")

    return start, start + timedelta(days=7)


def _list_households(db):
    with db.cursor() as cur:
        cur.execute("SELECT id, name FROM households ORDER BY id")
        return cur.fetchall()


def build_weekly_report_data(db, household_id, start, end):
    """Return totals and category/member breakdowns for one household week."""
    params = (household_id, start, end)
    with db.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS transaction_count, "
            "COALESCE(SUM(total_amount), 0) AS total_amount "
            "FROM transactions WHERE household_id = %s AND status = 'CONFIRMED' "
            "AND occurred_on >= %s AND occurred_on < %s",
            params,
        )
        totals = cur.fetchone()

        cur.execute(
            "SELECT t.category_id, COALESCE(c.name, 'Chưa phân loại') AS name, "
            "COUNT(*) AS transaction_count, SUM(t.total_amount) AS total_amount "
            "FROM transactions t LEFT JOIN categories c ON c.id = t.category_id "
            "WHERE t.household_id = %s AND t.status = 'CONFIRMED' "
            "AND t.occurred_on >= %s AND t.occurred_on < %s "
            "GROUP BY t.category_id, c.name "
            "ORDER BY total_amount DESC, t.category_id",
            params,
        )
        by_category = cur.fetchall()

        cur.execute(
            "SELECT t.member_id AS user_id, "
            "COALESCE(NULLIF(u.display_name, ''), "
            "CONCAT('Thành viên #', u.id)) AS display_name, "
            "COUNT(*) AS transaction_count, SUM(t.total_amount) AS total_amount "
            "FROM transactions t JOIN users u ON u.id = t.member_id "
            "WHERE t.household_id = %s AND t.status = 'CONFIRMED' "
            "AND t.occurred_on >= %s AND t.occurred_on < %s "
            "GROUP BY t.member_id, u.display_name, u.id "
            "ORDER BY total_amount DESC, t.member_id",
            params,
        )
        by_member = cur.fetchall()

    return {
        "transaction_count": int(totals["transaction_count"]),
        "total_amount": int(totals["total_amount"]),
        "by_category": [
            {
                "category_id": row["category_id"],
                "name": row["name"],
                "transaction_count": int(row["transaction_count"]),
                "total_amount": int(row["total_amount"]),
            }
            for row in by_category
        ],
        "by_member": [
            {
                "user_id": row["user_id"],
                "display_name": row["display_name"],
                "transaction_count": int(row["transaction_count"]),
                "total_amount": int(row["total_amount"]),
            }
            for row in by_member
        ],
    }


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


def _format_vnd(amount):
    return f"{int(amount):,}".replace(",", ".") + " VND"


def _report_email(household_name, report, start, end, locale="vi"):
    last_day = end - timedelta(days=1)
    if locale == "en":
        subject = (
            f"HomeWallet: Weekly spending report "
            f"{start.strftime('%d/%m/%Y')}–{last_day.strftime('%d/%m/%Y')}"
        )
        lines = [
            f"Weekly spending report for household {household_name}",
            f"Period: {start.strftime('%d/%m/%Y')} to {last_day.strftime('%d/%m/%Y')}",
            f"Total spending: {_format_vnd(report['total_amount'])}",
            f"Confirmed transactions: {report['transaction_count']}",
            "",
            "By category:",
        ]
        lines.extend(
            f"- {row['name']}: {_format_vnd(row['total_amount'])} "
            f"({row['transaction_count']} transaction(s))"
            for row in report["by_category"]
        )
        lines.extend(("", "By member:"))
        lines.extend(
            f"- {row['display_name']}: {_format_vnd(row['total_amount'])} "
            f"({row['transaction_count']} transaction(s))"
            for row in report["by_member"]
        )
        lines.extend(
            ("", "This summary includes confirmed transactions only.")
        )
        return subject, "\n".join(lines)

    subject = (
        f"HomeWallet: Báo cáo chi tiêu tuần "
        f"{start.strftime('%d/%m/%Y')}–{last_day.strftime('%d/%m/%Y')}"
    )
    lines = [
        f"Báo cáo chi tiêu tuần của hộ {household_name}",
        f"Thời gian: {start.strftime('%d/%m/%Y')} đến {last_day.strftime('%d/%m/%Y')}",
        f"Tổng chi: {_format_vnd(report['total_amount'])}",
        f"Số giao dịch đã xác nhận: {report['transaction_count']}",
        "",
        "Theo danh mục:",
    ]
    lines.extend(
        f"- {row['name']}: {_format_vnd(row['total_amount'])} "
        f"({row['transaction_count']} giao dịch)"
        for row in report["by_category"]
    )
    lines.extend(("", "Theo thành viên:"))
    lines.extend(
        f"- {row['display_name']}: {_format_vnd(row['total_amount'])} "
        f"({row['transaction_count']} giao dịch)"
        for row in report["by_member"]
    )
    lines.extend(("", "Đây là báo cáo tổng hợp; chỉ bao gồm giao dịch đã xác nhận."))
    return subject, "\n".join(lines)


def _ses_client(config, ses_client=None):
    if ses_client is not None:
        return ses_client
    return boto3.client("ses", region_name=config.get("AWS_REGION", "ap-southeast-1"))


def _send_report(config, ses, household, report, recipients, start, end):
    sender = config.get("SES_FROM_ADDRESS")
    if not sender:
        raise RuntimeError("SES_FROM_ADDRESS is not configured")
    recipient_groups = group_recipients_by_locale(recipients)
    for locale, addresses in recipient_groups.items():
        subject, body = _report_email(
            household["name"], report, start, end, locale
        )
        ses.send_email(
            Source=sender,
            Destination={"BccAddresses": addresses},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            },
        )


def _aws_error_fields(exc):
    if not isinstance(exc, ClientError):
        return {}
    error = exc.response.get("Error", {})
    return {
        "aws_error_code": error.get("Code"),
        "aws_error_message": error.get("Message"),
    }


def run_weekly_reports(
    *, config=None, ses_client=None, period_key=None, timezone=JOB_TIMEZONE, db=None
):
    config = config or load_config()
    start, end = _week_bounds(period_key, timezone)
    effective_period_key = start.isoformat()
    own_db = db is None
    db = db or connect(config)
    ses = None
    sent = skipped = failed = 0

    try:
        households = _list_households(db)
        for household in households:
            household_id = household["id"]
            report = build_weekly_report_data(db, household_id, start, end)
            if report["transaction_count"] == 0:
                skipped += 1
                _log(
                    "weekly_report_skipped",
                    household_id=household_id,
                    period_key=effective_period_key,
                    reason="no_confirmed_transactions",
                )
                continue

            recipients = _household_recipients(db, household_id)
            if not recipients:
                skipped += 1
                _log(
                    "weekly_report_skipped",
                    household_id=household_id,
                    period_key=effective_period_key,
                    reason="no_recipients",
                )
                continue

            job_name = f"{JOB_NAME_PREFIX}{household_id}"
            if not claim_job_run(db, job_name, effective_period_key):
                skipped += 1
                _log(
                    "weekly_report_skipped",
                    household_id=household_id,
                    period_key=effective_period_key,
                    reason="already_claimed_or_succeeded",
                )
                continue

            try:
                if ses is None:
                    ses = _ses_client(config, ses_client)
                _send_report(config, ses, household, report, recipients, start, end)
                finish_job_run(db, job_name, effective_period_key, "SUCCEEDED")
                sent += 1
                _log(
                    "weekly_report_sent",
                    household_id=household_id,
                    period_key=effective_period_key,
                    transaction_count=report["transaction_count"],
                )
            except Exception as exc:
                db.rollback()
                finish_job_run(db, job_name, effective_period_key, "FAILED")
                failed += 1
                _log(
                    "weekly_report_failed",
                    household_id=household_id,
                    period_key=effective_period_key,
                    error=type(exc).__name__,
                    **_aws_error_fields(exc),
                )

        result = {
            "job": "weekly-report",
            "period_key": effective_period_key,
            "period_end_exclusive": end.isoformat(),
            "timezone": timezone,
            "sent": sent,
            "skipped": skipped,
            "failed": failed,
        }
        _log("scheduled_job_finished", **result)
        if failed:
            raise RuntimeError(f"{failed} weekly report(s) failed; retry is allowed")
        return result
    finally:
        if own_db:
            db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Send weekly HomeWallet spending reports"
    )
    parser.add_argument(
        "--period-key",
        help="Monday YYYY-MM-DD starting the report week; defaults to previous full week",
    )
    parser.add_argument("--timezone", default=JOB_TIMEZONE)
    args = parser.parse_args()
    run_weekly_reports(period_key=args.period_key, timezone=args.timezone)


if __name__ == "__main__":
    main()
