import test from "node:test";
import assert from "node:assert/strict";
import { signInStep } from "../src/auth/signInStep.js";
import { readSessionToken } from "../src/auth/sessionToken.js";
import { hostedUiFallbackEnabled } from "../src/auth/hostedUiPolicy.js";

test("Hosted UI fallback is opt-in and unavailable from local origins", () => {
  assert.equal(hostedUiFallbackEnabled(undefined, "http://localhost:5173"), false);
  assert.equal(hostedUiFallbackEnabled("true", "http://localhost:5173"), false);
  assert.equal(hostedUiFallbackEnabled("true", "https://127.0.0.1:5173"), false);
  assert.equal(hostedUiFallbackEnabled("false", "https://daoedidcrnf1f.cloudfront.net"), false);
  assert.equal(hostedUiFallbackEnabled("true", "https://daoedidcrnf1f.cloudfront.net"), true);
});
test("TOTP sign-in setup consumes the challenge secret, not an authenticated setup API", () => {
  assert.deepEqual(signInStep({ nextStep: { signInStep: "CONTINUE_SIGN_IN_WITH_TOTP_SETUP", totpSetupDetails: { sharedSecret: "SYNTHETIC" } } }), { flow: "totpSetup", secret: "SYNTHETIC" });
  assert.equal(signInStep({ nextStep: { signInStep: "CONTINUE_SIGN_IN_WITH_TOTP_SETUP" } }).flow, "unsupported");
});
test("MFA choices reflect the server and reject missing choices", () => {
  assert.deepEqual(signInStep({ nextStep: { signInStep: "CONTINUE_SIGN_IN_WITH_MFA_SELECTION", allowedMFATypes: ["TOTP"] } }).methods, ["TOTP"]);
  assert.equal(signInStep({ nextStep: { signInStep: "CONTINUE_SIGN_IN_WITH_MFA_SELECTION" } }).flow, "unsupported");
});
test("account recovery, confirmation, password change and unknown challenges have explicit outcomes", () => {
  for (const [step, flow] of Object.entries({ RESET_PASSWORD: "forgot", CONFIRM_SIGN_UP: "confirmSignUp", CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED: "newPassword", CONTINUE_SIGN_IN_WITH_EMAIL_SETUP: "emailSetup", CONFIRM_SIGN_IN_WITH_TOTP_CODE: "mfa", DONE: "done", FUTURE_CHALLENGE: "unsupported" })) {
    assert.equal(signInStep({ nextStep: { signInStep: step } }).flow, flow);
  }
  assert.equal(signInStep({ nextStep: { signInStep: "CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED", missingAttributes: ["phone_number"] } }).flow, "unsupported");
});
test("expired, malformed, or incomplete browser tokens cannot crash or authenticate the UI", () => {
  for (const value of ["{", "null", "{}", JSON.stringify({ access: "test", exp: 99 }), JSON.stringify({ access: "test", exp: "999" })]) {
    const storage = new Map([["hw.token", value]]);
    assert.equal(readSessionToken({ getItem: k => storage.get(k), removeItem: k => storage.delete(k) }, 100), null);
    assert.equal(storage.has("hw.token"), false);
  }
  assert.equal(readSessionToken({ getItem: () => JSON.stringify({ access: "test", exp: 101 }) }, 100), "test");
});
