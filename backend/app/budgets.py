import re
from datetime import date
from decimal import Decimal

from flask import Blueprint, current_app, g, jsonify, request

from .auth import require_auth
from .budget_suggestions import BudgetSuggestionError, suggest_with_gemini
from .budget_rules import suggest_budget, validate_budget
from .db import get_db
from .errors import ApiError
from .households import json_body, membership, require_owner

bp = Blueprint("budgets", __name__, url_prefix="/api")


def _period_start(period):
    if not isinstance(period, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
        raise ApiError(422, "VALIDATION", "Kỳ ngân sách phải có dạng YYYY-MM")
    try:
        return date.fromisoformat(f"{period}-01")
    except ValueError as exc:
        raise ApiError(422, "VALIDATION", "Kỳ ngân sách không hợp lệ") from exc


def _json_integer(value, field, *, minimum=0):
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ApiError(422, "VALIDATION", f"{field} phải là số nguyên không âm")
    return value


def _parse_budget_body(data):
    if set(data) != {"income_estimate", "savings_goal", "allocations"}:
        raise ApiError(422, "VALIDATION", "Thiếu hoặc có trường ngân sách không được hỗ trợ")

    income_estimate = _json_integer(data["income_estimate"], "income_estimate")
    savings_goal = _json_integer(data["savings_goal"], "savings_goal")
    raw_allocations = data["allocations"]
    if not isinstance(raw_allocations, list):
        raise ApiError(422, "VALIDATION", "allocations phải là một danh sách")

    allocations = {}
    for allocation in raw_allocations:
        if not isinstance(allocation, dict) or set(allocation) != {"category_id", "amount"}:
            raise ApiError(422, "VALIDATION", "Mỗi phân bổ cần category_id và amount")
        category_id = _json_integer(allocation["category_id"], "category_id", minimum=1)
        amount = _json_integer(allocation["amount"], "amount")
        if category_id in allocations:
            raise ApiError(422, "VALIDATION", "Danh mục không được lặp lại")
        allocations[category_id] = amount

    return income_estimate, savings_goal, allocations


def _parse_suggestion_body(data):
    if set(data) != {"income_estimate", "savings_goal"}:
        raise ApiError(422, "VALIDATION", "Cần income_estimate và savings_goal")
    return (
        _json_integer(data["income_estimate"], "income_estimate"),
        _json_integer(data["savings_goal"], "savings_goal"),
    )


def _valid_categories(db, household_id, category_ids=None):
    query = (
        "SELECT id, name FROM categories "
        "WHERE (household_id IS NULL OR household_id = %s)"
    )
    params = [household_id]
    if category_ids is not None:
        if not category_ids:
            return {}
        placeholders = ", ".join(["%s"] * len(category_ids))
        query += f" AND id IN ({placeholders})"
        params.extend(category_ids)
    query += " ORDER BY id"
    with db.cursor() as cur:
        cur.execute(query, tuple(params))
        return {row["id"]: row["name"] for row in cur.fetchall()}


def _validate_allocations(db, household_id, income_estimate, savings_goal, allocations):
    categories = _valid_categories(db, household_id, allocations.keys())
    if set(categories) != set(allocations):
        raise ApiError(422, "VALIDATION", "Danh mục không hợp lệ")
    try:
        validate_budget(income_estimate, savings_goal, allocations, categories.keys())
    except ValueError as exc:
        raise ApiError(422, "VALIDATION", str(exc)) from exc
    return categories


def _budget_payload(db, household_id, period):
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, period, income_estimate, savings_goal, source, status "
            "FROM budgets WHERE household_id = %s AND period = %s",
            (household_id, period),
        )
        budget = cur.fetchone()
        if not budget:
            return None
        cur.execute(
            "SELECT bl.category_id, c.name, bl.amount "
            "FROM budget_lines bl JOIN categories c ON c.id = bl.category_id "
            "WHERE bl.budget_id = %s ORDER BY bl.category_id",
            (budget["id"],),
        )
        allocations = cur.fetchall()

    return {
        "period": budget["period"],
        "income_estimate": int(budget["income_estimate"]),
        "savings_goal": int(budget["savings_goal"]),
        "source": budget["source"],
        "status": budget["status"],
        "allocations": [
            {
                "category_id": row["category_id"],
                "name": row["name"],
                "amount": int(row["amount"]),
            }
            for row in allocations
        ],
    }


def _previous_periods(period):
    year, month = map(int, period.split("-"))
    month_index = year * 12 + month - 1
    periods = []
    for offset in (3, 2, 1):
        previous_index = month_index - offset
        previous_year, zero_based_month = divmod(previous_index, 12)
        previous_month = zero_based_month + 1
        periods.append(
            f"{previous_year:04d}-{previous_month:02d}" if previous_year >= 1 else None
        )
    return periods


def _historical_spending(db, household_id, period):
    periods = _previous_periods(period)
    spending = {month: {} for month in periods if month is not None}
    if not spending:
        return [{}, {}, {}]

    first_period = next(month for month in periods if month is not None)
    start = _period_start(first_period)
    end = _period_start(period)
    with db.cursor() as cur:
        cur.execute(
            "SELECT DATE_FORMAT(occurred_on, '%Y-%m') AS period, category_id, "
            "SUM(total_amount) AS amount FROM transactions "
            "WHERE household_id = %s AND status = 'CONFIRMED' "
            "AND category_id IS NOT NULL AND occurred_on >= %s AND occurred_on < %s "
            "GROUP BY period, category_id",
            (household_id, start, end),
        )
        for row in cur.fetchall():
            spending[row["period"]][row["category_id"]] = int(row["amount"])
    return [spending.get(month, {}) if month is not None else {} for month in periods]


def _fit_to_available_income(allocations, available):
    total = sum(allocations.values())
    if total <= available:
        return allocations
    if available == 0 or total == 0:
        return {category_id: 0 for category_id in allocations}

    scaled = {
        category_id: (amount * available) // total
        for category_id, amount in allocations.items()
    }
    remainder = available - sum(scaled.values())
    order = sorted(
        allocations,
        key=lambda category_id: (
            -((allocations[category_id] * available) % total),
            category_id,
        ),
    )
    for category_id in order[:remainder]:
        scaled[category_id] += 1
    return scaled


@bp.get("/budgets/<period>")
@require_auth
def get_budget(period):
    _period_start(period)
    db = get_db()
    household = membership(db, g.user["id"])
    if not household:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy")
    return jsonify(budget=_budget_payload(db, household["household_id"], period))


@bp.put("/budgets/<period>")
@require_auth
def put_budget(period):
    _period_start(period)
    db = get_db()
    household = membership(db, g.user["id"])
    if not household:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy")
    require_owner(household)
    income_estimate, savings_goal, allocations = _parse_budget_body(json_body())
    _validate_allocations(
        db, household["household_id"], income_estimate, savings_goal, allocations
    )

    try:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO budgets "
                "(household_id, period, income_estimate, savings_goal, source, status) "
                "VALUES (%s, %s, %s, %s, 'MANUAL', 'ACTIVE') AS incoming "
                "ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id), "
                "income_estimate = incoming.income_estimate, "
                "savings_goal = incoming.savings_goal, source = 'MANUAL', status = 'ACTIVE'",
                (household["household_id"], period, income_estimate, savings_goal),
            )
            created = cur.rowcount == 1
            budget_id = cur.lastrowid
            cur.execute("DELETE FROM budget_lines WHERE budget_id = %s", (budget_id,))
            if allocations:
                cur.executemany(
                    "INSERT INTO budget_lines (budget_id, category_id, amount) "
                    "VALUES (%s, %s, %s)",
                    [
                        (budget_id, category_id, amount)
                        for category_id, amount in allocations.items()
                    ],
                )
        db.commit()
    except Exception:
        db.rollback()
        raise

    payload = _budget_payload(db, household["household_id"], period)
    return jsonify(budget=payload), 201 if created else 200


@bp.post("/budgets/<period>/suggest")
@require_auth
def suggest_budget_for_period(period):
    _period_start(period)
    db = get_db()
    household = membership(db, g.user["id"])
    if not household:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy")
    require_owner(household)
    income_estimate, savings_goal = _parse_suggestion_body(json_body())
    available = income_estimate - savings_goal
    if available < 0:
        raise ApiError(
            422, "VALIDATION", "savings_goal không được lớn hơn income_estimate"
        )

    categories = _valid_categories(db, household["household_id"])
    previous_periods = _previous_periods(period)
    historical = _historical_spending(db, household["household_id"], period)
    try:
        allocations = suggest_with_gemini(
            period=period,
            income_estimate=income_estimate,
            savings_goal=savings_goal,
            categories=categories,
            monthly_spending=list(zip(previous_periods, historical)),
            config=current_app.config,
        )
        source = "LLM"
    except BudgetSuggestionError as exc:
        current_app.logger.warning(
            "budget suggestion using rule fallback (%s)", type(exc.__cause__ or exc).__name__
        )
        try:
            allocations = suggest_budget(historical, Decimal("1"))
            allocations = _fit_to_available_income(allocations, available)
            validate_budget(income_estimate, savings_goal, allocations, categories.keys())
        except ValueError as rule_error:
            raise ApiError(422, "VALIDATION", str(rule_error)) from rule_error
        source = "RULE"

    suggestion = {
        "period": period,
        "income_estimate": income_estimate,
        "savings_goal": savings_goal,
        "source": source,
        "status": "DRAFT",
        "allocations": [
            {
                "category_id": category_id,
                "name": categories[category_id],
                "amount": amount,
            }
            for category_id, amount in sorted(allocations.items())
        ],
    }
    return jsonify(suggestion=suggestion)
