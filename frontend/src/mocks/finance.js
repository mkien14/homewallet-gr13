import { todayIso } from "../format.js";

let nextFailure = "none";

function fail(status, code, message) {
  throw Object.assign(new Error(message), { status, code });
}

export function setFinanceFailure(kind) {
  if (!["none", "network", "validation", "conflict"].includes(kind)) throw new Error("Kịch bản thử không hợp lệ.");
  nextFailure = kind;
}

function mutationFailure() {
  const kind = nextFailure;
  nextFailure = "none";
  if (kind === "network") fail(0, "NETWORK_ERROR", "Mô phỏng mất kết nối. Nội dung của bạn vẫn được giữ, hãy thử lại.");
  if (kind === "validation") fail(422, "VALIDATION", "Mô phỏng lỗi kiểm tra dữ liệu (422). Hãy kiểm tra nội dung rồi lưu lại.");
  if (kind === "conflict") fail(409, "CONFLICT", "Mô phỏng xung đột dữ liệu (409). Nội dung chỉnh sửa vẫn được giữ.");
}

function validPeriod(period) {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(period) || period.startsWith("0000")) fail(422, "VALIDATION", "Kỳ ngân sách phải có dạng YYYY-MM và năm lớn hơn 0.");
}

function nonnegative(value, label) {
  if (!Number.isSafeInteger(value) || value < 0) fail(422, "VALIDATION", `${label} phải là số nguyên đồng không âm.`);
  return value;
}

function objectBody(body, fields) {
  if (!body || typeof body !== "object" || Array.isArray(body) || Object.keys(body).some((key) => !fields.includes(key))) {
    fail(422, "VALIDATION", "Dữ liệu thiếu hoặc có trường không được hỗ trợ.");
  }
}

function category(state, id) {
  if (!Number.isSafeInteger(id) || id <= 0 || !state.categories.some((item) => item.id === id)) fail(422, "VALIDATION", "Danh mục không hợp lệ.");
}

function owner(state) {
  if (!state.household) fail(404, "NOT_FOUND", "Bạn cần tham gia một hộ gia đình.");
  if (state.household.role !== "owner") fail(403, "FORBIDDEN", "Chỉ Chủ hộ được chỉnh sửa ngân sách.");
}

function financeState(state) {
  if (!state.household) fail(404, "NOT_FOUND", "Bạn cần tham gia một hộ gia đình.");
  // Add finance data to old version-1 demos without replacing receipts or transactions.
  state.financeByHousehold ??= {};
  const key = String(state.household.id);
  if (!Object.hasOwn(state.financeByHousehold, key)) {
    const sample = state.household.id === 1;
    const period = todayIso().slice(0, 7);
    state.financeByHousehold[key] = {
      budgets: sample ? { [period]: {
        period, income_estimate: 12000000, savings_goal: 2000000, source: "MANUAL", status: "ACTIVE",
        allocations: [{ category_id: 1, amount: 4500000 }, { category_id: 2, amount: 1000000 }, { category_id: 3, amount: 1500000 }, { category_id: 4, amount: 1000000 }],
      } } : {},
    };
  }
  const data = state.financeByHousehold[key];
  // Migrate the initial preview's versioned budgets to the real API contract.
  for (const [period, budget] of Object.entries(data.budgets)) {
    data.budgets[period] = budgetPayload(state, period, budget);
  }
  return data;
}

function allocationPayload(state, allocations) {
  return allocations.map(({ category_id, amount }) => ({
    category_id, name: state.categories.find((item) => item.id === category_id)?.name ?? "Danh mục", amount,
  })).sort((left, right) => left.category_id - right.category_id);
}

function budgetPayload(state, period, body) {
  return {
    period, income_estimate: body.income_estimate, savings_goal: body.savings_goal,
    source: "MANUAL", status: "ACTIVE", allocations: allocationPayload(state, body.allocations),
  };
}

function budgetBody(state, body) {
  objectBody(body, ["income_estimate", "savings_goal", "allocations"]);
  nonnegative(body.income_estimate, "Thu nhập");
  nonnegative(body.savings_goal, "Tiết kiệm");
  if (!Array.isArray(body.allocations)) fail(422, "VALIDATION", "Phân bổ ngân sách phải là một danh sách.");
  const seen = new Set();
  let total = BigInt(body.savings_goal);
  for (const allocation of body.allocations) {
    objectBody(allocation, ["category_id", "amount"]);
    category(state, allocation.category_id);
    if (seen.has(allocation.category_id)) fail(422, "VALIDATION", "Danh mục không được phân bổ hai lần.");
    seen.add(allocation.category_id);
    total += BigInt(nonnegative(allocation.amount, "Phân bổ"));
  }
  if (total > BigInt(body.income_estimate)) fail(422, "VALIDATION", "Tổng phân bổ và tiết kiệm vượt quá thu nhập dự kiến.");
}

export function dispatchFinance(state, route, verb, body) {
  const budget = /^\/api\/budgets\/([^/]+)$/.exec(route);
  if (!budget) return { handled: false };
  const data = financeState(state);
  validPeriod(budget[1]);
  if (verb !== "GET") { owner(state); mutationFailure(); }
  if (verb === "GET") return { handled: true, result: { budget: data.budgets[budget[1]] ?? null } };
  if (verb === "PUT") {
    budgetBody(state, body);
    const saved = budgetPayload(state, budget[1], body);
    data.budgets[budget[1]] = saved;
    return { handled: true, result: { budget: saved } };
  }
  fail(405, "METHOD_NOT_ALLOWED", "Thao tác không được hỗ trợ.");
}
