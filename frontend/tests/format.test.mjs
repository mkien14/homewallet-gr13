import test from "node:test";
import assert from "node:assert/strict";
import { formatDate, formatVnd, parseVnd, todayIso } from "../src/format.js";

test("Vietnamese currency and date formats preserve integer VND and local dates", () => {
  assert.equal(formatVnd(1234567).replace(/\s/g, " "), "1.234.567 ₫");
  assert.equal(formatDate("2026-10-12"), "12/10/2026");
  assert.equal(formatDate("2026-10-12T08:30:00Z"), "12/10/2026");
  assert.equal(formatDate(null), "");
  assert.equal(formatDate("not-a-date"), "");
  assert.equal(todayIso(new Date(2026, 0, 2, 0, 1)), "2026-01-02");
});

test("parses formatted VND without converting negative or unsafe inputs into positive amounts", () => {
  assert.equal(parseVnd("1.234.567 ₫"), 1234567);
  assert.equal(parseVnd("0"), 0);
  assert.equal(parseVnd("-50.000"), null);
  assert.equal(parseVnd("₫ -50.000"), null);
  assert.equal(parseVnd("1,5"), null);
  assert.equal(parseVnd("1.234.567 VND"), 1234567);
  assert.equal(parseVnd(""), null);
  assert.equal(parseVnd("abc"), null);
  assert.equal(parseVnd("99999999999999999999"), null);
});
