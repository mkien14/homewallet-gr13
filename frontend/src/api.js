import { getToken, login } from "./auth/auth";
import { USE_MOCK } from "./mode";
import { ApiError, readApiResponse } from "./apiResponse";

export { ApiError } from "./apiResponse";

export async function api(path, { method = "GET", body, headers, signal } = {}) {
  signal?.throwIfAborted();
  if (USE_MOCK) {
    const { mockApi } = await import("./mocks/index.js");
    signal?.throwIfAborted();
    const result = await mockApi(path, { method, body, headers });
    signal?.throwIfAborted();
    return result;
  }
  const token = getToken();
  if (!token) {
    await login(); 
    throw new ApiError(401, "UNAUTHENTICATED", "Cần đăng nhập");
  }

  const requestHeaders = new Headers(headers);
  requestHeaders.set("Authorization", `Bearer ${token}`);
  if (body !== undefined) requestHeaders.set("Content-Type", "application/json");
  try {
    let response;
    try {
      response = await fetch(path, {
        method,
        headers: requestHeaders,
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal,
      });
    } catch (error) {
      if (signal?.aborted) throw error;
      throw new ApiError(0, "NETWORK_ERROR", "Không kết nối được máy chủ API. Hãy kiểm tra kết nối và backend đang chạy.");
    }
    return await readApiResponse(response, { signal });
  } catch (error) {
    if (error.status === 401 && error.code === "TOKEN_EXPIRED") {
      sessionStorage.removeItem("hw.token");
      await login();
    }
    error.path = path;
    throw error;
  }
}
