import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";
import { mockApi, resetMockData } from "../src/mocks/index.js";
import { dispatchRecurringMock } from "../src/mocks/recurring.js";

beforeEach(() => resetMockData());
const billDraft = () => ({ name: "Internet", category_id: 4, due_day: 31, expected_amount: 250000, remind_days_before: 3, active: true });

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


test("recurring mock permits member reads and rejects writes", () => {
  const state = { household: { id: 1, role: "member" }, categories: [{ id: 2 }, { id: 4 }] };
  assert.equal(dispatchRecurringMock(state, "/api/recurring-bills", "GET").result.items.length, 2);
  assert.throws(() => dispatchRecurringMock(state, "/api/recurring-bills", "POST", billDraft()), { status: 403 });
  assert.throws(() => dispatchRecurringMock(state, "/api/recurring-bills/1", "PATCH", { active: false }), { status: 403 });
});
