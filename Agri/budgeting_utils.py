from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation


def _coerce_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                pass
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            pass
    return None


def calculate_week_start(planting_date, relational_week):
    planting = _coerce_date(planting_date)
    if planting is None:
        return None
    relational_week = int(relational_week or 0)
    planting_week_start = planting - timedelta(days=planting.weekday())
    return planting_week_start + timedelta(days=relational_week * 7)


def continuous_week_range(saved_weeks, initial_start=-2, initial_end=12):
    weeks = [int(week) for week in saved_weeks if week is not None]
    start_week = min([initial_start, *weeks])
    end_week = max([initial_end, *weeks])
    return list(range(start_week, end_week + 1))


def budget_week_periods(saved_week_starts):
    stored_starts = {}
    for relational_week, week_start in saved_week_starts.items():
        normalized_week_start = _coerce_date(week_start)
        if relational_week is not None and normalized_week_start is not None:
            stored_starts[int(relational_week)] = normalized_week_start
    if not stored_starts:
        return []

    first_week = min(stored_starts)
    last_week = max(stored_starts)
    weeks = []
    for relational_week in range(first_week, last_week + 1):
        if relational_week in stored_starts:
            week_start = stored_starts[relational_week]
        else:
            anchor_week = min(stored_starts, key=lambda saved_week: abs(saved_week - relational_week))
            week_start = stored_starts[anchor_week] + timedelta(days=(relational_week - anchor_week) * 7)
        weeks.append((relational_week, week_start))

    return [
        {
            "relational_week": relational_week,
            "week_start": week_start,
            "next_week_start": weeks[index + 1][1] if index + 1 < len(weeks) else week_start + timedelta(days=7),
        }
        for index, (relational_week, week_start) in enumerate(weeks)
    ]


def effective_budget_hectares(budgeted_hectares, project_hectares):
    value = budgeted_hectares if budgeted_hectares is not None else project_hectares
    return float(value or 0)


def expense_value_from_transaction_sign(transaction_value):
    return -float(_to_decimal(transaction_value))


def format_iso_week_label(value):
    d = _coerce_date(value)
    if d is None:
        return "-"
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _to_decimal(value, default=Decimal("0")):
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def budget_line_total_cost(quantity_per_ha, budget_ha, unit_price):
    total = _to_decimal(quantity_per_ha) * _to_decimal(budget_ha) * _to_decimal(unit_price)
    return float(total)


def budget_line_cost_per_ha(quantity_per_ha, unit_price):
    return float(_to_decimal(quantity_per_ha) * _to_decimal(unit_price))
