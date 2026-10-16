import { config } from './config.js';
import { authService } from './auth/service.js';

const MAX_UPLOAD_BYTES = 2 * 1024 * 1024;
const ALLOWED_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);

export class ApiError extends Error {
  constructor(message, { status = 0, code = 'API_ERROR', cause } = {}) {
    super(message, cause ? { cause } : undefined);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

/** Keeps the already-created receipt so a failed S3 transfer can be retried safely. */
export class ReceiptUploadError extends ApiError {
  constructor(message, { plan, cause, code = 'UPLOAD_FAILED', creationUncertain = false } = {}) {
    super(message, { code, cause });
    this.name = 'ReceiptUploadError';
    this.receiptId = plan?.receipt_id;
    this.uploadPlan = plan;
    this.creationUncertain = creationUncertain;
  }
}

function uncertainReceiptCreation(cause) {
  return new ReceiptUploadError(
    'Chưa xác định được API đã tạo hóa đơn hay chưa. Không gửi tạo lại; hãy kiểm tra hóa đơn đang chờ trên backend trước khi tiếp tục.',
    { code: 'RECEIPT_CREATION_UNKNOWN', creationUncertain: true, cause },
  );
}

function invalidResponse() {
  return new ApiError('Dữ liệu API chưa đúng định dạng HomeWallet. Vui lòng kiểm tra kết nối backend.', {
    code: 'INVALID_RESPONSE',
  });
}

function identifier(value) {
  if ((typeof value === 'string' && value.trim()) || (Number.isSafeInteger(value) && value > 0)) {
    return String(value);
  }
  throw invalidResponse();
}

function household(value) {
  if (!value || typeof value !== 'object' || typeof value.name !== 'string' || !value.name.trim()
    || !['OWNER', 'MEMBER'].includes(value.role?.toUpperCase?.())
    || typeof value.currency !== 'string' || !/^[A-Z]{3}$/.test(value.currency)) {
    throw invalidResponse();
  }
  if (value.invite_code !== undefined && typeof value.invite_code !== 'string') throw invalidResponse();
  return {
    id: identifier(value.id),
    name: value.name,
    role: value.role.toUpperCase(),
    currency: value.currency,
    ...(value.invite_code === undefined ? {} : { invite_code: value.invite_code }),
  };
}

function textInput(value, label, maximum) {
  if (typeof value !== 'string' || !value.trim() || value.trim().length > maximum) {
    throw new ApiError(`${label} phải có từ 1 đến ${maximum} ký tự.`, { code: 'INVALID_INPUT' });
  }
  return value.trim();
}

function httpError(status) {
  const messages = {
    400: 'Thông tin gửi lên chưa hợp lệ. Vui lòng kiểm tra và thử lại.',
    401: 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.',
    403: 'Bạn không có quyền thực hiện thao tác với hộ gia đình này.',
    404: 'API này chưa có trên backend hoặc dữ liệu không còn tồn tại. Vui lòng kiểm tra cấu hình triển khai.',
    409: 'Dữ liệu đã thay đổi hoặc bạn đã tham gia hộ gia đình này. Vui lòng tải lại danh sách.',
    413: 'Ảnh vượt quá dung lượng API cho phép. Vui lòng chọn ảnh nhỏ hơn.',
    422: 'Thông tin gửi lên chưa hợp lệ. Vui lòng kiểm tra và thử lại.',
    429: 'Có quá nhiều yêu cầu. Vui lòng đợi một lúc rồi thử lại.',
  };
  return new ApiError(messages[status] ?? 'Máy chủ đang gặp lỗi. Vui lòng thử lại sau.', {
    status,
    code: status === 401 ? 'UNAUTHORIZED' : 'HTTP_ERROR',
  });
}

function cancelled() {
  return new ApiError('Đã hủy tải ảnh. Bạn có thể thử lại với cùng hóa đơn.', { code: 'ABORTED' });
}

/** Accept only S3 bucket endpoints, never arbitrary URLs received in an API response. */
export function validateS3UploadUrl(value) {
  let url;
  try { url = new URL(value); } catch { throw invalidResponse(); }
  const match = url.hostname.match(/^(.+)\.s3(?:[.-]([a-z]{2}(?:-gov)?-[a-z]+-\d))?\.amazonaws\.com(\.cn)?$/);
  const bucket = match?.[1];
  const region = match?.[2];
  if (url.protocol !== 'https:' || url.port || url.username || url.password || url.search || url.hash
    || url.pathname !== '/' || !bucket || bucket.length < 3 || bucket.length > 63
    || !/^[a-z0-9][a-z0-9.-]*[a-z0-9]$/.test(bucket) || bucket.includes('..')
    || bucket.split('.').some((part) => part.startsWith('-') || part.endsWith('-'))
    || /^\d+\.\d+\.\d+\.\d+$/.test(bucket)
    || (Boolean(match[3]) !== Boolean(region?.startsWith('cn-')))) {
    throw invalidResponse();
  }
  return url.href;
}

function uploadPlan(value) {
  const fields = value?.upload?.fields;
  if (!fields || typeof fields !== 'object' || Array.isArray(fields)
    || typeof fields.key !== 'string' || !fields.key
    || !Object.entries(fields).every(([key, field]) => key && key.toLowerCase() !== 'file' && typeof field === 'string')) {
    throw invalidResponse();
  }
  return Object.freeze({
    receipt_id: identifier(value.receipt_id),
    upload: Object.freeze({
      url: validateS3UploadUrl(value.upload.url),
      fields: Object.freeze({ ...fields }),
    }),
  });
}

function uploadFile(file) {
  if (!file || typeof file.name !== 'string' || !ALLOWED_IMAGE_TYPES.has(file.type)
    || !Number.isSafeInteger(file.size) || file.size <= 0 || file.size > MAX_UPLOAD_BYTES) {
    throw new ApiError('Ảnh tải lên phải là JPEG, PNG hoặc WebP đã nén, dung lượng tối đa 2 MiB.', {
      code: 'INVALID_FILE',
    });
  }
}

export function createApiClient({ baseUrl = '/api', getAccessToken, fetchImpl = globalThis.fetch } = {}) {
  const origin = globalThis.location?.origin ?? 'http://localhost';
  const base = new URL(baseUrl, origin);
  if (base.origin !== origin || !/^\/api(?:\/|$)/.test(base.pathname) || base.search || base.hash
    || base.username || base.password) {
    throw new ApiError('API phải sử dụng đường dẫn /api trên cùng tên miền website.', { code: 'INVALID_CONFIG' });
  }
  const path = base.pathname.replace(/\/$/, '');

  async function request(endpoint, { method = 'GET', body, signal, onDispatch } = {}) {
    if (signal?.aborted) throw cancelled();
    const token = await getAccessToken?.();
    if (typeof token !== 'string' || !token.trim()) throw httpError(401);
    if (signal?.aborted) throw cancelled();
    let response;
    try {
      onDispatch?.();
      response = await fetchImpl(`${path}${endpoint}`, {
        method,
        headers: {
          Accept: 'application/json',
          Authorization: `Bearer ${token}`,
          ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        },
        credentials: 'omit',
        redirect: 'error',
        cache: 'no-store',
        signal,
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
    } catch (error) {
      if (error?.name === 'AbortError' || signal?.aborted) throw cancelled();
      throw new ApiError('Không kết nối được API. Vui lòng kiểm tra mạng và cấu hình /api trên CloudFront.', {
        code: 'NETWORK_ERROR',
      });
    }
    if (!response.ok) throw httpError(response.status);
    try { return await response.json(); } catch { throw invalidResponse(); }
  }

  async function requestReceiptUpload(householdId, file, { signal } = {}) {
    uploadFile(file);
    let dispatched = false;
    let data;
    try {
      data = await request('/receipts', {
        method: 'POST',
        body: {
          household_id: textInput(String(householdId ?? ''), 'Mã hộ gia đình', 128),
          filename: file.name,
          content_type: file.type,
          size_bytes: file.size,
        },
        signal,
        onDispatch: () => { dispatched = true; },
      });
    } catch (error) {
      // The request can reach the backend even if its response never reaches this browser.
      // A caller must reconcile the pending receipt instead of blindly creating a duplicate.
      if (dispatched && (['NETWORK_ERROR', 'ABORTED', 'INVALID_RESPONSE'].includes(error.code)
        || error.status >= 500 || error.status === 408)) {
        throw uncertainReceiptCreation(error);
      }
      throw error;
    }
    try { return uploadPlan(data); } catch (error) {
      // Creation may have succeeded even when its upload contract is invalid. Do not invite duplicate creation.
      let receiptId;
      try { receiptId = identifier(data?.receipt_id); } catch { /* No usable receipt id. */ }
      if (!receiptId) throw uncertainReceiptCreation(error);
      const failure = new ReceiptUploadError(
        'API đã trả về thông tin tải ảnh chưa hợp lệ. Không tạo lại hóa đơn; hãy kiểm tra backend.',
        { code: 'INVALID_UPLOAD_PLAN', cause: error },
      );
      failure.receiptId = receiptId;
      throw failure;
    }
  }

  async function resumeReceiptUpload({ plan: providedPlan, file, onProgress, signal }) {
    uploadFile(file);
    const plan = uploadPlan(providedPlan);
    const form = new FormData();
    Object.entries(plan.upload.fields).forEach(([key, value]) => form.append(key, value));
    form.append('file', file, file.name);
    if (signal?.aborted) {
      throw new ReceiptUploadError('Đã hủy tải ảnh. Bạn có thể thử lại với cùng hóa đơn.', { plan, code: 'ABORTED' });
    }
    onProgress?.(0);
    let response;
    try {
      response = await fetchImpl(plan.upload.url, {
        method: 'POST',
        body: form,
        credentials: 'omit',
        redirect: 'error',
        signal,
      });
    } catch (error) {
      throw new ReceiptUploadError(
        error?.name === 'AbortError' || signal?.aborted
          ? 'Đã hủy tải ảnh. Bạn có thể thử lại với cùng hóa đơn.'
          : 'Chưa tải được ảnh lên S3. Kiểm tra mạng hoặc CORS và thử lại với cùng hóa đơn.',
        { plan, code: error?.name === 'AbortError' || signal?.aborted ? 'ABORTED' : 'UPLOAD_NETWORK_ERROR' },
      );
    }
    if (!response.ok) {
      throw new ReceiptUploadError(
        response.status === 403
          ? 'S3 từ chối tải ảnh: chữ ký có thể đã hết hạn. Không tạo hóa đơn mới; hãy kiểm tra hoặc cấp lại chữ ký cho hóa đơn này.'
          : 'S3 chưa nhận được ảnh. Bạn có thể thử tải lại với cùng hóa đơn.',
        { plan, code: response.status === 403 ? 'UPLOAD_EXPIRED' : 'UPLOAD_HTTP_ERROR' },
      );
    }
    onProgress?.(100);
    return { receipt_id: plan.receipt_id };
  }

  return {
    async listHouseholds({ signal } = {}) {
      const data = await request('/households', { signal });
      if (!Array.isArray(data?.households)) throw invalidResponse();
      return data.households.map(household);
    },
    async createHousehold(name, { signal } = {}) {
      const data = await request('/households', {
        method: 'POST', body: { name: textInput(name, 'Tên hộ gia đình', 100) }, signal,
      });
      return household(data?.household);
    },
    async joinHousehold(inviteCode, { signal } = {}) {
      const data = await request('/households/join', {
        method: 'POST', body: { invite_code: textInput(inviteCode, 'Mã mời', 128) }, signal,
      });
      return household(data?.household);
    },
    requestReceiptUpload,
    resumeReceiptUpload,
    async uploadReceipt({ householdId, file, onProgress, signal }) {
      const plan = await requestReceiptUpload(householdId, file, { signal });
      return resumeReceiptUpload({ plan, file, onProgress, signal });
    },
  };
}

export const api = createApiClient({
  baseUrl: config.apiBaseUrl,
  getAccessToken: () => authService.getAccessToken(),
});
