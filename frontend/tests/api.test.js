import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../src/config.js', () => ({ config: { apiBaseUrl: '/api' } }));
vi.mock('../src/auth/service.js', () => ({ authService: { getAccessToken: vi.fn() } }));

import { createApiClient, ReceiptUploadError, validateS3UploadUrl } from '../src/api.js';

const family = { id: 7, name: 'Nhà mình', role: 'OWNER', currency: 'VND', invite_code: 'ABC123' };
const plan = {
  receipt_id: 'receipt-1',
  upload: {
    url: 'https://homewallet-receipts.s3.ap-southeast-1.amazonaws.com/',
    fields: { key: 'households/7/receipt-1.jpg', policy: 'signed-policy', 'x-amz-signature': 'signed-value' },
  },
};
const success = (data, status = 200) => ({ ok: true, status, json: async () => data });
const fail = (status) => ({ ok: false, status });

describe('HomeWallet API client', () => {
  let fetchImpl;
  let client;
  let file;
  beforeEach(() => {
    fetchImpl = vi.fn();
    client = createApiClient({ fetchImpl, getAccessToken: async () => 'access-token' });
    file = new File(['image-bytes'], 'hoa-don.jpg', { type: 'image/jpeg' });
  });

  it('lists, creates and joins households with Bearer access token and expected request bodies', async () => {
    fetchImpl.mockResolvedValueOnce(success({ households: [family] }))
      .mockResolvedValueOnce(success({ household: family }))
      .mockResolvedValueOnce(success({ household: family }));
    await expect(client.listHouseholds()).resolves.toEqual([{ ...family, id: '7' }]);
    await client.createHousehold('  Nhà mình  ');
    await client.joinHousehold(' ABC123 ');
    expect(fetchImpl.mock.calls.map(([url]) => url)).toEqual(['/api/households', '/api/households', '/api/households/join']);
    expect(fetchImpl.mock.calls[0][1]).toMatchObject({
      headers: { Authorization: 'Bearer access-token' }, credentials: 'omit', redirect: 'error', cache: 'no-store',
    });
    expect(JSON.parse(fetchImpl.mock.calls[1][1].body)).toEqual({ name: 'Nhà mình' });
    expect(JSON.parse(fetchImpl.mock.calls[2][1].body)).toEqual({ invite_code: 'ABC123' });
  });

  it('requests a presigned POST and sends signed fields before file without leaking auth to S3', async () => {
    const onProgress = vi.fn();
    fetchImpl.mockResolvedValueOnce(success(plan)).mockResolvedValueOnce(success(null, 204));
    await expect(client.uploadReceipt({ householdId: '7', file, onProgress })).resolves.toEqual({ receipt_id: 'receipt-1' });
    const [apiUrl, apiOptions] = fetchImpl.mock.calls[0];
    expect(apiUrl).toBe('/api/receipts');
    expect(JSON.parse(apiOptions.body)).toEqual({
      household_id: '7', filename: 'hoa-don.jpg', content_type: 'image/jpeg', size_bytes: file.size,
    });
    const [uploadUrl, uploadOptions] = fetchImpl.mock.calls[1];
    expect(uploadUrl).toBe(plan.upload.url);
    expect(uploadOptions).toMatchObject({ method: 'POST', credentials: 'omit', redirect: 'error' });
    expect(uploadOptions).not.toHaveProperty('headers');
    expect([...uploadOptions.body.keys()]).toEqual(['key', 'policy', 'x-amz-signature', 'file']);
    expect(uploadOptions.body.get('file').name).toBe(file.name);
    expect(onProgress.mock.calls).toEqual([[0], [100]]);
  });

  it('retains the receipt and retries only S3 after a failed transfer', async () => {
    fetchImpl.mockResolvedValueOnce(success(plan)).mockRejectedValueOnce(new TypeError('network'));
    let error;
    try { await client.uploadReceipt({ householdId: 7, file }); } catch (caught) { error = caught; }
    expect(error).toBeInstanceOf(ReceiptUploadError);
    expect(error).toMatchObject({ receiptId: 'receipt-1', code: 'UPLOAD_NETWORK_ERROR', uploadPlan: plan });
    fetchImpl.mockResolvedValueOnce(success(null, 204));
    await expect(client.resumeReceiptUpload({ plan: error.uploadPlan, file })).resolves.toEqual({ receipt_id: 'receipt-1' });
    expect(fetchImpl.mock.calls.filter(([url]) => url === '/api/receipts')).toHaveLength(1);
  });

  it('does not report S3 rejection as upload success and retains the receipt id', async () => {
    const onProgress = vi.fn();
    fetchImpl.mockResolvedValueOnce(success(plan)).mockResolvedValueOnce(fail(403));
    await expect(client.uploadReceipt({ householdId: 7, file, onProgress })).rejects.toMatchObject({
      code: 'UPLOAD_EXPIRED', receiptId: 'receipt-1', uploadPlan: plan,
    });
    expect(onProgress).not.toHaveBeenCalledWith(100);
  });

  it.each([401, 404, 413, 500])('provides a controlled HTTP %s error without backend content', async (status) => {
    fetchImpl.mockResolvedValue(fail(status));
    await expect(client.listHouseholds()).rejects.toMatchObject({ status, name: 'ApiError' });
  });

  it('rejects missing access tokens before sending a request', async () => {
    const noSession = createApiClient({ fetchImpl, getAccessToken: async () => null });
    await expect(noSession.listHouseholds()).rejects.toMatchObject({ code: 'UNAUTHORIZED' });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('rejects malformed API responses instead of presenting fabricated data', async () => {
    fetchImpl.mockResolvedValueOnce(success({ households: [{ ...family, role: 'ADMIN' }] }));
    await expect(client.listHouseholds()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
    fetchImpl.mockResolvedValueOnce({ ok: true, json: async () => { throw new Error('HTML fallback'); } });
    await expect(client.listHouseholds()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  });

  it('keeps a receipt id if its returned upload plan is unsafe', async () => {
    fetchImpl.mockResolvedValueOnce(success({ ...plan, upload: { ...plan.upload, url: 'https://attacker.example/' } }));
    await expect(client.uploadReceipt({ householdId: 7, file })).rejects.toMatchObject({
      code: 'INVALID_UPLOAD_PLAN', receiptId: 'receipt-1', uploadPlan: undefined,
    });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('rejects signed plans containing a competing file field', async () => {
    fetchImpl.mockResolvedValueOnce(success({ ...plan, upload: { ...plan.upload, fields: { ...plan.upload.fields, file: 'bad' } } }));
    await expect(client.uploadReceipt({ householdId: 7, file })).rejects.toMatchObject({ code: 'INVALID_UPLOAD_PLAN' });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('never sends auth to another API origin or to non-API paths', () => {
    for (const baseUrl of ['https://attacker.example/api', '//attacker.example/api', '/files', '/api/../files', '/api?token=x']) {
      expect(() => createApiClient({ baseUrl, fetchImpl })).toThrow();
    }
  });

  it('rejects unsupported or oversized files before creating a receipt', async () => {
    await expect(client.uploadReceipt({ householdId: 7, file: new File(['x'], 'image.svg', { type: 'image/svg+xml' }) }))
      .rejects.toMatchObject({ code: 'INVALID_FILE' });
    await expect(client.uploadReceipt({ householdId: 7, file: new File([new Uint8Array(2 * 1024 * 1024 + 1)], 'huge.jpg', { type: 'image/jpeg' }) }))
      .rejects.toMatchObject({ code: 'INVALID_FILE' });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('preserves a retry plan on abort and never sends the aborted S3 request', async () => {
    const controller = new AbortController();
    controller.abort();
    await expect(client.resumeReceiptUpload({ plan, file, signal: controller.signal })).rejects.toMatchObject({
      code: 'ABORTED', receiptId: 'receipt-1', uploadPlan: plan,
    });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('reports API network failure without including raw request errors', async () => {
    fetchImpl.mockRejectedValue(new Error('secret-token-in-error'));
    await expect(client.listHouseholds()).rejects.toMatchObject({ code: 'NETWORK_ERROR' });
    await expect(client.listHouseholds()).rejects.not.toThrow('secret-token');
  });

  it('blocks duplicate creation when the POST response is lost on the network', async () => {
    fetchImpl.mockRejectedValueOnce(new TypeError('network disconnected after request'));
    await expect(client.uploadReceipt({ householdId: 7, file })).rejects.toMatchObject({
      name: 'ReceiptUploadError', code: 'RECEIPT_CREATION_UNKNOWN', creationUncertain: true,
      receiptId: undefined, uploadPlan: undefined,
    });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(fetchImpl.mock.calls[0][0]).toBe('/api/receipts');
  });

  it('marks creation uncertain when POST is aborted after dispatch', async () => {
    const controller = new AbortController();
    fetchImpl.mockImplementationOnce(async () => {
      controller.abort();
      throw new DOMException('Request aborted', 'AbortError');
    });
    await expect(client.requestReceiptUpload(7, file, { signal: controller.signal })).rejects.toMatchObject({
      code: 'RECEIPT_CREATION_UNKNOWN', creationUncertain: true, receiptId: undefined, uploadPlan: undefined,
    });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('marks creation uncertain when a successful POST has unreadable JSON', async () => {
    fetchImpl.mockResolvedValueOnce({ ok: true, status: 201, json: async () => { throw new SyntaxError('Incomplete JSON'); } });
    await expect(client.requestReceiptUpload(7, file)).rejects.toMatchObject({
      code: 'RECEIPT_CREATION_UNKNOWN', creationUncertain: true, receiptId: undefined, uploadPlan: undefined,
    });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('marks creation uncertain if a successful response does not identify its receipt', async () => {
    fetchImpl.mockResolvedValueOnce(success({ upload: plan.upload }, 201));
    await expect(client.requestReceiptUpload(7, file)).rejects.toMatchObject({
      code: 'RECEIPT_CREATION_UNKNOWN', creationUncertain: true,
    });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it.each([408, 500, 502, 503])('does not assume HTTP %s means the receipt was not created', async (status) => {
    fetchImpl.mockResolvedValueOnce(fail(status));
    await expect(client.requestReceiptUpload(7, file)).rejects.toMatchObject({
      code: 'RECEIPT_CREATION_UNKNOWN', creationUncertain: true,
    });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('allows a deliberate retry after an explicit validation rejection', async () => {
    fetchImpl.mockResolvedValueOnce(fail(413)).mockResolvedValueOnce(success(plan, 201));
    await expect(client.requestReceiptUpload(7, file)).rejects.toMatchObject({ status: 413, code: 'HTTP_ERROR' });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    await expect(client.requestReceiptUpload(7, file)).resolves.toEqual(plan);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('keeps pre-aborted creation safe to retry without sending a POST', async () => {
    const controller = new AbortController();
    controller.abort();
    await expect(client.requestReceiptUpload(7, file, { signal: controller.signal })).rejects.toMatchObject({ code: 'ABORTED' });
    expect(fetchImpl).not.toHaveBeenCalled();
    fetchImpl.mockResolvedValueOnce(success(plan));
    await expect(client.requestReceiptUpload(7, file)).resolves.toEqual(plan);
  });

  it('does not dispatch creation if the signal aborts while acquiring an access token', async () => {
    const controller = new AbortController();
    const duringAuth = createApiClient({
      fetchImpl,
      getAccessToken: async () => { controller.abort(); return 'valid-token'; },
    });
    await expect(duringAuth.requestReceiptUpload(7, file, { signal: controller.signal })).rejects.toMatchObject({ code: 'ABORTED' });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('does not mark missing auth or invalid local input as uncertain creation', async () => {
    const getAccessToken = vi.fn(async () => null);
    const noSession = createApiClient({ fetchImpl, getAccessToken });
    await expect(noSession.requestReceiptUpload(7, file)).rejects.toMatchObject({ code: 'UNAUTHORIZED' });
    expect(fetchImpl).not.toHaveBeenCalled();
    getAccessToken.mockResolvedValueOnce('new-access-token');
    fetchImpl.mockResolvedValueOnce(success(plan));
    await expect(noSession.requestReceiptUpload(7, file)).resolves.toEqual(plan);
    expect(fetchImpl).toHaveBeenCalledTimes(1);

    fetchImpl.mockClear();
    await expect(client.requestReceiptUpload('', file)).rejects.toMatchObject({ code: 'INVALID_INPUT' });
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});

describe('S3 presigned POST URL validation', () => {
  it.each([
    'https://homewallet.s3.amazonaws.com/',
    'https://homewallet.s3.ap-southeast-1.amazonaws.com/',
    'https://homewallet.s3-ap-southeast-1.amazonaws.com/',
    'https://homewallet.s3.cn-north-1.amazonaws.com.cn/',
  ])('accepts AWS bucket endpoint %s', (url) => expect(validateS3UploadUrl(url)).toBe(url));

  it.each([
    'http://homewallet.s3.amazonaws.com/',
    'https://homewallet.s3.amazonaws.com.evil.example/',
    'https://amazonaws.com/',
    'https://s3.amazonaws.com/',
    'https://homewallet.s3.amazonaws.com:444/',
    'https://user:password@homewallet.s3.amazonaws.com/',
    'https://homewallet.s3.amazonaws.com/?redirect=https://evil.example',
    'https://homewallet.s3.amazonaws.com/upload',
    'https://homewallet.s3.ap-southeast-1.amazonaws.com.cn/',
    'https://homewallet.s3.cn-north-1.amazonaws.com/',
  ])('rejects unsafe or unsupported endpoint %s', (url) => expect(() => validateS3UploadUrl(url)).toThrow());
});
