import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";
import { mockApi, resetMockData, setMockRole } from "../src/mocks/index.js";
import { dispatchFinance } from "../src/mocks/finance.js";
import { todayIso } from "../src/format.js";

beforeEach(() => resetMockData());
const period = () => todayIso().slice(0, 7);
const path = () => `/api/budgets/${period()}`;

test("suggestion matches real API DRAFT envelope and missing history allocates nothing", async () => {
  const original = await mockApi(path());
  const response = await mockApi(`${path()}/suggest`, { method: "POST", body: { income_estimate: 10000000, savings_goal: 2000000 } });
  assert.deepEqual(Object.keys(response), ["suggestion"]);
  assert.equal(response.suggestion.source, "RULE");
  assert.equal(response.suggestion.status, "DRAFT");
  assert.equal(response.suggestion.period, period());
  assert.deepEqual(response.suggestion.allocations, []);
  response.suggestion.allocations.push({ category_id: 1, name: "Ăn uống", amount: 1 });
  assert.deepEqual(await mockApi(path()), original);
});

test("historical suggestions use previous three months confirmed only and stay bounded", () => {
  const state = {
    household: { id: 2, role: "owner" }, categories: [{ id: 1 }, { id: 2 }],
    transactions: [
      { household_id: 2, occurred_on: "2026-09-01", status: "CONFIRMED", category_id: 1, total_amount: 300000 },
      { household_id: 2, occurred_on: "2026-08-01", status: "DRAFT", category_id: 2, total_amount: 9000000 },
      { household_id: 2, occurred_on: "2026-06-01", status: "CONFIRMED", category_id: 2, total_amount: 9000000 },
      { household_id: 1, occurred_on: "2026-09-01", status: "CONFIRMED", category_id: 2, total_amount: 9000000 },
    ],
  };
  const result = dispatchFinance(state, "/api/budgets/2026-10/suggest", "POST", { income_estimate: 1000000, savings_goal: 0 }).result;
  assert.deepEqual(result.suggestion.allocations, [{ category_id: 1, name: "Danh mục", amount: 100000 }]);
  const bounded = dispatchFinance(state, "/api/budgets/2026-10/suggest", "POST", { income_estimate: 10000, savings_goal: 10000 }).result;
  assert.ok(bounded.suggestion.allocations.every((item) => item.amount === 0));
});

test("suggestion rounding and proportional fit match backend rules", () => {
  const state = {
    household: { id: 2, role: "owner" }, categories: [{ id: 1, name: "A" }, { id: 2, name: "B" }],
    transactions: [
      { household_id: 2, occurred_on: "2026-09-01", status: "CONFIRMED", category_id: 1, total_amount: 5 },
      { household_id: 2, occurred_on: "2026-09-01", status: "CONFIRMED", category_id: 2, total_amount: 8 },
    ],
  };
  const response = dispatchFinance(state, "/api/budgets/2026-10/suggest", "POST", { income_estimate: 4, savings_goal: 0 }).result;
  assert.deepEqual(response.suggestion.allocations, [{ category_id: 1, name: "A", amount: 2 }, { category_id: 2, name: "B", amount: 2 }]);
});

test("members cannot request a suggestion", async () => {
  setMockRole("member");
  await assert.rejects(mockApi(`${path()}/suggest`, { method: "POST", body: { income_estimate: 10000000, savings_goal: 0 } }), { status: 403 });
});
