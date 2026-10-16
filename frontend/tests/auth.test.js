// @vitest-environment node
import { describe, expect, it, vi } from 'vitest';
import { OidcClient, UserManager } from 'oidc-client-ts';
import { readConfig } from '../src/config.js';
import { AuthError, createAuthService, createOidcSettings, safeReturnTo } from '../src/auth/service.js';

const origin = 'https://wallet.example.com';
const config = readConfig({
  VITE_COGNITO_AUTHORITY: 'https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_Abc123',
  VITE_COGNITO_DOMAIN: 'https://homewallet.auth.ap-southeast-1.amazoncognito.com',
  VITE_COGNITO_CLIENT_ID: 'publicclient123',
}, origin);

function memoryStorage() {
  const entries = new Map();
  return {
    get length() { return entries.size; },
    key: (index) => [...entries.keys()][index] ?? null,
    getItem: (key) => entries.get(key) ?? null,
    setItem: (key, value) => entries.set(key, String(value)),
    removeItem: (key) => entries.delete(key),
  };
}

function harness(user = null) {
  const callbacks = {};
  const manager = {
    events: {
      addUserLoaded: (callback) => { callbacks.loaded = callback; },
      addUserUnloaded: (callback) => { callbacks.unloaded = callback; },
      addAccessTokenExpired: (callback) => { callbacks.expired = callback; },
    },
    getUser: vi.fn(async () => user),
    removeUser: vi.fn(async () => { user = null; }),
    signinSilent: vi.fn(async () => null),
    clearStaleState: vi.fn(async () => {}),
    signinRedirect: vi.fn(async () => {}),
    signinRedirectCallback: vi.fn(async () => user),
  };
  const navigate = vi.fn();
  const service = createAuthService({
    config, origin, storage: memoryStorage(), managerFactory: () => manager, navigate, now: () => 1_000,
  });
  return { service, manager, callbacks, navigate };
}

describe('Cognito protocol settings', () => {
  it('uses real oidc-client-ts to generate code flow, S256 PKCE, state and nonce', async () => {
    const storage = memoryStorage();
    const settings = createOidcSettings(config, storage);
    expect(settings).toMatchObject({
      response_type: 'code', disablePKCE: false, automaticSilentRenew: false,
      scope: 'openid email profile', loadUserInfo: false,
    });
    expect(settings).not.toHaveProperty('client_secret');
    const client = new OidcClient(settings);
    const request = await client.createSigninRequest({ state: { returnTo: '/upload' }, nonce: 'unique-nonce' });
    const url = new URL(request.url);
    expect(url.origin).toBe(config.cognitoDomain);
    expect(url.pathname).toBe('/oauth2/authorize');
    expect(url.searchParams.get('response_type')).toBe('code');
    expect(url.searchParams.get('code_challenge_method')).toBe('S256');
    expect(url.searchParams.get('code_challenge')).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(url.searchParams.get('state')).toBeTruthy();
    expect(url.searchParams.get('nonce')).toBe('unique-nonce');
    expect(url.searchParams.has('code_verifier')).toBe(false);
    const saved = JSON.parse(storage.getItem(`homewallet.oidc.${url.searchParams.get('state')}`));
    expect(saved.code_verifier).toBeTruthy();
    expect(saved.data).toEqual({ returnTo: '/upload' });
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(saved.code_verifier));
    expect(Buffer.from(digest).toString('base64url')).toBe(url.searchParams.get('code_challenge'));
  });

  it('uses real library validation to reject a callback without matching state', async () => {
    const service = createAuthService({ config, origin, storage: memoryStorage() });
    await expect(service.completeLogin(`${origin}/auth/callback?code=private-code&state=forged`))
      .rejects.toMatchObject({ name: 'AuthError', code: 'AUTH_CALLBACK' });
    await expect(service.completeLogin(`${origin}/auth/callback?code=private-code&state=forged`))
      .rejects.not.toThrow('private-code');
  });

  it('rejects a saved OAuth transaction older than 15 minutes without exchanging the code', async () => {
    const storage = memoryStorage();
    const settings = createOidcSettings(config, storage);
    const client = new OidcClient(settings);
    const request = await client.createSigninRequest({ nonce: 'stored-nonce' });
    const state = new URL(request.url).searchParams.get('state');
    const key = `homewallet.oidc.${state}`;
    const saved = JSON.parse(storage.getItem(key));
    saved.created = Math.floor(Date.now() / 1000) - 901;
    storage.setItem(key, JSON.stringify(saved));
    const fetch = vi.spyOn(globalThis, 'fetch');
    const service = createAuthService({ config, origin, storage });
    await expect(service.completeLogin(`${origin}/auth/callback?code=private-code&state=${state}`))
      .rejects.toMatchObject({ code: 'AUTH_CALLBACK' });
    expect(fetch).not.toHaveBeenCalled();
    expect(storage.getItem(key)).toBeNull();
  });

  it.each(['', '&error=access_denied&error_description=private-code'])
    ('uses real library state validation to reject missing code or provider denial', async (suffix) => {
      const storage = memoryStorage();
      const settings = createOidcSettings(config, storage);
      const client = new OidcClient(settings);
      const request = await client.createSigninRequest({ nonce: 'stored-nonce' });
      const state = new URL(request.url).searchParams.get('state');
      const service = createAuthService({ config, origin, storage });
      const callback = `${origin}/auth/callback?state=${state}${suffix}`;
      await expect(service.completeLogin(callback)).rejects.toMatchObject({ code: 'AUTH_CALLBACK' });
      expect(storage.getItem(`homewallet.oidc.${state}`)).toBeNull();
    });

  it.each([true, false])('exchanges a code using the saved PKCE verifier and validates nonce (matching: %s)', async (matchingNonce) => {
    const storage = memoryStorage();
    const settings = createOidcSettings(config, storage);
    const client = new OidcClient(settings);
    const request = await client.createSigninRequest({ nonce: 'stored-nonce', state: { returnTo: '/upload' } });
    const state = new URL(request.url).searchParams.get('state');
    const saved = JSON.parse(storage.getItem(`homewallet.oidc.${state}`));
    const currentTime = Math.floor(Date.now() / 1000);
    const claims = {
      sub: 'test-user', iss: config.cognitoAuthority, aud: config.cognitoClientId,
      nonce: matchingNonce ? 'stored-nonce' : 'wrong-nonce', iat: currentTime, exp: currentTime + 3600,
    };
    // Synthetic token; this test exercises protocol handling without AWS credentials.
    const idToken = [
      Buffer.from(JSON.stringify({ alg: 'RS256', typ: 'JWT' })).toString('base64url'),
      Buffer.from(JSON.stringify(claims)).toString('base64url'),
      'test-signature',
    ].join('.');
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      access_token: 'test-access-token', refresh_token: 'test-refresh-token', id_token: idToken,
      token_type: 'Bearer', scope: 'openid email profile', expires_in: 3600,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    const service = createAuthService({ config, origin, storage });
    const result = service.completeLogin(`${origin}/auth/callback?code=test-code&state=${state}`);
    if (matchingNonce) {
      await expect(result).resolves.toMatchObject({ user: { access_token: 'test-access-token' }, returnTo: '/upload' });
    } else {
      await expect(result).rejects.toMatchObject({ code: 'AUTH_CALLBACK' });
      expect(await service.getUser()).toBeNull();
    }
    expect(fetch).toHaveBeenCalledOnce();
    expect(fetch.mock.calls[0][0]).toBe(`${config.cognitoDomain}/oauth2/token`);
    const options = fetch.mock.calls[0][1];
    expect(options.method).toBe('POST');
    const body = new URLSearchParams(options.body);
    expect(body.get('grant_type')).toBe('authorization_code');
    expect(body.get('code')).toBe('test-code');
    expect(body.get('code_verifier')).toBe(saved.code_verifier);
    expect(body.get('redirect_uri')).toBe(config.redirectUri);
    expect(body.has('client_secret')).toBe(false);
  });

  it('persists actual UserManager sessions in the supplied session store only', async () => {
    const storage = memoryStorage();
    const manager = new UserManager(createOidcSettings(config, storage));
    await manager.settings.userStore.set('test-session', 'session-value');
    expect(storage.getItem('homewallet.oidc.test-session')).toBe('session-value');
    expect(await manager.settings.stateStore.get('test-session')).toBe('session-value');
  });
});

describe('safe return routes', () => {
  it.each(['/', '/households', '/upload', `${origin}/upload`])('preserves known route %s', (route) => {
    expect(safeReturnTo(route, origin)).toBe(new URL(route, origin).pathname);
  });
  it.each(['https://evil.example/upload', '//evil.example/upload', 'javascript:alert(1)', '/auth/callback', '/unknown', null])
    ('discards unsafe or unsupported route %s', (route) => expect(safeReturnTo(route, origin)).toBe('/'));
  it('does not propagate OAuth query parameters or fragments', () => {
    expect(safeReturnTo('/upload?code=private#token', origin)).toBe('/upload');
  });
});

describe('authentication lifecycle', () => {
  it('fails safely when no user is signed in', async () => {
    const { service } = harness();
    expect(await service.getUser()).toBeNull();
    await expect(service.getAccessToken()).rejects.toBeInstanceOf(AuthError);
    await expect(service.getAccessToken()).rejects.toMatchObject({ code: 'AUTH_REQUIRED' });
  });

  it('returns an access token rather than the ID token for API calls', async () => {
    const { service, manager } = harness({ access_token: 'access', id_token: 'identity', expires_at: 2_000 });
    expect(await service.getAccessToken()).toBe('access');
    expect(manager.signinSilent).not.toHaveBeenCalled();
  });

  it('clears expired sessions without attempting an iframe login', async () => {
    const { service, manager } = harness({ access_token: 'expired', expires_at: 900 });
    await expect(service.getAccessToken()).rejects.toMatchObject({ code: 'AUTH_REQUIRED' });
    expect(manager.removeUser).toHaveBeenCalledOnce();
    expect(manager.signinSilent).not.toHaveBeenCalled();
  });

  it('refreshes an expired token once for concurrent API requests', async () => {
    const { service, manager } = harness({ access_token: 'expired', refresh_token: 'refresh', expires_at: 900 });
    manager.signinSilent.mockResolvedValue({ access_token: 'new-access', expires_at: 2_000 });
    expect(await Promise.all([service.getAccessToken(), service.getAccessToken()])).toEqual(['new-access', 'new-access']);
    expect(manager.signinSilent).toHaveBeenCalledOnce();
  });

  it('clears the session and sanitizes a refresh failure', async () => {
    const { service, manager } = harness({ access_token: 'expired', refresh_token: 'refresh', expires_at: 900 });
    manager.signinSilent.mockRejectedValue(new Error('provider included private-token'));
    await expect(service.getAccessToken()).rejects.toMatchObject({ code: 'AUTH_REQUIRED' });
    expect(manager.removeUser).toHaveBeenCalledOnce();
  });

  it('passes a fresh nonce and safe route to the library for redirect login', async () => {
    const { service, manager } = harness();
    await service.login('https://evil.example/upload');
    expect(manager.clearStaleState).toHaveBeenCalledOnce();
    expect(manager.signinRedirect).toHaveBeenCalledWith({
      state: { returnTo: '/' }, nonce: expect.stringMatching(/^[0-9a-f-]{36}$/),
    });
  });

  it('handles a callback once even when StrictMode runs it twice', async () => {
    const user = { access_token: 'access', expires_at: 2_000, state: { returnTo: '/upload' } };
    const { service, manager } = harness(user);
    const callback = `${origin}/auth/callback?code=code&state=state`;
    const first = service.completeLogin(callback);
    const second = service.completeLogin(callback);
    expect(first).toBe(second);
    expect(await first).toEqual({ user, returnTo: '/upload' });
    expect(manager.signinRedirectCallback).toHaveBeenCalledOnce();
  });

  it.each([
    `${origin}/auth/callback?error=access_denied&error_description=private-code`,
    `${origin}/auth/callback?state=missing-code`,
  ])('sanitizes library callback validation errors', async (url) => {
    const { service, manager } = harness();
    manager.signinRedirectCallback.mockRejectedValue(new Error('provider message private-code'));
    await expect(service.completeLogin(url)).rejects.toMatchObject({ code: 'AUTH_CALLBACK' });
    await expect(service.completeLogin(url)).rejects.not.toThrow('private-code');
  });

  it('rejects callback URLs outside the configured path before exchanging a code', async () => {
    const { service, manager } = harness();
    await expect(service.completeLogin('https://evil.example/auth/callback?code=x')).rejects.toMatchObject({ code: 'AUTH_CALLBACK' });
    expect(manager.signinRedirectCallback).not.toHaveBeenCalled();
  });

  it('clears the local user before redirecting to the Cognito logout endpoint', async () => {
    const { service, manager, navigate } = harness({ access_token: 'access', expires_at: 2_000 });
    await service.logout();
    expect(manager.removeUser).toHaveBeenCalledOnce();
    const url = new URL(navigate.mock.calls[0][0]);
    expect(url.origin).toBe(config.cognitoDomain);
    expect(url.pathname).toBe('/logout');
    expect(url.searchParams.get('client_id')).toBe(config.cognitoClientId);
    expect(url.searchParams.get('logout_uri')).toBe(`${origin}/`);
    expect(manager.removeUser.mock.invocationCallOrder[0]).toBeLessThan(navigate.mock.invocationCallOrder[0]);
  });

  it('notifies subscribers with users and supports unsubscribe', async () => {
    const { service, callbacks } = harness();
    const listener = vi.fn();
    const unsubscribe = service.subscribe(listener);
    await service.getUser();
    const user = { access_token: 'access', expires_at: 2_000 };
    callbacks.loaded(user);
    expect(listener).toHaveBeenLastCalledWith(user);
    await callbacks.expired();
    expect(listener).toHaveBeenLastCalledWith(null);
    unsubscribe();
    callbacks.loaded(user);
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it('refreshes an idle session on expiry before notifying the UI', async () => {
    const { service, callbacks, manager } = harness({ access_token: 'expired', refresh_token: 'refresh', expires_at: 900 });
    const renewed = { access_token: 'new-access', expires_at: 2_000 };
    manager.signinSilent.mockResolvedValue(renewed);
    const listener = vi.fn();
    service.subscribe(listener);
    // Instantiate the manager and register event handlers without reading a user.
    await service.login();
    await callbacks.expired();
    expect(manager.signinSilent).toHaveBeenCalledOnce();
    expect(listener).toHaveBeenCalledWith(renewed);
    expect(listener).not.toHaveBeenCalledWith(null);
  });
});
