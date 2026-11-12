import assert from "node:assert/strict";
import test from "node:test";
import { userDisplayName } from "../src/displayName.js";

test("greeting uses the saved display name and trims whitespace", () => {
  assert.equal(userDisplayName({ display_name: "  Hoàng  ", email: "private@example.com" }, "bạn"), "Hoàng");
});

test("missing, blank, malformed, or email display names use the localized fallback", () => {
  for (const user of [undefined, {}, { display_name: null }, { display_name: "  " }, { display_name: 123 }, { display_name: "private@example.com" }]) {
    assert.equal(userDisplayName(user, "bạn"), "bạn");
    assert.equal(userDisplayName(user, "there"), "there");
  }
  assert.equal(userDisplayName({ email: "private@example.com" }, "there"), "there");
});
