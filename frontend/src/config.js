const text = (value) => (typeof value === 'string' ? value.trim() : '');

function webUrl(value, { allowLocalHttp = false } = {}) {
  const url = new URL(value);
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
  if (
    (url.protocol !== 'https:' && !(allowLocalHttp && local && url.protocol === 'http:')) ||
    url.username || url.password || url.search || url.hash
  ) {
    throw new Error('URL không hợp lệ');
  }
  return url;
}

/** Vite variables are public build-time settings. Never put a client secret here. */
export function readConfig(env = {}, origin = 'http://localhost:5173') {
  const errors = [];
  const cognitoAuthority = text(env.VITE_COGNITO_AUTHORITY).replace(/\/+$/, '');
  const cognitoDomain = text(env.VITE_COGNITO_DOMAIN).replace(/\/+$/, '');
  const cognitoClientId = text(env.VITE_COGNITO_CLIENT_ID);
  const redirectUri = text(env.VITE_COGNITO_REDIRECT_URI) || `${origin}/auth/callback`;
  const logoutUri = text(env.VITE_COGNITO_LOGOUT_URI) || `${origin}/`;
  const apiBaseUrl = text(env.VITE_API_BASE_URL).replace(/\/+$/, '') || '/api';

  // The bearer token must only go through this site's CloudFront /api behavior.
  if (apiBaseUrl !== '/api') {
    errors.push('VITE_API_BASE_URL phải là /api trên cùng website.');
  }

  if (!cognitoAuthority || !cognitoDomain || !cognitoClientId) {
    errors.push('Cần cấu hình VITE_COGNITO_AUTHORITY, VITE_COGNITO_DOMAIN và VITE_COGNITO_CLIENT_ID để đăng nhập.');
  }
  if (cognitoAuthority) {
    try {
      const authority = webUrl(cognitoAuthority);
      if (
        !/^cognito-idp\.[a-z0-9-]+\.amazonaws\.com(?:\.cn)?$/.test(authority.hostname) ||
        !/^\/[a-z0-9-]+_[A-Za-z0-9]+$/.test(authority.pathname) || authority.port
      ) throw new Error();
    } catch {
      errors.push('VITE_COGNITO_AUTHORITY phải là HTTPS issuer của Cognito user pool.');
    }
  }
  if (cognitoDomain) {
    try {
      const domain = webUrl(cognitoDomain);
      if (domain.pathname !== '/' || domain.port) throw new Error();
    } catch {
      errors.push('VITE_COGNITO_DOMAIN phải là HTTPS domain đăng nhập Cognito, không có đường dẫn.');
    }
  }
  if (cognitoClientId && !/^[a-zA-Z0-9]+$/.test(cognitoClientId)) {
    errors.push('VITE_COGNITO_CLIENT_ID không hợp lệ.');
  }
  for (const [name, value, expectedPath] of [
    ['VITE_COGNITO_REDIRECT_URI', redirectUri, '/auth/callback'],
    ['VITE_COGNITO_LOGOUT_URI', logoutUri, '/'],
  ]) {
    try {
      const url = webUrl(value, { allowLocalHttp: true });
      if (url.origin !== origin || url.pathname !== expectedPath) throw new Error();
    } catch {
      errors.push(`${name} phải trỏ đến ${expectedPath} trên cùng website (HTTPS, hoặc HTTP localhost khi phát triển).`);
    }
  }
  if (text(env.VITE_COGNITO_CLIENT_SECRET)) {
    errors.push('Frontend phải dùng Cognito public app client không có client secret.');
  }

  return Object.freeze({
    apiBaseUrl: apiBaseUrl === '/api' ? apiBaseUrl : '/api',
    cognitoAuthority,
    cognitoDomain,
    cognitoClientId,
    redirectUri,
    logoutUri,
    isAuthConfigured: errors.length === 0,
    configurationError: errors.join(' '),
  });
}

export const config = readConfig(
  import.meta.env ?? {},
  globalThis.location?.origin ?? 'http://localhost:5173',
);
