import test from "node:test";
import assert from "node:assert/strict";
import { buildTransactionBody, transactionDateLimit } from "../src/transactionForm.js";

const now = new Date(2026, 9, 31, 23, 45);
const fields = { occurredOn: "2026-10-31", amount: "150.000 ₫", categoryId: "1", note: "  Tiền ăn  " };
const categories = [{ id: 1, name: "Ăn uống" }];

test("manual transaction payload matches the real API and permits no category", () => {
  assert.deepEqual(buildTransactionBody(fields, categories, now), {
    occurred_on: "2026-10-31", total_amount: 150000, category_id: 1, note: "Tiền ăn",
  });
  assert.deepEqual(buildTransactionBody({ ...fields, categoryId: "", note: "" }, [], now), {
    occurred_on: "2026-10-31", total_amount: 150000, category_id: null, note: null,
  });
  assert.equal(buildTransactionBody({ ...fields, categoryId: null, note: null }, [], now).category_id, null);
});

test("transaction date limit uses local tomorrow across month and year boundaries", () => {
  assert.equal(transactionDateLimit(now), "2026-11-01");
  assert.equal(transactionDateLimit(new Date(2026, 11, 31, 0, 5)), "2027-01-01");
  assert.equal(buildTransactionBody({ ...fields, occurredOn: "2026-11-01" }, categories, now).occurred_on, "2026-11-01");
  assert.throws(() => buildTransactionBody({ ...fields, occurredOn: "2026-11-02" }, categories, now), /không quá ngày mai/);
});

test("manual form rejects nonexistent dates and dates outside Python date range", () => {
  for (const occurredOn of ["2026-02-29", "2026-04-31", "0000-01-01", "10000-01-01", "2026-1-01", ""]) {
    assert.throws(() => buildTransactionBody({ ...fields, occurredOn }, categories, now), /Ngày chi tiêu/);
  }
  assert.equal(buildTransactionBody({ ...fields, occurredOn: "2024-02-29" }, categories, now).occurred_on, "2024-02-29");
});

test("manual form rejects noninteger, nonpositive or unsafe amounts", () => {
  for (const amount of ["", "0", "-1", "1,5", "999999999999999999", "abc"]) {
    assert.throws(() => buildTransactionBody({ ...fields, amount }, categories, now), /số nguyên đồng/);
  }
});

test("unknown categories and notes over 500 characters are rejected before POST", () => {
  for (const categoryId of ["2", "-1", "1.0", "1.5", "abc"]) {
    assert.throws(() => buildTransactionBody({ ...fields, categoryId }, categories, now), /Danh mục không hợp lệ/);
  }
  assert.equal(buildTransactionBody({ ...fields, note: "a".repeat(500) }, categories, now).note.length, 500);
  assert.throws(() => buildTransactionBody({ ...fields, note: "a".repeat(501) }, categories, now), /500/);
  assert.throws(() => buildTransactionBody({ ...fields, note: 5 }, categories, now), /500/);
});
