import { getToken, login } from "./auth/auth";

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export async function api(path, { method = "GET", body } = {}) {
  const token = getToken();
  if (!token) {
    await login(); 
    throw new ApiError(401, "UNAUTHENTICATED", "Cần đăng nhập");
  }

  const res = await fetch(path, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);

  if (!res.ok) {
    const err = data?.error;
    if (res.status === 401 && err?.code === "TOKEN_EXPIRED") {
      sessionStorage.removeItem("hw.token");
      await login();
    }
    throw new ApiError(res.status, err?.code, err?.message || "Có lỗi xảy ra");
  }
  return data;
}