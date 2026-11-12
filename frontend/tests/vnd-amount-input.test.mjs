import test from "node:test";
import assert from "node:assert/strict";
import { deleteVndGroupingDigit, formatVndInputEdit } from "../src/vndAmountInput.js";
import { buildTransactionBody } from "../src/transactionForm.js";

test("typing six integer digits groups inside the field and keeps the caret at the end", () => {
  let value = "";
  for (const digit of "120000") {
    const raw = value + digit;
    const edit = formatVndInputEdit(value, raw, raw.length, raw.length, { inputType: "insertText", data: digit });
    value = edit.value;
    assert.equal(edit.start, value.length);
    assert.equal(edit.end, value.length);
  }
  assert.equal(value, "120.000");
});

test("pasted raw/grouped integer VND formats without changing its API amount", () => {
  for (const data of ["120000", "120,000", "120.000 ₫", "120 000 VND"]) {
    const result = formatVndInputEdit("", data, data.length, data.length, { inputType: "insertFromPaste", data });
    assert.equal(result.value, "120.000");
    assert.equal(buildTransactionBody({ occurredOn: "2026-01-01", amount: result.value, categoryId: "" }, []).total_amount, 120000);
  }
});

test("invalid pasted decimals, signs, text, and unsafe integers stay invalid", () => {
  for (const data of ["1.25", "1,25", "-120000", "+120000", "1e3", "abc", "9007199254740992"]) {
    const result = formatVndInputEdit("1.234", data, data.length, data.length, { inputType: "insertFromPaste", data });
    assert.equal(result.value, data);
    assert.throws(() => buildTransactionBody({ occurredOn: "2026-01-01", amount: result.value }, []), /số nguyên đồng/);
  }
});

test("typing a decimal point is preserved instead of stripped", () => {
  assert.equal(formatVndInputEdit("120.000", "120.000.", 8, 8, { inputType: "insertText", data: "." }).value, "120.000.");
  assert.equal(formatVndInputEdit("120.000.", "120.000.5", 9, 9, { inputType: "insertText", data: "5" }).value, "120.000.5");
});

test("middle insertion/paste and replacement preserve cursor position by digits", () => {
  assert.deepEqual(formatVndInputEdit("120.000", "1250.000", 3, 3, { inputType: "insertText", data: "5" }), { value: "1.250.000", start: 4, end: 4 });
  assert.deepEqual(formatVndInputEdit("120.000", "12990.000", 4, 4, { inputType: "insertFromPaste", data: "99" }), { value: "12.990.000", start: 5, end: 5 });
  assert.deepEqual(formatVndInputEdit("120.000", "159.000", 3, 3, { inputType: "insertText", data: "59" }), { value: "159.000", start: 3, end: 3 });
});

test("Backspace and Delete beside grouping dots remove the adjacent digit", () => {
  assert.deepEqual(deleteVndGroupingDigit("120.000", 4, 4, "Backspace"), { value: "12.000", start: 2, end: 2 });
  assert.deepEqual(deleteVndGroupingDigit("120.000", 3, 3, "Delete"), { value: "12.000", start: 4, end: 4 });
  assert.deepEqual(deleteVndGroupingDigit("1.234", 2, 2, "Backspace"), { value: "234", start: 0, end: 0 });
  assert.equal(deleteVndGroupingDigit("120.000", 1, 3, "Backspace"), null);
  assert.equal(deleteVndGroupingDigit("120.000", 0, 0, "Delete"), null);
});

test("deleting digits regroups old separators and clearing the whole field stays empty", () => {
  assert.deepEqual(formatVndInputEdit("120.000", "120.00", 6, 6, { inputType: "deleteContentBackward" }), { value: "12.000", start: 6, end: 6 });
  assert.deepEqual(formatVndInputEdit("120.000", "", 0, 0, { inputType: "deleteContentBackward" }), { value: "", start: 0, end: 0 });
});
