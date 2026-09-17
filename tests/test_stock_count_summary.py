from datetime import date

from Inventory.routes.stock_count.stock_count_summary import evaluate_count_status, format_date_value


def test_recent_status_when_counted_recently():
    status = evaluate_count_status(date(2026, 9, 16), date(2026, 9, 30), today=date(2026, 9, 17))
    assert status["status"] == "recent"
    assert status["days_since"] == 1


def test_due_status_when_due_soon():
    status = evaluate_count_status(date(2026, 9, 1), date(2026, 9, 10), today=date(2026, 9, 9))
    assert status["status"] == "due"
    assert status["days_until"] == 1


def test_never_counted_status():
    status = evaluate_count_status(None, None, today=date(2026, 9, 17))
    assert status["status"] == "never"
    assert status["label"] == "Never counted"


def test_format_date_value_handles_date_objects_and_strings():
    assert format_date_value(date(2026, 9, 17)) == "2026-09-17"
    assert format_date_value("2026-09-17") == "2026-09-17"
    assert format_date_value(None) == "N/A"
