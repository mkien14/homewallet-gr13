from collections.abc import Collection, Mapping, Sequence
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _non_negative_integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def validate_budget(
    income_estimate: int,
    savings_goal: int,
    allocations: Mapping[int, int],
    valid_category_ids: Collection[int],
) -> None:
    """Validate category allocations and savings against estimated household income."""
    income_estimate = _non_negative_integer(income_estimate, "income_estimate")
    savings_goal = _non_negative_integer(savings_goal, "savings_goal")
    if not isinstance(allocations, Mapping):
        raise ValueError("allocations must map category IDs to integer amounts")
    if not isinstance(valid_category_ids, Collection):
        raise ValueError("valid_category_ids must be a collection")

    if any(
        not isinstance(category_id, int)
        or isinstance(category_id, bool)
        or category_id <= 0
        for category_id in valid_category_ids
    ):
        raise ValueError("valid_category_ids must contain positive integer IDs")
    valid_ids = set(valid_category_ids)
    allocated_total = 0
    for category_id, amount in allocations.items():
        if (
            not isinstance(category_id, int)
            or isinstance(category_id, bool)
            or category_id <= 0
            or category_id not in valid_ids
        ):
            raise ValueError(f"invalid category ID: {category_id}")
        allocated_total += _non_negative_integer(
            amount, f"allocation for category {category_id}"
        )

    if allocated_total + savings_goal > income_estimate:
        raise ValueError("category allocations plus savings_goal exceed income_estimate")


def suggest_budget(
    monthly_spending: Sequence[Mapping[int, int]],
    coefficient: Decimal | int | float | str,
) -> dict[int, int]:
    """Return category budgets from exactly three months of spending and an explicit factor."""
    if (
        not isinstance(monthly_spending, Sequence)
        or isinstance(monthly_spending, (str, bytes))
        or len(monthly_spending) != 3
    ):
        raise ValueError("monthly_spending must contain exactly three months")
    try:
        factor = Decimal(str(coefficient))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("coefficient must be a finite non-negative number") from exc
    if not factor.is_finite() or factor < 0:
        raise ValueError("coefficient must be a finite non-negative number")

    totals = {}
    for month in monthly_spending:
        if not isinstance(month, Mapping):
            raise ValueError("each month must map category IDs to spending amounts")
        for category_id, amount in month.items():
            if (
                not isinstance(category_id, int)
                or isinstance(category_id, bool)
                or category_id <= 0
            ):
                raise ValueError(f"invalid category ID: {category_id}")
            totals[category_id] = totals.get(category_id, 0) + _non_negative_integer(
                amount, f"spending for category {category_id}"
            )

    suggested = {}
    for category_id, total in totals.items():
        average = Decimal(total) / Decimal(3)
        try:
            adjusted_amount = (average * factor).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        except InvalidOperation as exc:
            raise ValueError("suggested amount is outside the supported numeric range") from exc
        suggested[category_id] = int(adjusted_amount)
    return suggested
