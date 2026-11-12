import test from "node:test";
import assert from "node:assert/strict";
import { notificationDate, notificationText } from "../src/notificationContent.js";

test("notifications accept string payloads and select requested language from maps", () => {
  const translate = (text) => text;
  assert.equal(notificationText("Original message", "vi", translate), "Original message");
  const content = { vi: "Sắp đến hạn", en: "Due soon" };
  assert.equal(notificationText(content, "en", translate), "Due soon");
  assert.equal(notificationText(content, "vi", translate), "Sắp đến hạn");
  assert.equal(notificationText({ en: "Due soon" }, "vi", translate), "Due soon");
  for (const value of [null, 2, [], { vi: {}, en: "" }]) {
    assert.equal(notificationText(value, "vi", translate, "Notification"), "Notification");
  }
});

test("notification dates preserve UTC offsets and do not crash on malformed payloads", () => {
  assert.equal(notificationDate("2026-11-12T12:00:00+07:00", "en"), notificationDate("2026-11-12T05:00:00Z", "en"));
  assert.equal(notificationDate("2026-11-12T05:00:00", "en"), notificationDate("2026-11-12T05:00:00Z", "en"));
  for (const value of [null, "", "invalid", {}]) assert.equal(notificationDate(value, "en"), "");
});
