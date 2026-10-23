export class ApiError extends Error {
  constructor(status, code, message, requestId) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

function fallbackMessage(status) {
  if (status === 502 || status === 503) return `Không kết nối được máy chủ API (HTTP ${status}). Hãy kiểm tra backend đang chạy và thử lại.`;
  if (status === 504) return "Máy chủ API phản hồi quá chậm (HTTP 504). Hãy thử lại sau.";
  if (status === 401) return "Phiên đăng nhập không hợp lệ hoặc đã hết hạn. Hãy đăng nhập lại.";
  if (status === 403) return "Bạn không có quyền thực hiện thao tác này.";
  if (status === 404) return "Không tìm thấy dữ liệu hoặc địa chỉ API được yêu cầu.";
  if (status >= 500) return `Máy chủ API gặp lỗi (HTTP ${status}). Hãy thử lại sau.`;
  return `Yêu cầu không thực hiện được (HTTP ${status}). Hãy kiểm tra dữ liệu và thử lại.`;
}

export async function readApiResponse(response, { signal } = {}) {
  if (response.status === 204) return null;
  const data = await response.json().catch((error) => {
    if (signal?.aborted) throw error;
    return null;
  });
  const requestId = data?.error?.request_id || response.headers.get("X-Request-Id");
  if (!response.ok) {
    const error = data?.error;
    throw new ApiError(response.status, error?.code || `HTTP_${response.status}`,
      error?.message || fallbackMessage(response.status), requestId);
  }
  if (data === null || typeof data !== "object") {
    throw new ApiError(502, "INVALID_RESPONSE", "API trả về dữ liệu không hợp lệ. Hãy kiểm tra địa chỉ backend và thử lại.", requestId);
  }
  return data;
}
