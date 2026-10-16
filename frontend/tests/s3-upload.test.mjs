import test from 'node:test';
import assert from 'node:assert/strict';
import { PresignedPostUploadError, uploadToS3, validateS3UploadUrl } from '../src/receipts/s3-upload.mjs';

const url = 'https://homewallet-receipts.s3.ap-southeast-1.amazonaws.com/';
const image = (type = 'image/jpeg', size = 32, name = 'receipt.jpg') => new File([new Uint8Array(size)], name, { type });
const fields = () => ({
  key: 'receipts/household-1/receipt-42.jpg',
  policy: 'signed-policy==',
  'x-amz-algorithm': 'AWS4-HMAC-SHA256',
  'x-amz-credential': 'access-key/20261016/ap-southeast-1/s3/aws4_request',
  'x-amz-date': '20261016T000000Z',
  'x-amz-signature': 'signed-value',
  'x-amz-security-token': 'session/token+with=signed/characters',
  'Content-Type': 'image/jpeg',
  success_action_status: '204',
});
const options = (overrides = {}) => ({ url, fields: fields(), file: image(), fetchImpl: async () => new Response(null, { status: 204 }), ...overrides });

async function rejectsWith(input, code, status = 0) {
  await assert.rejects(uploadToS3(input), (error) => {
    assert.ok(error instanceof PresignedPostUploadError);
    assert.equal(error.name, 'PresignedPostUploadError');
    assert.equal(error.code, code);
    assert.equal(error.status, status);
    return true;
  });
}

test('accepts HTTPS bucket virtual-host endpoints and normalizes a missing root slash', () => {
  for (const endpoint of [
    'https://homewallet-receipts.s3.amazonaws.com',
    'https://homewallet-receipts.s3.ap-southeast-1.amazonaws.com',
    'https://homewallet-receipts.s3-ap-southeast-1.amazonaws.com',
    'https://homewallet-receipts.s3.us-gov-west-1.amazonaws.com',
    'https://homewallet-receipts.s3.cn-north-1.amazonaws.com.cn',
    'https://homewallet-receipts.s3-cn-northwest-1.amazonaws.com.cn',
  ]) assert.equal(validateS3UploadUrl(endpoint), `${endpoint}/`);
  assert.equal(validateS3UploadUrl(url), url);
});

test('rejects unsafe, non-bucket and unsupported S3 URL forms', () => {
  for (const endpoint of [
    undefined, null, {}, new URL(url), '', ` ${url}`, `${url}\n`,
    'http://homewallet-receipts.s3.amazonaws.com/',
    'https://homewallet-receipts.s3.amazonaws.com:443/',
    'https://homewallet-receipts.s3.amazonaws.com:8443/',
    'https://user:password@homewallet-receipts.s3.amazonaws.com/',
    'https://homewallet-receipts.s3.amazonaws.com@evil.example/',
    'https://homewallet-receipts.s3.amazonaws.com.evil.example/',
    'https://homewallet-receipts.s3.amazonaws.com/?policy=secret',
    'https://homewallet-receipts.s3.amazonaws.com/?',
    'https://homewallet-receipts.s3.amazonaws.com/#',
    'https://homewallet-receipts.s3.amazonaws.com/file.jpg',
    'https://homewallet-receipts.s3.amazonaws.com/./',
    'https://homewallet-receipts.s3.amazonaws.com\\',
    'https://homewallet-receipts%2es3.amazonaws.com/',
    'https://homewallet-receipts.s3.amazonaws.com./',
    'https://home.wallet.s3.amazonaws.com/',
    'https://ab.s3.amazonaws.com/',
    `https://${'a'.repeat(64)}.s3.amazonaws.com/`,
    'https://-homewallet.s3.amazonaws.com/',
    'https://homewallet-.s3.amazonaws.com/',
    'https://xn--homewallet.s3.amazonaws.com/',
    'https://homewallet-s3alias.s3.amazonaws.com/',
    'https://homewallet--ol-s3.s3.amazonaws.com/',
    'https://homewallet--x-s3.s3.amazonaws.com/',
    'https://homewallet--table-s3.s3.amazonaws.com/',
    'https://homewallet-receipts.s3.cn-north-1.amazonaws.com/',
    'https://homewallet-receipts.s3.ap-southeast-1.amazonaws.com.cn/',
    'https://homewallet-receipts.s3.amazonaws.com.cn/',
    'https://s3.ap-southeast-1.amazonaws.com/homewallet-receipts/',
    'https://homewallet-receipts.s3-website-ap-southeast-1.amazonaws.com/',
    'https://homewallet-receipts.s3-accelerate.amazonaws.com/',
    'https://homewallet-receipts.s3.dualstack.ap-southeast-1.amazonaws.com/',
    'https://localhost/', 'https://127.0.0.1/', 'https://[::1]/',
  ]) assert.throws(() => validateS3UploadUrl(endpoint), (error) => error.code === 'INVALID_UPLOAD_URL', String(endpoint));
});

test('preserves signed fields and session token, places file last, and isolates browser auth', async () => {
  const signedFields = Object.freeze(fields());
  const file = image();
  const controller = new AbortController();
  const progress = [];
  let calls = 0;
  const result = await uploadToS3(options({
    fields: signedFields, file, signal: controller.signal,
    onProgress: (value) => progress.push(value),
    fetchImpl: async (requestUrl, init) => {
      calls += 1;
      assert.equal(requestUrl, url);
      assert.equal(init.method, 'POST');
      assert.equal(init.credentials, 'omit');
      assert.equal(init.redirect, 'error');
      assert.equal(init.signal, controller.signal);
      assert.equal(Object.hasOwn(init, 'headers'), false);
      assert.equal(Object.hasOwn(init, 'Authorization'), false);
      assert.ok(init.body instanceof FormData);
      const entries = [...init.body.entries()];
      assert.deepEqual(entries.slice(0, -1), Object.entries(signedFields));
      assert.equal(entries.at(-1)[0], 'file');
      assert.equal(entries.at(-1)[1].name, file.name);
      assert.equal(entries.at(-1)[1].type, file.type);
      assert.deepEqual(await entries.at(-1)[1].arrayBuffer(), await file.arrayBuffer());
      return new Response(null, { status: 204 });
    },
  }));
  assert.deepEqual(result, { status: 204 });
  assert.deepEqual(progress, [0, 100]);
  assert.equal(calls, 1);
  assert.equal(signedFields['x-amz-security-token'], 'session/token+with=signed/characters');
});

for (const status of [200, 201, 204]) {
  test(`accepts S3 successful status ${status} without parsing the response body`, async () => {
    const result = await uploadToS3(options({ fetchImpl: async () => ({ ok: true, status, text: () => { throw new Error('must not read signed S3 response'); } }) }));
    assert.deepEqual(result, { status });
  });
}

test('accepts all supported image types and the exact 2 MiB boundary', async () => {
  for (const type of ['image/jpeg', 'image/png', 'image/webp']) {
    assert.deepEqual(await uploadToS3(options({ file: image(type, 2 * 1024 * 1024) })), { status: 204 });
  }
});

test('accepts null-prototype signed fields and preserves empty optional values', async () => {
  const signedFields = Object.assign(Object.create(null), fields(), { optional: '' });
  await uploadToS3(options({ fields: signedFields, fetchImpl: async (_url, init) => {
    assert.equal(init.body.get('optional'), '');
    return new Response(null, { status: 204 });
  } }));
});

test('rejects invalid signed field objects before sending a request', async () => {
  const accessor = { key: 'safe.jpg' };
  Object.defineProperty(accessor, 'policy', { enumerable: true, get() { throw new Error('must not invoke getters'); } });
  const hidden = { key: 'safe.jpg' };
  Object.defineProperty(hidden, 'policy', { value: 'hidden' });
  for (const invalid of [
    undefined, null, [], new Date(), {}, { key: '' }, { key: 1 },
    { ...fields(), file: 'competing' }, { ...fields(), FILE: 'competing' },
    { ...fields(), FiLe: 'competing' }, { ...fields(), '': 'empty field name' },
    { ...fields(), policy: 123 }, { ...fields(), policy: null },
    { ...fields(), nested: {} }, { ...fields(), [Symbol('policy')]: 'hidden' },
    Object.create({ key: 'inherited.jpg' }), accessor, hidden,
  ]) await rejectsWith(options({ fields: invalid, fetchImpl: () => assert.fail('must not fetch') }), 'INVALID_FIELDS');
});

test('rejects invalid files and oversized images before sending a request', async () => {
  for (const file of [
    undefined, null, {}, new Blob(['plain blob'], { type: 'image/jpeg' }),
    { name: 'receipt.jpg', size: 10, type: 'image/jpeg' },
    image('image/jpeg', 0), image('image/jpeg', 2 * 1024 * 1024 + 1),
    image('image/gif'), image('image/svg+xml'), image('text/html'),
    image('image/jpeg', 1, ''), image('image/jpeg', 1, '   '),
  ]) await rejectsWith(options({ file, fetchImpl: () => assert.fail('must not fetch') }), 'INVALID_FILE');
});

test('invalid URL cannot cause a request or a progress callback', async () => {
  await rejectsWith(options({ url: 'https://evil.example/', fetchImpl: () => assert.fail('must not fetch'), onProgress: () => assert.fail('must not report progress') }), 'INVALID_UPLOAD_URL');
});

test('403 reports rejection without claiming that every forbidden response is an expired signature', async () => {
  let calls = 0;
  const progress = [];
  await rejectsWith(options({ onProgress: (value) => progress.push(value), fetchImpl: async () => {
    calls += 1;
    return { ok: false, status: 403, text: () => assert.fail('must not expose response XML') };
  } }), 'UPLOAD_FORBIDDEN', 403);
  assert.equal(calls, 1);
  assert.deepEqual(progress, [0]);
});

for (const status of [400, 413, 429, 500, 503]) {
  test(`preserves HTTP ${status} and never retries automatically`, async () => {
    let calls = 0;
    await rejectsWith(options({ fetchImpl: async () => { calls += 1; return new Response('private S3 details', { status }); } }), 'UPLOAD_HTTP_ERROR', status);
    assert.equal(calls, 1);
  });
}

test('network/CORS failures return controlled text without raw exception or signing details', async () => {
  const secret = 'SECRET-signature-response-url';
  await assert.rejects(uploadToS3(options({ fetchImpl: async () => { throw new Error(secret); } })), (error) => {
    assert.equal(error.code, 'UPLOAD_NETWORK_ERROR');
    assert.equal(error.message.includes(secret), false);
    assert.equal(error.cause, undefined);
    return true;
  });
});

test('a signal aborted before upload prevents network and progress calls', async () => {
  const controller = new AbortController();
  controller.abort();
  await rejectsWith(options({ signal: controller.signal, fetchImpl: () => assert.fail('must not fetch'), onProgress: () => assert.fail('must not report progress') }), 'ABORTED');
});

test('an abort from the initial progress callback still prevents network access', async () => {
  const controller = new AbortController();
  await rejectsWith(options({ signal: controller.signal, onProgress: () => controller.abort(), fetchImpl: () => assert.fail('must not fetch') }), 'ABORTED');
});

test('aborting an in-flight request returns ABORTED without completed progress', async () => {
  const controller = new AbortController();
  const progress = [];
  await rejectsWith(options({ signal: controller.signal, onProgress: (value) => progress.push(value), fetchImpl: async (_url, init) => {
    controller.abort();
    assert.equal(init.signal.aborted, true);
    throw new DOMException('private abort detail', 'AbortError');
  } }), 'ABORTED');
  assert.deepEqual(progress, [0]);
});

test('a fetch AbortError also maps to ABORTED without a supplied signal', async () => {
  await rejectsWith(options({ fetchImpl: async () => { throw new DOMException('aborted', 'AbortError'); } }), 'ABORTED');
});

test('does not report success if the signal aborted before the response resolves', async () => {
  const controller = new AbortController();
  const progress = [];
  await rejectsWith(options({ signal: controller.signal, onProgress: (value) => progress.push(value), fetchImpl: async () => {
    controller.abort();
    return new Response(null, { status: 204 });
  } }), 'ABORTED');
  assert.deepEqual(progress, [0]);
});

test('progress callback exceptions cannot turn a successful upload into an error', async () => {
  assert.deepEqual(await uploadToS3(options({ onProgress: () => { throw new Error('UI callback failure'); } })), { status: 204 });
  assert.deepEqual(await uploadToS3(options({ onProgress: async () => { throw new Error('async UI callback failure'); } })), { status: 204 });
});

test('malformed fetch responses use a controlled network error', async () => {
  for (const response of [undefined, null, {}, { status: 204 }, { ok: true }]) {
    await rejectsWith(options({ fetchImpl: async () => response }), 'UPLOAD_NETWORK_ERROR');
  }
});
