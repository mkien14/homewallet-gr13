import assert from "node:assert/strict";
import test from "node:test";
import { createReceiptForm, receiptConfirmationBody } from "../src/receiptForm.js";

const now = new Date(2026, 9, 21, 12);
const draft = () => ({ occurred_on: "2026-10-21", total_amount: 147000, merchant: null, category_id: null, items: [] });

test("receipt confirmation supports optional merchant, categories, and no line items", () => {
  const form = createReceiptForm(draft());
  assert.deepEqual(receiptConfirmationBody(form, [], { now }), draft());
});

test("receipt form preserves optional item metadata supplied by the server", () => {
  const data = { ...draft(), items: [{ description: null, quantity: null, amount: 147000, category_id: null, unit_price: 0 }] };
  const form = createReceiptForm(data, () => "line1");
  assert.equal(form.items[0].key, "line1");
  assert.deepEqual(receiptConfirmationBody(form, [], { now }), data);
});

test("invalid receipt date, money, quantity and removed category are rejected", () => {
  for (const change of [{ occurred_on: "0000-01-01" }, { occurred_on: "2026-02-30" }, { occurred_on: "2026-10-23" }, { total_amount: "-500" }, { category_id: "999" }]) {
    assert.throws(() => receiptConfirmationBody({ ...createReceiptForm(draft()), ...change }, [], { now }));
  }
  const form = createReceiptForm({ ...draft(), items: [{ amount: 147000, quantity: 10000000, category_id: null }] });
  assert.throws(() => receiptConfirmationBody(form, [], { now }), /Số lượng/);
});
