import test from "node:test";
import assert from "node:assert/strict";
import { buildRecurringBody, createNeedsReconciliation, matchingRecurringBills, recurringError, recurringFields, validRecurringBill } from "../src/recurringForm.js";

const categories = [{ id: 1, name: "Điện nước" }];
const fields = { name: "  Tiền điện  ", categoryId: "1", dueDay: "31", amount: "500.000 ₫", remindDays: "3", active: true };

test("recurring payload converts money and dates without sending household scope", () => {
  assert.deepEqual(buildRecurringBody(fields, categories), {
    name: "Tiền điện", category_id: 1, due_day: 31, expected_amount: 500000, remind_days_before: 3, active: true,
  });
  assert.equal(buildRecurringBody({ ...fields, amount: "0", remindDays: "0" }, categories).expected_amount, 0);
});

test("recurring form rejects invalid days, reminders, money and categories", () => {
  for (const dueDay of ["0", "32", "1.5", "", "-1"]) assert.throws(() => buildRecurringBody({ ...fields, dueDay }, categories), /Ngày đến hạn/);
  for (const remindDays of ["-1", "31", "0.5", ""]) assert.throws(() => buildRecurringBody({ ...fields, remindDays }, categories), /Số ngày nhắc trước/);
  for (const amount of ["-5", "1,5", "9007199254740992"]) assert.throws(() => buildRecurringBody({ ...fields, amount }, categories), /Số tiền dự kiến/);
  assert.throws(() => buildRecurringBody({ ...fields, categoryId: "2" }, categories), /danh mục hợp lệ/);
  assert.throws(() => buildRecurringBody({ ...fields, name: " " }, categories), /Tên hóa đơn/);
  assert.equal(buildRecurringBody({ ...fields, name: "x".repeat(100) }, categories).name.length, 100);
  assert.throws(() => buildRecurringBody({ ...fields, name: "x".repeat(101) }, categories), /Tên hóa đơn/);
});

test("editing a paused bill round trips without reactivating it", () => {
  const bill = { id: 9, ...buildRecurringBody({ ...fields, active: false }, categories) };
  assert.equal(validRecurringBill(bill, categories), true);
  const expectedBody = buildRecurringBody({ ...fields, active: false }, categories);
  assert.deepEqual(buildRecurringBody(recurringFields(bill), categories), expectedBody);
  assert.equal(validRecurringBill({ ...bill, expected_amount: "500000" }, categories), false);
  assert.equal(validRecurringBill({ ...bill, active: "false" }, categories), false);
});

test("nullable category and amount round trip without turning unknown money into zero", () => {
  const body = buildRecurringBody({ ...fields, categoryId: "", amount: "" }, []);
  assert.equal(body.category_id, null);
  assert.equal(body.expected_amount, null);
  const bill = { id: 2, ...body };
  assert.equal(validRecurringBill(bill, []), true);
  assert.equal(recurringFields(bill).amount, "");
  assert.equal(recurringFields(bill).categoryId, "");
  assert.deepEqual(buildRecurringBody(recurringFields(bill), []), body);
  assert.equal(buildRecurringBody({ ...fields, amount: "0" }, categories).expected_amount, 0);
  assert.equal(validRecurringBill({ ...bill, expected_amount: undefined }, []), false);
  assert.equal(validRecurringBill({ ...bill, category_id: undefined }, []), false);
});

test("structured NOT_FOUND preserves the server error and request identifier", () => {
  const error = { status: 404, code: "NOT_FOUND", message: "Không tìm thấy hóa đơn trong hộ.", requestId: "request-42" };
  assert.deepEqual(recurringError(error), { status: 404, message: error.message, requestId: "request-42" });
  assert.match(recurringError({ status: 404, code: "HTTP_404", message: "HTML response" }).message, /địa chỉ API.*khởi động lại backend/);
  assert.doesNotMatch(recurringError(error).message, /dữ liệu mẫu|chưa sẵn sàng/);
});

test("only uncertain create outcomes require checking the server list before retry", () => {
  for (const status of [undefined, 0, 500, 502, 504]) assert.equal(createNeedsReconciliation({ status }), true);
  for (const status of [400, 401, 403, 404, 409, 422]) assert.equal(createNeedsReconciliation({ status }), false);
});

test("reconciliation finds only new bills matching all fields including nullable money", () => {
  const body = buildRecurringBody({ ...fields, categoryId: "", amount: "" }, []);
  const items = [{ id: 1, ...body }, { id: 2, ...body }, { id: 3, ...body, expected_amount: 0 }, { id: 4, ...body, active: false }];
  assert.deepEqual(matchingRecurringBills(items, body, [1]).map((bill) => bill.id), [2]);
});
