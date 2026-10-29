import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";
import { mockApi, resetMockData, setFinanceFailure, setMockRole } from "../src/mocks/index.js";

beforeEach(() => resetMockData());
const path = "/api/budgets/2000-01";
const budget = { income_estimate: 10000000, savings_goal: 2000000, allocations: [{ category_id: 1, amount: 3000000 }] };

test("mock budget upsert follows the real response contract and retains values", async () => {
  assert.equal((await mockApi(path)).budget, null);
  const saved = await mockApi(path, { method: "PUT", body: budget });
  assert.equal(saved.budget.period, "2000-01");
  assert.equal(saved.budget.source, "MANUAL");
  assert.equal(saved.budget.status, "ACTIVE");
  assert.equal(saved.budget.allocations[0].name, "Ăn uống");
  assert.deepEqual(await mockApi(path), saved);
  assert.deepEqual(await mockApi(path, { method: "PUT", body: budget }), saved);
});

test("mock rejects invalid data and member writes without mutating saved budgets", async () => {
  const saved = await mockApi(path, { method: "PUT", body: budget });
  await assert.rejects(mockApi(path, { method: "PUT", body: { ...budget, savings_goal: 9000000 } }), { status: 422 });
  setMockRole("member");
  assert.deepEqual(await mockApi(path), saved);
  await assert.rejects(mockApi(path, { method: "PUT", body: budget }), { status: 403 });
  assert.deepEqual(await mockApi(path), saved);
});

test("mock failure controls apply once and leave the stored budget unchanged", async () => {
  for (const [kind, status] of [["network", 0], ["validation", 422], ["conflict", 409]]) {
    setFinanceFailure(kind);
    await assert.rejects(mockApi(path, { method: "PUT", body: budget }), { status });
    assert.equal((await mockApi(path)).budget, null);
  }
  assert.ok((await mockApi(path, { method: "PUT", body: budget })).budget);
});
