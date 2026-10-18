import { config } from "../config";
import { challengeFor, randomString } from "./pkce";

const TOKEN_KEY = "hw.token";
const VERIFIER_KEY = "hw.pkce.verifier";
const STATE_KEY = "hw.pkce.state";

export async function login() {
  const verifier = randomString(48); 
  const state = randomString(16);
  sessionStorage.setItem(VERIFIER_KEY, verifier);
  sessionStorage.setItem(STATE_KEY, state);

  const params = new URLSearchParams({
    client_id: config.clientId,
    response_type: "code",
    scope: config.scopes,
    redirect_uri: config.redirectUri,
    state,
    code_challenge: await challengeFor(verifier),
    code_challenge_method: "S256",
  });
  window.location.assign(`${config.cognitoDomain}/oauth2/authorize?${params}`);
}

export async function handleCallback() {
  const q = new URLSearchParams(window.location.search);
  if (q.get("error")) throw new Error(q.get("error_description") || q.get("error"));

  const code = q.get("code");
  const verifier = sessionStorage.getItem(VERIFIER_KEY);
  if (!code || !verifier || q.get("state") !== sessionStorage.getItem(STATE_KEY)) {
    throw new Error("Phiên đăng nhập không hợp lệ, hãy thử đăng nhập lại");
  }
  sessionStorage.removeItem(VERIFIER_KEY);
  sessionStorage.removeItem(STATE_KEY);

  const res = await fetch(`${config.cognitoDomain}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      client_id: config.clientId,
      code,
      redirect_uri: config.redirectUri,
      code_verifier: verifier,
    }),
  });
  if (!res.ok) throw new Error("Không đổi được mã đăng nhập lấy token");

  const t = await res.json();
  sessionStorage.setItem(
    TOKEN_KEY,
    JSON.stringify({ access: t.access_token, exp: Date.now() + (t.expires_in - 30) * 1000 })
  );
}

export function getToken() {
  const raw = sessionStorage.getItem(TOKEN_KEY);
  if (!raw) return null;
  const t = JSON.parse(raw);
  if (Date.now() >= t.exp) {
    sessionStorage.removeItem(TOKEN_KEY);
    return null;
  }
  return t.access;
}

export const isLoggedIn = () => getToken() !== null;

export function logout() {
  sessionStorage.removeItem(TOKEN_KEY);
  const p = new URLSearchParams({ client_id: config.clientId, logout_uri: config.logoutUri });
  window.location.assign(`${config.cognitoDomain}/logout?${p}`);
}