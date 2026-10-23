import test, { beforeEach, mock } from "node:test";
import assert from "node:assert/strict";
import { completeMockUpload, mockApi, resetMockData } from "../src/mocks/index.js";
import { todayIso } from "../src/format.js";

beforeEach(() => resetMockData());

test("dashboard mock requires a valid period just like the new Flask endpoint", async () => {
  for (const path of ["/api/dashboard", "/api/dashboard?period=2026-13", "/api/dashboard?period=0000-01", "/api/dashboard?period=9999-12"]) {
    await assert.rejects(mockApi(path), { status: 422 });
  }
  const empty = await mockApi("/api/dashboard?period=2000-01");
  assert.equal(empty.total, 0);
  assert.deepEqual(empty.by_category, []);
  assert.deepEqual(empty.by_member, []);
  assert.deepEqual(empty.by_week, []);
});

const dashboardPath = () => `/api/dashboard?period=${todayIso().slice(0, 7)}`;
const manual = () => ({ occurred_on: todayIso(), total_amount: 42000, category_id: 1, note: "Bữa trưa" });
const createManual = (body, key = "test-key") => mockApi("/api/transactions", { method: "POST", headers: { "Idempotency-Key": key }, body });

test("all receipt states and correctly shaped household/category fixtures are available", async () => {
  const { items } = await mockApi("/api/receipts");
  assert.deepEqual(new Set(items.map((item) => item.status)), new Set(["UPLOADING", "UPLOADED", "PROCESSING", "DRAFT_READY", "NEEDS_REVIEW", "FAILED", "CONFIRMED"]));
  const { user, household } = await mockApi("/api/me");
  assert.equal(user.id, 1);
  assert.equal(household.id, 1);
  const { members } = await mockApi("/api/households/1/members");
  assert.equal(members.length, 2);
  assert.ok((await mockApi("/api/categories")).categories.length > 0);
});

test("dashboard excludes OCR drafts and member filters follow member_id", async () => {
  const dashboard = await mockApi(dashboardPath());
  assert.equal(dashboard.total, 227000);
  assert.equal(dashboard.by_category.reduce((sum, item) => sum + item.amount, 0), dashboard.total);
  assert.equal(dashboard.by_member.reduce((sum, item) => sum + item.amount, 0), dashboard.total);
  assert.equal(dashboard.by_week.reduce((sum, item) => sum + item.amount, 0), dashboard.total);
  const filtered = await mockApi(`${dashboardPath()}&member_id=2`);
  assert.equal(filtered.total, dashboard.total);
  const { items } = await mockApi("/api/transactions?member_id=2");
  assert.ok(items.every((transaction) => transaction.member_id === 2));
});

test("manual transaction repeated with the same key creates one confirmed record", async () => {
  const first = await createManual(manual());
  const second = await createManual(manual());
  assert.deepEqual(second, first);
  assert.equal(first.transaction.status, "CONFIRMED");
  assert.equal(first.transaction.member_id, 1);
  const { items } = await mockApi("/api/transactions");
  assert.equal(items.filter((item) => item.id === first.transaction.id).length, 1);
  assert.equal((await mockApi(dashboardPath())).total, 269000);
});

test("idempotency replays the original transaction even if valid input changes, as the real API does", async () => {
  const original = await createManual(manual());
  assert.deepEqual(await createManual({ ...manual(), total_amount: 10000 }), original);
  assert.equal((await mockApi(dashboardPath())).total, 269000);
  await assert.rejects(mockApi("/api/transactions", { method: "POST", body: manual() }), { status: 422 });
  await assert.rejects(createManual(manual(), "x".repeat(65)), { status: 422 });
});

test("keyset pagination excludes new inserts when continuing an older page", async () => {
  const first = await mockApi("/api/receipts?limit=2");
  assert.equal(first.next_cursor, String(first.items.at(-1).id));
  await mockApi("/api/receipts", { method: "POST", body: { content_type: "image/jpeg", size: 100 } });
  const second = await mockApi(`/api/receipts?limit=2&cursor=${first.next_cursor}`);
  assert.ok(second.items.every((item) => item.id < Number(first.next_cursor)));
  assert.equal(new Set([...first.items, ...second.items].map((item) => item.id)).size, 4);
});

test("uncategorized manual expenses and optional receipt fields match the real API", async () => {
  const result = await createManual({ ...manual(), category_id: null, note: null });
  assert.equal(result.transaction.category_id, null);
  const detail = await mockApi("/api/receipts/4");
  const confirmed = await mockApi("/api/receipts/4/confirm", { method: "POST", body: {
    occurred_on: todayIso(), total_amount: 147000, merchant: null, category_id: null, items: [],
  } });
  assert.equal(confirmed.transaction.id, detail.draft.transaction_id);
  assert.equal(confirmed.transaction.category_id, null);
  assert.deepEqual(confirmed.transaction.items, []);
  const future = new Date();
  future.setDate(future.getDate() + 2);
  await assert.rejects(createManual({ ...manual(), occurred_on: todayIso(future) }, "future-key"), { status: 422 });
});

test("invalid amounts, dates and categories leave dashboard unchanged", async () => {
  for (const body of [
    { ...manual(), total_amount: -10 },
    { ...manual(), total_amount: 1.5 },
    { ...manual(), occurred_on: "2026-02-30" },
    { ...manual(), category_id: 999 },
  ]) await assert.rejects(createManual(body), { status: 422, code: "VALIDATION" });
  assert.equal((await mockApi(dashboardPath())).total, 227000);
});

test("confirming an edited receipt updates its existing draft exactly once", async () => {
  const detail = await mockApi("/api/receipts/5");
  const body = { ...detail.draft, total_amount: 147000, merchant: "Cửa hàng đã sửa" };
  const result = await mockApi("/api/receipts/5/confirm", { method: "POST", body });
  assert.equal(result.transaction.id, detail.draft.transaction_id);
  assert.equal(result.transaction.status, "CONFIRMED");
  assert.equal(result.transaction.merchant, "Cửa hàng đã sửa");
  assert.equal((await mockApi("/api/receipts/5")).status, "CONFIRMED");
  assert.equal((await mockApi(dashboardPath())).total, 374000);
  await assert.rejects(mockApi("/api/receipts/5/confirm", { method: "POST", body }), { status: 409 });
  assert.equal((await mockApi(dashboardPath())).total, 374000);
});

test("receipt confirmation rejects invalid lines and non-ready receipts", async () => {
  const { draft } = await mockApi("/api/receipts/4");
  await assert.rejects(mockApi("/api/receipts/4/confirm", { method: "POST", body: { ...draft, items: [{ ...draft.items[0], quantity: -1 }] } }), { status: 422 });
  await assert.rejects(mockApi("/api/receipts/6/confirm", { method: "POST", body: draft }), { status: 409 });
  assert.equal((await mockApi(dashboardPath())).total, 227000);
});

test("receipt pagination returns each item once and filter preserves status", async () => {
  let cursor = "";
  const ids = [];
  do {
    const page = await mockApi(`/api/receipts?limit=2&cursor=${cursor}`);
    ids.push(...page.items.map((item) => item.id));
    cursor = page.next_cursor;
  } while (cursor);
  assert.equal(ids.length, 7);
  assert.equal(new Set(ids).size, 7);
  assert.equal((await mockApi("/api/receipts?status=FAILED")).items[0].status, "FAILED");
  await assert.rejects(mockApi("/api/receipts?cursor=bad"), { status: 422 });
});

test("mock uploads progress to a single OCR draft without touching S3", async () => {
  let now = Date.now();
  const timer = mock.method(Date, "now", () => now);
  try {
    const { receipt, upload } = await mockApi("/api/receipts", { method: "POST", body: { content_type: "image/jpeg", size: 100 } });
    assert.ok(upload.url.startsWith("mock://"));
    await completeMockUpload(receipt.id, new Blob(["demo"], { type: "image/jpeg" }));
    assert.equal((await mockApi(`/api/receipts/${receipt.id}`)).status, "UPLOADED");
    now += 3100;
    assert.equal((await mockApi(`/api/receipts/${receipt.id}`)).status, "PROCESSING");
    now += 3100;
    const detail = await mockApi(`/api/receipts/${receipt.id}`);
    assert.equal(detail.status, "DRAFT_READY");
    assert.ok(detail.image_url.startsWith("blob:"));
    const repeated = await mockApi(`/api/receipts/${receipt.id}`);
    assert.equal(repeated.draft.transaction_id, detail.draft.transaction_id);
    const { items } = await mockApi("/api/transactions");
    assert.equal(items.filter((transaction) => transaction.receipt_id === receipt.id).length, 1);
  } finally {
    timer.mock.restore();
  }
});

test("API responses are copied and cannot corrupt stored fixtures", async () => {
  const response = await mockApi("/api/categories");
  response.categories.length = 0;
  assert.equal((await mockApi("/api/categories")).categories.length, 4);
  await assert.rejects(mockApi("/api/unknown"), { status: 404 });
});
