import assert from "node:assert/strict";
import test from "node:test";
import { ApiError, readApiResponse } from "../src/apiResponse.js";

test("empty Vite proxy 502 explains the backend connection failure", async () => {
  await assert.rejects(readApiResponse(new Response("", { status: 502 })), (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 502);
    assert.equal(error.code, "HTTP_502");
    assert.match(error.message, /Không kết nối được máy chủ API/);
    assert.match(error.message, /backend/);
    return true;
  });
});

test("API errors preserve status/code/message and request ID for debugging", async () => {
  await assert.rejects(readApiResponse(Response.json({ error: {
    code: "VALIDATION", message: "Ngày giao dịch không hợp lệ", request_id: "review-request",
  } }, { status: 422 })), {
    status: 422, code: "VALIDATION", message: "Ngày giao dịch không hợp lệ", requestId: "review-request",
  });
});

test("successful HTML is rejected instead of treating a write as successful", async () => {
  await assert.rejects(readApiResponse(new Response("<html>Frontend fallback</html>", { status: 200 })), {
    status: 502, code: "INVALID_RESPONSE",
  });
  assert.equal(await readApiResponse(new Response(null, { status: 204 })), null);
  assert.deepEqual(await readApiResponse(Response.json({ transaction: { id: 5 } })), { transaction: { id: 5 } });
});
