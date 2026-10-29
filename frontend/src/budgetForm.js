import { parseVnd } from "./format.js";

export function budgetToForm(budget, categories) {
  return {
    income: String(budget?.income_estimate ?? ""),
    savings: String(budget?.savings_goal ?? 0),
    allocations: Object.fromEntries(categories.map(({ id }) => [id, String(budget?.allocations?.find((line) => line.category_id === id)?.amount ?? 0)])),
  };
}

export function buildBudgetBody(form, categories) {
  const income_estimate = parseVnd(form.income);
  const savings_goal = parseVnd(form.savings);
  if (income_estimate === null || savings_goal === null) throw new Error("Thu nhập và mục tiêu tiết kiệm phải là số nguyên đồng không âm.");
  const allocations = categories.map(({ id, name }) => {
    const amount = parseVnd(form.allocations[id]);
    if (amount === null) throw new Error(`Ngân sách ${name} phải là số nguyên đồng không âm.`);
    return { category_id: id, amount };
  });
  const total = allocations.reduce((sum, line) => sum + line.amount, savings_goal);
  if (!Number.isSafeInteger(total)) throw new Error("Tổng ngân sách vượt giới hạn số tiền hỗ trợ.");
  if (total > income_estimate) throw new Error("Tổng phân bổ và tiết kiệm đang vượt thu nhập dự kiến. Hãy điều chỉnh trước khi lưu.");
  return { income_estimate, savings_goal, allocations };
}

export function checkBudget(budget, categories, period, { suggestion = false } = {}) {
  const money = (value) => Number.isSafeInteger(value) && value >= 0;
  if (!budget || budget.period !== period || !money(budget.income_estimate) || !money(budget.savings_goal) || !Array.isArray(budget.allocations) ||
      (suggestion ? !["RULE", "LLM"].includes(budget.source) || budget.status !== "DRAFT" : !["MANUAL", "RULE", "LLM"].includes(budget.source) || budget.status !== "ACTIVE")) {
    throw new Error("API trả về ngân sách không hợp lệ. Hãy tải lại để kiểm tra.");
  }
  const seen = new Set();
  let total = budget.savings_goal;
  for (const line of budget.allocations) {
    if (!line || !categories.some((category) => category.id === line.category_id) || seen.has(line.category_id) || !money(line.amount) || typeof line.name !== "string") {
      throw new Error("API trả về phân bổ danh mục không hợp lệ.");
    }
    seen.add(line.category_id);
    total += line.amount;
  }
  if (!Number.isSafeInteger(total) || total > budget.income_estimate) throw new Error("Ngân sách từ API vượt thu nhập dự kiến.");
  return budget;
}
