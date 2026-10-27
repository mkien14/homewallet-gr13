import json

from google import genai
from google.genai import types

from .budget_rules import validate_budget


class BudgetSuggestionError(Exception):
    """The model is unavailable or returned a suggestion outside the contract."""


def _parse_allocations(text, categories, income_estimate, savings_goal):
    try:
        result = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise BudgetSuggestionError("invalid JSON") from exc
    if not isinstance(result, dict) or set(result) != {"allocations"}:
        raise BudgetSuggestionError("unexpected response schema")
    rows = result["allocations"]
    if not isinstance(rows, list):
        raise BudgetSuggestionError("allocations must be an array")

    allocations = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"category_id", "amount"}:
            raise BudgetSuggestionError("each allocation must have category_id and amount")
        category_id = row["category_id"]
        amount = row["amount"]
        if (
            not isinstance(category_id, int)
            or isinstance(category_id, bool)
            or category_id not in categories
        ):
            raise BudgetSuggestionError("unknown category")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
            raise BudgetSuggestionError("amount must be a non-negative integer")
        if category_id in allocations:
            raise BudgetSuggestionError("duplicate category")
        allocations[category_id] = amount

    try:
        validate_budget(
            income_estimate,
            savings_goal,
            allocations,
            categories.keys(),
        )
    except ValueError as exc:
        raise BudgetSuggestionError("suggestion failed budget validation") from exc
    return allocations


def suggest_with_gemini(
    *,
    period,
    income_estimate,
    savings_goal,
    categories,
    monthly_spending,
    config,
    client=None,
):
    api_key = config.get("GEMINI_API_KEY")
    model = config.get("GEMINI_MODEL")
    if not api_key or not model:
        raise BudgetSuggestionError("Gemini is not configured")

    category_rows = [
        {"category_id": category_id, "name": name}
        for category_id, name in sorted(categories.items())
    ]
    history_rows = [
        {
            "period": month,
            "spending": [
                {"category_id": category_id, "amount": amount}
                for category_id, amount in sorted(spending.items())
            ],
        }
        for month, spending in monthly_spending
    ]
    prompt = (
        "Đề xuất ngân sách tháng cho một hộ gia đình tại Việt Nam. Chỉ dùng dữ liệu "
        "tổng hợp được cung cấp; không suy diễn khoản thu nhập hoặc tạo danh mục mới. "
        "Trả về duy nhất JSON đúng schema: "
        '{"allocations":[{"category_id":1,"amount":1000000}]}. '
        "Mỗi category_id chỉ xuất hiện một lần; amount là số nguyên VND không âm. "
        "Tổng allocations không được vượt available_income. Có thể trả mảng rỗng. "
        "Không thêm markdown hay giải thích.\n"
        f"Target period: {period}\n"
        f"Income estimate: {income_estimate}\n"
        f"Savings goal: {savings_goal}\n"
        f"Available income: {income_estimate - savings_goal}\n"
        f"Valid categories: {json.dumps(category_rows, ensure_ascii=False)}\n"
        f"Confirmed monthly spending: {json.dumps(history_rows, ensure_ascii=False)}"
    )
    try:
        client = client or genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=10_000),
        )
        response = client.models.generate_content(
            model=model,
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0,
            ),
        )
    except Exception as exc:
        raise BudgetSuggestionError("Gemini request failed") from exc
    if not getattr(response, "text", None):
        raise BudgetSuggestionError("Gemini returned an empty response")
    return _parse_allocations(
        response.text,
        categories,
        income_estimate,
        savings_goal,
    )
