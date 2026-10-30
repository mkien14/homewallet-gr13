from datetime import date

from botocore.exceptions import ClientError

from jobs import weekly_report


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        self.sql.append((query, params))

    def fetchone(self):
        return self.rows.pop(0)

    def fetchall(self):
        return self.rows.pop(0)


class FakeDb:
    def __init__(self, rows):
        self.cursor_instance = FakeCursor(rows)

    def cursor(self):
        return self.cursor_instance


class FakeSes:
    def __init__(self):
        self.calls = []

    def send_email(self, **kwargs):
        self.calls.append(kwargs)


def test_week_bounds_uses_previous_complete_monday_to_sunday_week():
    assert weekly_report._week_bounds("2026-10-26") == (
        date(2026, 10, 26),
        date(2026, 11, 2),
    )


def test_period_key_must_be_monday():
    try:
        weekly_report._week_bounds("2026-10-29")
    except ValueError as exc:
        assert str(exc) == "period_key must be the Monday starting the report week"
    else:
        raise AssertionError("Expected a non-Monday period key to be rejected")


def test_report_data_queries_confirmed_transactions_in_household_and_week():
    db = FakeDb(
        [
            {"transaction_count": 2, "total_amount": 1250000},
            [
                {
                    "category_id": 1,
                    "name": "Ăn uống",
                    "transaction_count": 2,
                    "total_amount": 1250000,
                }
            ],
            [
                {
                    "user_id": 7,
                    "display_name": "An",
                    "transaction_count": 2,
                    "total_amount": 1250000,
                }
            ],
        ]
    )

    result = weekly_report.build_weekly_report_data(
        db, 7, date(2026, 10, 26), date(2026, 11, 2)
    )

    assert result["transaction_count"] == 2
    assert result["total_amount"] == 1250000
    assert result["by_category"][0]["name"] == "Ăn uống"
    assert result["by_member"][0]["display_name"] == "An"
    assert len(db.cursor_instance.sql) == 3
    for query, params in db.cursor_instance.sql:
        assert "household_id = %s" in query
        assert "status = 'CONFIRMED'" in query
        assert params == (7, date(2026, 10, 26), date(2026, 11, 2))


def test_report_email_formats_vnd_and_confirmed_notice():
    subject, body = weekly_report._report_email(
        "Nhà A",
        {
            "transaction_count": 2,
            "total_amount": 1250000,
            "by_category": [
                {
                    "name": "Ăn uống",
                    "transaction_count": 2,
                    "total_amount": 1250000,
                }
            ],
            "by_member": [
                {
                    "display_name": "An",
                    "transaction_count": 2,
                    "total_amount": 1250000,
                }
            ],
        },
        date(2026, 10, 26),
        date(2026, 11, 2),
    )

    assert "26/10/2026–01/11/2026" in subject
    assert "1.250.000 VND" in body
    assert "chỉ bao gồm giao dịch đã xác nhận" in body


def test_send_report_uses_bcc_and_utf8():
    ses = FakeSes()
    weekly_report._send_report(
        {"SES_FROM_ADDRESS": "sender@example.test"},
        ses,
        {"name": "Nhà A"},
        {
            "transaction_count": 1,
            "total_amount": 100000,
            "by_category": [],
            "by_member": [],
        },
        ["an@example.test", "binh@example.test"],
        date(2026, 10, 26),
        date(2026, 11, 2),
    )

    message = ses.calls[0]
    assert message["Source"] == "sender@example.test"
    assert message["Destination"] == {
        "BccAddresses": ["an@example.test", "binh@example.test"]
    }
    assert message["Message"]["Subject"]["Charset"] == "UTF-8"
    assert message["Message"]["Body"]["Text"]["Charset"] == "UTF-8"


def test_aws_error_fields_expose_ses_code_without_recipient():
    error = ClientError(
        {
            "Error": {
                "Code": "MessageRejected",
                "Message": "Email address is not verified",
            }
        },
        "SendEmail",
    )

    assert weekly_report._aws_error_fields(error) == {
        "aws_error_code": "MessageRejected",
        "aws_error_message": "Email address is not verified",
    }
