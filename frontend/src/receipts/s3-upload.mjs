const MAX_UPLOAD_BYTES = 2 * 1024 * 1024;
const IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);

/** Errors contain safe UI text; S3 response bodies and signed fields are never exposed. */
export class PresignedPostUploadError extends Error {
  constructor(message, { code, status = 0 } = {}) {
    super(message);
    this.name = 'PresignedPostUploadError';
    this.code = code;
    this.status = status;
  }
}

function failure(code, message, status = 0) {
  return new PresignedPostUploadError(message, { code, status });
}

function aborted() {
  return failure('ABORTED', 'Đã hủy tải ảnh.');
}

/**
 * Accept HTTPS virtual-host S3 bucket endpoints only. Dotted bucket names are
 * excluded because the standard S3 wildcard certificate cannot cover them.
 * Path-style, website, accelerate, access-point and custom endpoints are outside
 * this contract. The object key belongs in the signed form fields, not the URL.
 */
export function validateS3UploadUrl(value) {
  const invalid = () => failure('INVALID_UPLOAD_URL', 'Địa chỉ tải ảnh S3 không hợp lệ.');
  // Check the original text as URL parsing normalizes explicit :443 ports,
  // backslashes and dot segments that this contract intentionally disallows.
  if (typeof value !== 'string' || !/^https:\/\/[a-z0-9.-]+\/?$/i.test(value)) throw invalid();
  let url;
  try { url = new URL(value); } catch { throw invalid(); }
  const match = url.hostname.match(/^([a-z0-9][a-z0-9-]{1,61}[a-z0-9])\.s3(?:[.-]([a-z]{2}(?:-gov)?-[a-z]+-[1-9][0-9]*))?\.amazonaws\.com(\.cn)?$/);
  const bucket = match?.[1];
  const region = match?.[2];
  if (!bucket || bucket.startsWith('xn--') || bucket.endsWith('-s3alias')
    || bucket.endsWith('--ol-s3') || bucket.endsWith('--x-s3') || bucket.endsWith('--table-s3')
    || Boolean(match?.[3]) !== Boolean(region?.startsWith('cn-'))
    || url.protocol !== 'https:' || url.username || url.password || url.port
    || url.pathname !== '/' || url.search || url.hash) {
    throw invalid();
  }
  return url.href;
}

function signedFieldEntries(fields) {
  const invalid = () => failure('INVALID_FIELDS', 'Thông tin ký tải ảnh S3 không hợp lệ.');
  if (!fields || typeof fields !== 'object'
    || ![Object.prototype, null].includes(Object.getPrototypeOf(fields))) throw invalid();
  const descriptors = Object.getOwnPropertyDescriptors(fields);
  const entries = [];
  for (const key of Reflect.ownKeys(descriptors)) {
    const descriptor = descriptors[key];
    if (typeof key !== 'string' || !key || key.toLowerCase() === 'file'
      || !descriptor.enumerable || !Object.hasOwn(descriptor, 'value')
      || typeof descriptor.value !== 'string') throw invalid();
    entries.push([key, descriptor.value]);
  }
  if (!Object.hasOwn(descriptors, 'key') || !descriptors.key.value) throw invalid();
  return entries;
}

function validateFile(file) {
  if (!(file instanceof Blob) || typeof file.name !== 'string' || !file.name.trim()
    || !IMAGE_TYPES.has(file.type) || !Number.isSafeInteger(file.size)
    || file.size <= 0 || file.size > MAX_UPLOAD_BYTES) {
    throw failure('INVALID_FILE', 'Ảnh tải lên phải là JPEG, PNG hoặc WebP, dung lượng từ 1 byte đến 2 MiB.');
  }
}

function notifyProgress(callback, value) {
  try {
    // These are lifecycle milestones, not measured network byte progress.
    const result = callback?.(value);
    if (result && typeof result.then === 'function') Promise.resolve(result).catch(() => {});
  } catch { /* UI callbacks must not change the upload result. */ }
}

/**
 * Upload an already prepared image using a presigned POST returned by the API.
 * Sends no application JWT, cookies, or manually constructed multipart headers.
 * Does not create a receipt, obtain signatures, or automatically retry a POST.
 */
export async function uploadToS3({ url, fields, file, signal, fetchImpl = globalThis.fetch, onProgress } = {}) {
  if (signal?.aborted) throw aborted();
  const uploadUrl = validateS3UploadUrl(url);
  const entries = signedFieldEntries(fields);
  validateFile(file);
  const form = new FormData();
  for (const [key, value] of entries) form.append(key, value);
  // S3 POST requires the file field to follow all signed fields.
  form.append('file', file, file.name);
  notifyProgress(onProgress, 0);
  if (signal?.aborted) throw aborted();
  let response;
  try {
    response = await fetchImpl(uploadUrl, {
      method: 'POST',
      body: form,
      credentials: 'omit',
      redirect: 'error',
      signal,
    });
  } catch (error) {
    if (signal?.aborted || error?.name === 'AbortError') throw aborted();
    throw failure('UPLOAD_NETWORK_ERROR', 'Chưa tải được ảnh lên S3. Vui lòng kiểm tra mạng hoặc cấu hình CORS.');
  }
  if (signal?.aborted) throw aborted();
  if (!response || typeof response.ok !== 'boolean' || !Number.isInteger(response.status)) {
    throw failure('UPLOAD_NETWORK_ERROR', 'Chưa nhận được phản hồi hợp lệ từ S3.');
  }
  if (!response.ok) {
    if (response.status === 403) {
      throw failure('UPLOAD_FORBIDDEN', 'S3 từ chối tải ảnh. Vui lòng kiểm tra chữ ký, chính sách tải lên và quyền truy cập.', 403);
    }
    throw failure('UPLOAD_HTTP_ERROR', 'S3 chưa nhận được ảnh. Vui lòng kiểm tra trạng thái trước khi thử lại.', response.status);
  }
  notifyProgress(onProgress, 100);
  return { status: response.status };
}
