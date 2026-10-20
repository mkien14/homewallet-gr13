from app.parsing import parse_date, parse_vnd


def test_parse_vnd_supports_vietnamese_amount_formats():
    assert parse_vnd("245.000 ₫") == 245000
    assert parse_vnd("245,000 VND") == 245000
    assert parse_vnd("245.000,00") == 245000
    assert parse_vnd(None) is None
    assert parse_vnd("không rõ") is None


def test_parse_date_supports_existing_formats_and_time_suffix():
    assert parse_date("19/10/2026") == "2026-10-19"
    assert parse_date("2026-10-19") == "2026-10-19"
    assert parse_date("19 Oct 2026") == "2026-10-19"
    assert parse_date("19/10/26 14:30") == "2026-10-19"
    assert parse_date(None) is None
    assert parse_date("31/02/2026") is None
