import test from "node:test";
import assert from "node:assert/strict";
import { t } from "../src/translations.js";
import { buildBudgetBody } from "../src/budgetForm.js";
import { buildRecurringBody } from "../src/recurringForm.js";
import { receiptConfirmationBody } from "../src/receiptForm.js";

function failure(action) {
  try { action(); } catch (error) { return error.message; }
  assert.fail("Expected validation to reject invalid input");
}

test("the same source message follows the current language both ways", () => {
  const message = "Đã thêm hóa đơn định kỳ.";
  assert.equal(t(message, "en"), "Recurring bill added.");
  assert.equal(t(message, "vi"), message);
  assert.equal(t(message, "en"), "Recurring bill added.");
});

test("recurring bill labels remain distinct from receipt labels", () => {
  assert.equal(t("Hóa đơn", "en"), "Receipts");
  assert.equal(t("khoản định kỳ", "en"), "bills");
  assert.equal(t("Danh sách hóa đơn định kỳ", "en"), "Recurring bill list");
  assert.equal(t("Dùng hóa đơn đã tìm thấy", "en"), "Use the bill found");
});

test("budget validation translates the message and preserves custom categories", () => {
  const validate = (name) => failure(() => buildBudgetBody({ income: "500", savings: "0", allocations: { 1: "bad" } }, [{ id: 1, name }]));
  assert.equal(t(validate("Ăn uống"), "en"), "The budget for Dining must be a non-negative whole VND amount.");
  assert.equal(t(validate("Quỹ của bà"), "en"), "The budget for Quỹ của bà must be a non-negative whole VND amount.");
  assert.equal(t("Quỹ của bà", "en"), "Quỹ của bà");
});

test("recurring form bounds are localised without changing validation", () => {
  const message = failure(() => buildRecurringBody({ name: "Điện", categoryId: "", amount: "", active: true, dueDay: "32", remindDays: "3" }, []));
  assert.equal(t(message, "en"), "The due day must be a whole number from 1 to 31.");
  assert.equal(t(message, "vi"), "Ngày đến hạn phải là số nguyên từ 1 đến 31.");
});

test("receipt row errors preserve the affected row number", () => {
  const message = failure(() => receiptConfirmationBody({ occurred_on: "2026-01-02", total_amount: "100", items: [{ amount: "0" }] }, [], { now: new Date("2026-01-03T00:00:00Z") }));
  assert.equal(t(message, "en"), "Line 1 total must be a whole VND amount greater than 0.");
  assert.equal(t("Số lượng dòng 12 phải lớn hơn 0 và không quá 9.999.999,999.", "en"), "Line 12 quantity must be greater than 0 and no more than 9,999,999.999.");
});

test("HTTP fallback errors retain the status code and leave unknown text unchanged", () => {
  assert.equal(t("Máy chủ API gặp lỗi (HTTP 500). Hãy thử lại sau.", "en"), "The server encountered an error (HTTP 500). Try again later.");
  assert.equal(t("My original receipt note", "en"), "My original receipt note");
  assert.equal(t(" toString ", "en"), " toString ");
});
