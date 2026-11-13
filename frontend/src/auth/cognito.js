import { Amplify } from "aws-amplify";
import {
  confirmResetPassword,
  confirmSignIn,
  confirmSignUp,
  fetchAuthSession,
  fetchUserAttributes,
  resendSignUpCode,
  resetPassword,
  signIn,
  signOut,
  signUp,
  updateUserAttribute,
  setUpTOTP,
  verifyTOTPSetup,
  fetchMFAPreference,
  updateMFAPreference,
} from "aws-amplify/auth";
import { cognitoUserPoolsTokenProvider } from "aws-amplify/auth/cognito";
import { config } from "../config";

const TOKEN_KEY = "hw.token";
const AUTH_MODE_KEY = "hw.auth.mode";
let configured = false;

function configureCognito() {
  if (!config.userPoolId || !config.clientId) {
    throw new Error("Cognito User Pool chưa được cấu hình. Hãy thêm VITE_COGNITO_USER_POOL_ID.");
  }
  if (configured) return;
  Amplify.configure({ Auth: { Cognito: { userPoolId: config.userPoolId, userPoolClientId: config.clientId } } });
  cognitoUserPoolsTokenProvider.setKeyValueStorage({
    async setItem(key, value) { sessionStorage.setItem(key, value); },
    async getItem(key) { return sessionStorage.getItem(key); },
    async removeItem(key) { sessionStorage.removeItem(key); },
    async clear() {
      const keys = [];
      for (let index = 0; index < sessionStorage.length; index += 1) {
        const key = sessionStorage.key(index);
        if (key?.startsWith("CognitoIdentityServiceProvider.") || key?.startsWith("amplify-")) keys.push(key);
      }
      keys.forEach((key) => sessionStorage.removeItem(key));
    },
  });
  configured = true;
}

export function hasReactAuthConfig() {
  return Boolean(config.userPoolId && config.clientId);
}

export async function reactSignIn(username, password) {
  configureCognito();
  return signIn({ username, password, options: { authFlowType: "USER_SRP_AUTH" } });
}

export async function reactSignUp(username, password, locale = "vi") {
  configureCognito();
  return signUp({ username, password, options: { userAttributes: { email: username, "custom:preferred_locale": locale === "en" ? "en" : "vi" } } });
}

export async function readReactPreferredLocale() {
  configureCognito();
  const attributes = await fetchUserAttributes();
  return attributes["custom:preferred_locale"];
}

export async function writeReactPreferredLocale(locale) {
  configureCognito();
  const result = await updateUserAttribute({ userAttribute: { attributeKey: "custom:preferred_locale", value: locale } });
  if (result.nextStep?.updateAttributeStep !== "DONE") throw new Error("Cognito locale update requires confirmation");
}

export async function reactConfirmSignUp(username, confirmationCode) {
  configureCognito();
  return confirmSignUp({ username, confirmationCode });
}

export async function reactResendSignUpCode(username) {
  configureCognito();
  return resendSignUpCode({ username });
}

export async function reactResetPassword(username) {
  configureCognito();
  return resetPassword({ username });
}

export async function reactConfirmResetPassword(username, confirmationCode, newPassword) {
  configureCognito();
  return confirmResetPassword({ username, confirmationCode, newPassword });
}

export async function reactConfirmSignIn(challengeResponse) {
  configureCognito();
  return confirmSignIn({ challengeResponse });
}

export async function reactSetUpTOTP() {
  configureCognito();
  return setUpTOTP();
}

export async function reactVerifyTOTP(code) {
  configureCognito();
  return verifyTOTPSetup({ code });
}

export async function reactMfaPreference() {
  configureCognito();
  return fetchMFAPreference();
}

export async function reactPreferTOTP() {
  configureCognito();
  return updateMFAPreference({ totp: "PREFERRED" });
}

export async function saveReactAuthSession() {
  configureCognito();
  const session = await fetchAuthSession();
  const accessToken = session.tokens?.accessToken;
  if (!accessToken) throw new Error("Cognito chưa trả access token cho phiên đăng nhập.");
  sessionStorage.setItem(TOKEN_KEY, JSON.stringify({ access: accessToken.toString(), exp: accessToken.payload.exp * 1000 - 30_000 }));
  sessionStorage.setItem(AUTH_MODE_KEY, "srp");
  return accessToken.toString();
}

export async function getReactAccessToken() {
  configureCognito();
  const session = await fetchAuthSession();
  const accessToken = session.tokens?.accessToken;
  if (!accessToken) return null;
  sessionStorage.setItem(TOKEN_KEY, JSON.stringify({ access: accessToken.toString(), exp: accessToken.payload.exp * 1000 - 30_000 }));
  return accessToken.toString();
}

export async function reactSignOut() {
  configureCognito();
  try { await signOut(); } finally {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(AUTH_MODE_KEY);
  }
}

export const isReactAuthSession = () => sessionStorage.getItem(AUTH_MODE_KEY) === "srp";
