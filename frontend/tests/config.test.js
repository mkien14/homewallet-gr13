// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { readConfig } from '../src/config.js';

const origin = 'https://wallet.example.com';
const env = {
  VITE_COGNITO_AUTHORITY: 'https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_Abc123',
  VITE_COGNITO_DOMAIN: 'https://homewallet.auth.ap-southeast-1.amazoncognito.com',
  VITE_COGNITO_CLIENT_ID: 'publicclient123',
};

describe('frontend configuration', () => {
  it('uses this CloudFront origin for API, callback and logout', () => {
    expect(readConfig(env, origin)).toMatchObject({
      apiBaseUrl: '/api',
      redirectUri: `${origin}/auth/callback`,
      logoutUri: `${origin}/`,
      isAuthConfigured: true,
      configurationError: '',
    });
  });

  it('can render the setup page without Cognito variables', () => {
    const config = readConfig({}, origin);
    expect(config.isAuthConfigured).toBe(false);
    expect(config.configurationError).toContain('VITE_COGNITO_AUTHORITY');
    expect(config.apiBaseUrl).toBe('/api');
  });

  it('accepts localhost callbacks for Vite development and trims inputs', () => {
    expect(readConfig({ ...env, VITE_COGNITO_DOMAIN: ` ${env.VITE_COGNITO_DOMAIN}/ ` }, 'http://localhost:5173'))
      .toMatchObject({ isAuthConfigured: true, cognitoDomain: env.VITE_COGNITO_DOMAIN });
  });

  it.each([
    ['VITE_API_BASE_URL', 'https://other.example.com/api'],
    ['VITE_API_BASE_URL', '//other.example.com/api'],
    ['VITE_API_BASE_URL', '/api?token=secret'],
    ['VITE_COGNITO_AUTHORITY', 'http://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_Abc123'],
    ['VITE_COGNITO_AUTHORITY', 'https://hosted-ui.example.com'],
    ['VITE_COGNITO_DOMAIN', 'http://login.example.com'],
    ['VITE_COGNITO_DOMAIN', 'https://login.example.com/oauth2/authorize'],
    ['VITE_COGNITO_DOMAIN', 'https://user:password@login.example.com'],
    ['VITE_COGNITO_REDIRECT_URI', 'https://other.example.com/auth/callback'],
    ['VITE_COGNITO_REDIRECT_URI', `${origin}/wrong-callback`],
    ['VITE_COGNITO_REDIRECT_URI', `${origin}/auth/callback#fragment`],
    ['VITE_COGNITO_LOGOUT_URI', 'https://other.example.com/'],
    ['VITE_COGNITO_CLIENT_SECRET', 'should-never-be-public'],
  ])('fails closed for unsafe %s', (name, value) => {
    const config = readConfig({ ...env, [name]: value }, origin);
    expect(config.isAuthConfigured).toBe(false);
    expect(config.configurationError).toContain(name === 'VITE_COGNITO_CLIENT_SECRET' ? 'client secret' : name);
    expect(config.configurationError).not.toContain(value);
    expect(config.apiBaseUrl).toBe('/api');
  });
});
