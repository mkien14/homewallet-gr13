from decimal import Decimal

import pytest

from app.budget_rules import suggest_budget, validate_budget


@pytest.mark.parametrize(
    "income,savings,allocations,category_ids",
    [
        (1_000_000, 200_000, {1: 300_000, 2: 500_000}, {1, 2}),
        (0, 0, {}, set()),
        (100, 100, {}, {1}),
        (100, 0, {1: 100}, {1}),
    ],
)
def test_validate_budget_accepts_valid_allocations(
    income, savings, allocations, category_ids
):
    validate_budget(income, savings, allocations, category_ids)


@pytest.mark.parametrize(
    "income,savings,allocations,category_ids",
    [
        (100, 0, {1: 50, 2: 51}, {1, 2}),
        (100, 1, {1: 100}, {1}),
        (100, 0, {9: 10}, {1, 2}),
        (-1, 0, {}, {1}),
        (100, -1, {}, {1}),
        (100, 0, {1: -1}, {1}),
        (100, 0, {1: True}, {1}),
        (100, 0, {"1": 10}, {1}),
        (True, 0, {}, {1}),
        (100, 0, {1: 10}, {True}),
    ],
)
def test_validate_budget_rejects_invalid_inputs(
    income, savings, allocations, category_ids
):
    with pytest.raises(ValueError):
        validate_budget(income, savings, allocations, category_ids)


def test_suggest_budget_averages_three_months_and_applies_factor():
    spending = [
        {1: 100_000, 2: 30_000},
        {1: 200_000},
        {1: 300_000, 2: 60_000},
    ]

    assert suggest_budget(spending, Decimal("1.1")) == {
        1: 220_000,
        2: 33_000,
    }


def test_suggest_budget_rounds_half_up_and_includes_zero_spend_months():
    assert suggest_budget([{1: 1}, {}, {}], 1) == {1: 0}
    assert suggest_budget([{1: 2}, {}, {}], 1) == {1: 1}


@pytest.mark.parametrize(
    "spending,coefficient",
    [
        ([{1: 10}, {1: 20}], 1),
        ([{1: -1}, {}, {}], 1),
        ([{"1": 10}, {}, {}], 1),
        ([{1: 10}, {}, {}], -1),
        ([{1: 10}, {}, {}], float("inf")),
        ([{1: 10}, {}, {}], "not-a-number"),
    ],
)
def test_suggest_budget_rejects_invalid_inputs(spending, coefficient):
    with pytest.raises(ValueError):
        suggest_budget(spending, coefficient)
