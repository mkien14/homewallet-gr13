import { UserManager, WebStorageStateStore } from 'oidc-client-ts';
import { config as defaultConfig } from '../config.js';

const LOGIN_REQUIRED = 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.';
const CALLBACK_FAILED = 'Không thể hoàn tất đăng nhập. Phiên xác thực có thể đã hết hạn hoặc không hợp lệ. Vui lòng thử đăng nhập lại.';
const KNOWN_ROUTES = new Set(['/', '/households', '/upload']);

export class AuthError extends Error {
  constructor(message, code = 'AUTH_REQUIRED') {
    super(message);
    this.name = 'AuthError';
    this.code = code;
  }
}

export function safeReturnTo(value, origin = globalThis.location?.origin) {
  if (typeof value !== 'string' || !origin) return '/';
  try {
    const url = new URL(value, origin);
    // Discard query/hash as well, so OAuth codes and untrusted parameters never persist.
    return url.origin === origin && KNOWN_ROUTES.has(url.pathname) ? url.pathname : '/';
  } catch {
    return '/';
  }
}

export function createOidcSettings(settings, storage = globalThis.sessionStorage) {
  if (!settings.isAuthConfigured) throw new AuthError(settings.configurationError || 'Chưa cấu hình đăng nhập Cognito.', 'AUTH_CONFIG');
  if (!storage) throw new AuthError('Trình duyệt không cho phép lưu phiên đăng nhập.', 'AUTH_STORAGE');
  return {
    authority: settings.cognitoAuthority,
    client_id: settings.cognitoClientId,
    redirect_uri: settings.redirectUri,
    post_logout_redirect_uri: settings.logoutUri,
    response_type: 'code',
    response_mode: 'query',
    scope: 'openid email profile',
    disablePKCE: false, // oidc-client-ts generates a verifier and its S256 challenge.
    loadUserInfo: false,
    // Cognito does not support prompt=none iframe renewal. Refresh explicitly below.
    automaticSilentRenew: false,
    monitorSession: false,
    revokeTokenTypes: ['refresh_token'],
    staleStateAgeInSeconds: 900,
    userStore: new WebStorageStateStore({ store: storage, prefix: 'homewallet.oidc.' }),
    stateStore: new WebStorageStateStore({ store: storage, prefix: 'homewallet.oidc.' }),
    metadata: {
      issuer: settings.cognitoAuthority,
      authorization_endpoint: `${settings.cognitoDomain}/oauth2/authorize`,
      token_endpoint: `${settings.cognitoDomain}/oauth2/token`,
      userinfo_endpoint: `${settings.cognitoDomain}/oauth2/userInfo`,
      jwks_uri: `${settings.cognitoAuthority}/.well-known/jwks.json`,
    },
  };
}

/** Keep tokens and OAuth transaction state in the current tab's sessionStorage. */
export function createAuthService({
  config = defaultConfig,
  managerFactory = (settings) => new UserManager(settings),
  storage,
  origin = globalThis.location?.origin ?? new URL(config.redirectUri).origin,
  navigate = (url) => globalThis.location.assign(url),
  now = () => Date.now() / 1000,
} = {}) {
  let manager;
  let refreshInFlight;
  let loginInFlight;
  let callbackUrl;
  let callbackInFlight;
  const listeners = new Set();
  const notify = (user) => {
    for (const listener of listeners) listener(user);
  };
  const usable = (user, margin = 0) => Boolean(
    user && typeof user.access_token === 'string' && user.access_token &&
    Number.isFinite(user.expires_at) && user.expires_at > now() + margin && !user.expired,
  );
  const getManager = () => {
    if (!manager) {
      manager = managerFactory(createOidcSettings(config, storage));
      manager.events.addUserLoaded((user) => notify(user));
      manager.events.addUserUnloaded(() => notify(null));
      manager.events.addAccessTokenExpired(async () => {
        // Preserve an idle session when a refresh token is still valid.
        try { notify(await readValidUser()); }
        catch { notify(null); }
      });
    }
    return manager;
  };
  const clearUser = async () => {
    await getManager().removeUser();
    notify(null);
  };

  const readValidUser = async () => {
    const current = await getManager().getUser();
    if (!current) return null;
    if (usable(current, 30)) return current;
    if (current.refresh_token) {
      if (!refreshInFlight) {
        refreshInFlight = getManager().signinSilent()
          .then(async (renewed) => {
            if (!usable(renewed)) {
              await clearUser();
              return null;
            }
            return renewed;
          })
          .catch(async () => {
            await clearUser();
            return null;
          })
          .finally(() => { refreshInFlight = undefined; });
      }
      return refreshInFlight;
    }
    // An otherwise valid token can still be used within the renewal margin.
    if (usable(current)) return current;
    await clearUser();
    return null;
  };

  return {
    async getUser() {
      if (!config.isAuthConfigured) return null;
      try { return await readValidUser(); }
      catch { throw new AuthError('Không thể đọc phiên đăng nhập. Hãy cho phép sessionStorage rồi thử lại.', 'AUTH_STORAGE'); }
    },
    async login(returnTo = '/') {
      if (!loginInFlight) {
        try {
          // The library persists this nonce beside state/PKCE and validates it on callback.
          const nonce = globalThis.crypto.randomUUID();
          loginInFlight = getManager().clearStaleState()
            .then(() => getManager().signinRedirect({ state: { returnTo: safeReturnTo(returnTo, origin) }, nonce }))
            .catch(() => { throw new AuthError('Không thể mở trang đăng nhập. Hãy kiểm tra cấu hình Cognito và thử lại.', 'AUTH_REDIRECT'); })
            .finally(() => { loginInFlight = undefined; });
        } catch {
          throw new AuthError(config.configurationError || 'Không thể bắt đầu đăng nhập trên trình duyệt này.', 'AUTH_CONFIG');
        }
      }
      return loginInFlight;
    },
    completeLogin(url = globalThis.location?.href) {
      // React StrictMode may run the callback effect twice. OAuth state is single use.
      if (callbackInFlight && callbackUrl === url) return callbackInFlight;
      callbackUrl = url;
      callbackInFlight = Promise.resolve().then(async () => {
        const callback = new URL(url);
        const expected = new URL(config.redirectUri);
        if (callback.origin !== expected.origin || callback.pathname !== expected.pathname || callback.hash) {
          throw new AuthError(CALLBACK_FAILED, 'AUTH_CALLBACK');
        }
        // Enforce the 15-minute OAuth transaction lifetime on the return trip too.
        await getManager().clearStaleState();
        // Missing code, provider errors, nonce and state mismatches are validated by oidc-client-ts.
        const user = await getManager().signinRedirectCallback(url);
        if (!usable(user)) {
          await clearUser();
          throw new AuthError(CALLBACK_FAILED, 'AUTH_CALLBACK');
        }
        notify(user);
        return { user, returnTo: safeReturnTo(user.state?.returnTo, origin) };
      }).catch(() => {
        // Do not expose provider errors, callback URLs, authorization codes or tokens.
        throw new AuthError(CALLBACK_FAILED, 'AUTH_CALLBACK');
      });
      return callbackInFlight;
    },
    async logout() {
      const activeManager = getManager();
      // Prevent a racing refresh from restoring credentials after local logout.
      if (refreshInFlight) await refreshInFlight.catch(() => {});
      await activeManager.removeUser();
      notify(null);
      const logout = new URL('/logout', config.cognitoDomain);
      logout.searchParams.set('client_id', config.cognitoClientId);
      logout.searchParams.set('logout_uri', config.logoutUri);
      navigate(logout.href);
    },
    async getAccessToken() {
      if (!config.isAuthConfigured) throw new AuthError(config.configurationError || 'Chưa cấu hình đăng nhập Cognito.', 'AUTH_CONFIG');
      try {
        const user = await readValidUser();
        if (user) return user.access_token;
      } catch {
        // Storage/provider failures must not leak tokens through error text.
      }
      throw new AuthError(LOGIN_REQUIRED);
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

export const authService = createAuthService();
