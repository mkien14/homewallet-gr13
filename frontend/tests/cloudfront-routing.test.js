// @vitest-environment node

import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { describe, expect, it } from 'vitest';

const source = readFileSync(
  new URL('../deploy/cloudfront-viewer-request.js', import.meta.url),
  'utf8',
);
const handler = runInNewContext(`${source}\nhandler;`);

function request(uri, method = 'GET') {
  return {
    uri,
    method,
    headers: { authorization: { value: 'Bearer test-access-token' } },
    querystring: {},
  };
}

describe('CloudFront frontend viewer-request routing', () => {
  it.each(['/', '/households', '/households/', '/upload', '/upload/', '/auth/callback', '/auth/callback/'])(
    'serves index.html on the known SPA route %s',
    (uri) => {
      expect(handler({ request: request(uri) }).uri).toBe('/index.html');
    },
  );

  it('keeps OAuth query parameters and headers intact on the callback route', () => {
    const callback = request('/auth/callback');
    callback.querystring = { code: { value: 'authorization-code' }, state: { value: 'state-value' } };
    const result = handler({ request: callback });

    expect(result).toBe(callback);
    expect(result.querystring).toEqual({ code: { value: 'authorization-code' }, state: { value: 'state-value' } });
    expect(result.headers.authorization.value).toBe('Bearer test-access-token');
  });

  it.each(['/api', '/api/households', '/api/receipts', '/api/not-found'])(
    'does not rewrite the backend URI %s',
    (uri) => {
      expect(handler({ request: request(uri) }).uri).toBe(uri);
    },
  );

  it.each(['/assets/app-a1b2.js', '/assets/app-a1b2.css', '/favicon.svg', '/index.html', '/unknown', '/toString', '/constructor', '/__proto__'])(
    'does not turn an asset or unknown URI into index.html: %s',
    (uri) => {
      expect(handler({ request: request(uri) }).uri).toBe(uri);
    },
  );

  it('supports HEAD on a known SPA route', () => {
    expect(handler({ request: request('/households', 'HEAD') }).uri).toBe('/index.html');
  });

  it.each(['POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])(
    'preserves %s requests instead of returning the SPA shell',
    (method) => {
      expect(handler({ request: request('/upload', method) }).uri).toBe('/upload');
    },
  );
});
