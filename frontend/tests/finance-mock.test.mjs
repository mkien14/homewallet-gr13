import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";
import { mockApi, resetMockData, setFinanceFailure, setMockRole } from "../src/mocks/index.js";
import { dispatchFinance } from "../src/mocks/finance.js";
import { todayIso } from "../src/format.js";

beforeEach(() => resetMockData());
const period = () => todayIso().slice(0, 7);
const path = () => `/api/budgets/${period()}`;
const draft = () => ({ income_estimate: 10000000, savings_goal: 2000000, allocations: [{ category_id: 1, amount: 3000000 }] });
const billDraft = () => ({ name: "Internet", category_id: 4, due_day: 31, expected_amount: 250000, remind_days_before: 3, active: true });

test("current month is seeded while an empty month can be created and updated", async () => {
  const sample = await mockApi(path());
  assert.equal(sample.budget.income_estimate, 12000000);
  assert.equal(sample.budget.source, "MANUAL");
  assert.equal(sample.budget.status, "ACTIVE");
  assert.equal(Object.hasOwn(sample.budget, "version"), false);
  assert.equal(sample.budget.allocations[0].name, "Ăn uống");
  assert.equal((await mockApi("/api/budgets/2000-01")).budget, null);
  const created = await mockApi("/api/budgets/2000-01", { method: "PUT", body: draft() });
  assert.equal(created.budget.source, "MANUAL");
  const updated = await mockApi("/api/budgets/2000-01", { method: "PUT", body: { ...draft(), savings_goal: 1500000 } });
  assert.equal(updated.budget.savings_goal, 1500000);
  assert.deepEqual(await mockApi("/api/budgets/2000-01"), updated);
});

test("PUT replaces existing period, removes omitted lines and is idempotent", async () => {
  const saved = await mockApi(path(), { method: "PUT", body: draft() });
  assert.deepEqual(await mockApi(path(), { method: "PUT", body: draft() }), saved);
  assert.equal(saved.budget.allocations.length, 1);
  const cleared = await mockApi(path(), { method: "PUT", body: { ...draft(), allocations: [] } });
  assert.deepEqual(cleared.budget.allocations, []);
  for (const unsupported of [{ version: null }, { source: "MANUAL" }, { status: "ACTIVE" }]) {
    await assert.rejects(mockApi(path(), { method: "PUT", body: { ...draft(), ...unsupported } }), { status: 422 });
  }
  assert.deepEqual(await mockApi(path()), cleared);
});

test("budget validates period, totals, category, duplicates and exact integer money", async () => {
  for (const invalid of ["0000-01", "2026-00", "2026-13", "2026-1"]) await assert.rejects(mockApi(`/api/budgets/${invalid}`), { status: 422 });
  const changes = [
    { income_estimate: -1 }, { savings_goal: 0.5 }, { income_estimate: Number.MAX_SAFE_INTEGER + 1 },
    { allocations: [{ category_id: 999, amount: 1 }] },
    { allocations: [{ category_id: 1, amount: 9000000 }] },
    { allocations: [{ category_id: 1, amount: 1 }, { category_id: 1, amount: 2 }] },
    { household_id: 2 },
  ];
  for (const change of changes) {
    await assert.rejects(mockApi("/api/budgets/2000-01", { method: "PUT", body: { ...draft(), ...change } }), { status: 422 });
    assert.equal((await mockApi("/api/budgets/2000-01")).budget, null);
  }
  const exact = { ...draft(), allocations: [{ category_id: 1, amount: 8000000 }] };
  assert.ok((await mockApi("/api/budgets/2000-01", { method: "PUT", body: exact })).budget);
});

test("members read existing finance data but cannot mutate it or request suggestions", async () => {
  const original = await mockApi(path());
  setMockRole("member");
  assert.equal((await mockApi("/api/me")).household.role, "member");
  assert.deepEqual(await mockApi(path()), original);
  assert.equal((await mockApi("/api/recurring-bills")).items.length, 2);
  for (const [route, method, body] of [
    [path(), "PUT", draft()],
    [`${path()}/suggest`, "POST", { income_estimate: 10000000, savings_goal: 0 }],
    ["/api/recurring-bills", "POST", billDraft()],
    ["/api/recurring-bills/1", "PATCH", { active: false }],
  ]) await assert.rejects(mockApi(route, { method, body }), { status: 403 });
  setMockRole("owner");
  assert.deepEqual(await mockApi(path()), original);
});

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

test("recurring bills create edit pause and resume without duplicate IDs", async () => {
  const created = (await mockApi("/api/recurring-bills", { method: "POST", body: billDraft() })).bill;
  assert.equal(created.id, 3);
  const edited = (await mockApi(`/api/recurring-bills/${created.id}`, { method: "PATCH", body: { expected_amount: 300000, name: "Internet mới" } })).bill;
  assert.equal(edited.name, "Internet mới");
  assert.equal(edited.due_day, 31);
  assert.equal((await mockApi(`/api/recurring-bills/${created.id}`, { method: "PATCH", body: { active: false } })).bill.active, false);
  assert.equal((await mockApi(`/api/recurring-bills/${created.id}`, { method: "PATCH", body: { active: true } })).bill.active, true);
  assert.equal((await mockApi("/api/recurring-bills")).items.length, 3);
});

test("invalid recurring mutations leave saved bill unchanged", async () => {
  const original = await mockApi("/api/recurring-bills");
  for (const change of [{ name: " " }, { name: "x".repeat(101) }, { category_id: 999 }, { due_day: 0 }, { due_day: 32 }, { expected_amount: -1 }, { expected_amount: 1.5 }, { remind_days_before: 31 }, { active: "true" }, { household_id: 2 }]) {
    await assert.rejects(mockApi("/api/recurring-bills/1", { method: "PATCH", body: change }), { status: 422 });
  }
  await assert.rejects(mockApi("/api/recurring-bills/999", { method: "PATCH", body: { active: false } }), { status: 404 });
  assert.deepEqual(await mockApi("/api/recurring-bills"), original);
});

test("recurring fields match nullable defaults and API does not promise POST deduplication", async () => {
  const options = { method: "POST", headers: { "Idempotency-Key": "ignored-by-real-backend" }, body: { name: "Internet", due_day: 5 } };
  const saved = (await mockApi("/api/recurring-bills", options)).bill;
  assert.deepEqual(saved, { id: 3, name: "Internet", due_day: 5, category_id: null, expected_amount: null, remind_days_before: 3, active: true });
  const repeated = (await mockApi("/api/recurring-bills", options)).bill;
  assert.notEqual(repeated.id, saved.id);
  const updated = (await mockApi(`/api/recurring-bills/${saved.id}`, { method: "PATCH", body: { name: "x".repeat(100), category_id: null, expected_amount: null } })).bill;
  assert.equal(updated.name.length, 100);
  assert.equal(updated.category_id, null);
  assert.equal(updated.expected_amount, null);
  assert.deepEqual((await mockApi("/api/recurring-bills")).items.map((item) => item.due_day), [1, 5, 5, 15]);
  assert.equal(await mockApi(`/api/recurring-bills/${saved.id}`, { method: "DELETE" }), null);
  await assert.rejects(mockApi(`/api/recurring-bills/${saved.id}`, { method: "PATCH", body: { active: false } }), { status: 404 });
});

test("failure controls apply once only to finance mutations and reset is clean", async () => {
  for (const [kind, status] of [["network", 0], ["validation", 422], ["conflict", 409]]) {
    setFinanceFailure(kind);
    assert.ok((await mockApi(path())).budget);
    await assert.rejects(mockApi("/api/recurring-bills", { method: "POST", body: billDraft() }), { status });
    assert.ok((await mockApi("/api/recurring-bills", { method: "POST", body: billDraft() })).bill);
  }
  setFinanceFailure("network");
  resetMockData();
  assert.ok((await mockApi("/api/recurring-bills", { method: "POST", body: billDraft() })).bill);
});

test("finance mock scopes data to active household and preserves legacy data", () => {
  const state = { household: { id: 1, role: "owner" }, categories: [{ id: 1 }], transactions: [], receipts: [{ id: 8 }] };
  assert.ok(dispatchFinance(state, "/api/recurring-bills", "GET").result.items.length);
  state.household.id = 2;
  assert.deepEqual(dispatchFinance(state, "/api/recurring-bills", "GET").result.items, []);
  assert.equal(dispatchFinance(state, `/api/budgets/${period()}`, "GET").result.budget, null);
  assert.deepEqual(state.receipts, [{ id: 8 }]);
  state.household.id = 1;
  assert.equal(dispatchFinance(state, "/api/recurring-bills", "GET").result.items.length, 2);
});

test("old versioned preview budget is migrated without losing edited amounts or receipts", () => {
  const state = {
    household: { id: 2, role: "owner" }, categories: [{ id: 1, name: "Ăn uống" }], transactions: [], receipts: [{ id: 9 }],
    financeByHousehold: { "2": { budgets: { "2026-10": { period: "2026-10", income_estimate: 1000000, savings_goal: 0, version: 7, allocations: [{ category_id: 1, amount: 345678 }] } }, bills: [], billIdempotency: { old: {} } } },
  };
  const response = dispatchFinance(state, "/api/budgets/2026-10", "GET").result;
  assert.deepEqual(response.budget, { period: "2026-10", income_estimate: 1000000, savings_goal: 0, source: "MANUAL", status: "ACTIVE", allocations: [{ category_id: 1, name: "Ăn uống", amount: 345678 }] });
  assert.equal(Object.hasOwn(state.financeByHousehold["2"], "billIdempotency"), false);
  assert.deepEqual(state.receipts, [{ id: 9 }]);
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
