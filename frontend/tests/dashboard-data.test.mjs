import assert from "node:assert/strict";
import test from "node:test";
import { aggregateTransactions, loadAllTransactions, loadDashboardData } from "../src/dashboardData.js";

test("member summary excludes drafts and groups Monday weeks across month boundaries", () => {
  const result = aggregateTransactions([
    { id: 1, status: "CONFIRMED", occurred_on: "2026-10-01", total_amount: 120000, member_id: 1, category_id: 2 },
    { id: 2, status: "DRAFT", occurred_on: "2026-10-02", total_amount: 999999, member_id: 1, category_id: 2 },
    { id: 3, status: "CONFIRMED", occurred_on: "2026-10-05", total_amount: 30000, member_id: 1, category_id: null },
  ], "2026-10", [{ id: 2, name: "Ăn uống" }], [{ id: 1, display_name: "Thức" }]);
  assert.equal(result.total, 150000);
  assert.deepEqual(result.by_member, [{ user_id: 1, display_name: "Thức", amount: 150000 }]);
  assert.deepEqual(result.by_week, [{ week_start: "2026-09-28", amount: 120000 }, { week_start: "2026-10-05", amount: 30000 }]);
  assert.equal(result.by_category[1].name, "Chưa phân loại");
});

test("transactions fetch follows every cursor so member totals never use only page one", async () => {
  const calls = [];
  const rows = await loadAllTransactions(async (path) => {
    calls.push(path);
    const cursor = new URL(path, "http://localhost").searchParams.get("cursor");
    return cursor ? { items: [{ id: 2, total_amount: 2 }], next_cursor: null }
      : { items: [{ id: 1, total_amount: 1 }], next_cursor: "next page" };
  }, { period: "2026-10", member_id: "1" });
  assert.deepEqual(rows.map((row) => row.id), [1, 2]);
  assert.equal(calls.length, 2);
  assert.equal(new URL(calls[1], "http://localhost").searchParams.get("cursor"), "next page");
});

test("repeated cursor fails rather than displaying an incomplete total", async () => {
  await assert.rejects(loadAllTransactions(async () => ({ items: [{ id: 1 }], next_cursor: "same" }), { period: "2026-10" }), /con trỏ phân trang trùng/);
});

test("cancelled requests stop pagination", async () => {
  const controller = new AbortController();
  await assert.rejects(loadAllTransactions(async () => {
    controller.abort();
    return { items: [{ id: 1 }], next_cursor: "next" };
  }, { period: "2026-10" }, controller.signal), { name: "AbortError" });
});

function dashboardApi(summaryResult, overrides = {}) {
  const calls = [];
  const api = async (path) => {
    calls.push(path);
    if (path === "/api/me") return { user: { id: 1 }, household: { id: 1 } };
    if (path === "/api/categories") return { categories: [{ id: 2, name: "Đi lại" }] };
    if (path === "/api/households/1/members") return { members: [{ id: 1, display_name: "Thức" }] };
    if (path.startsWith("/api/dashboard?")) {
      if (summaryResult instanceof Error) throw summaryResult;
      return summaryResult;
    }
    if (path.startsWith("/api/transactions?")) {
      if (overrides.transactionsError) throw overrides.transactionsError;
      const query = new URL(path, "http://localhost").searchParams;
      return query.get("cursor") ? { items: [{ id: 1, status: "CONFIRMED", occurred_on: "2026-10-02", member_id: 1, category_id: null, total_amount: 20000 }], next_cursor: null }
        : { items: [{ id: 3, status: "CONFIRMED", occurred_on: "2026-10-01", member_id: 1, category_id: 2, total_amount: 10000 }, { id: 2, status: "DRAFT", occurred_on: "2026-10-01", total_amount: 999999 }], next_cursor: "2" };
    }
    throw new Error(`Unexpected request ${path}`);
  };
  return { api, calls };
}

test("dashboard 404 is propagated now the route exists in main", async () => {
  const { api } = dashboardApi(Object.assign(new Error("Not found"), { status: 404 }));
  await assert.rejects(loadDashboardData(api, { period: "2026-10" }), { status: 404 });
});

test("an available dashboard API remains authoritative", async () => {
  const summary = { period: "2026-10", total: 30000, by_category: [], by_member: [], by_week: [] };
  const { api } = dashboardApi(summary);
  assert.deepEqual((await loadDashboardData(api, { period: "2026-10" })).summary, summary);
});

test("server/auth failures do not become a misleading zero or fake dashboard", async () => {
  for (const status of [401, 403, 500, 502, 503]) {
    const error = Object.assign(new Error(`HTTP ${status}`), { status });
    const { api } = dashboardApi(error);
    await assert.rejects(loadDashboardData(api, { period: "2026-10" }), { status });
  }
  const { api } = dashboardApi({ period: "2026-10", total: 0, by_category: [], by_member: [], by_week: [] }, {
    transactionsError: Object.assign(new Error("Connection lost"), { status: 502 }),
  });
  await assert.rejects(loadDashboardData(api, { period: "2026-10" }), { status: 502 });
});

test("member summary avoids unsupported member filters on the dashboard endpoint", async () => {
  const { api, calls } = dashboardApi(new Error("Dashboard should not be called"));
  const result = await loadDashboardData(api, { period: "2026-10", memberId: "1" });
  assert.equal(result.summary.total, 30000);
  assert.ok(!calls.some((path) => path.startsWith("/api/dashboard")));
  assert.equal(calls.filter((path) => path.startsWith("/api/transactions?")).length, 2);
});

test("nullable SQL category/member names are readable in charts and legends", async () => {
  const { api } = dashboardApi({ period: "2026-10", total: 30000,
    by_category: [{ category_id: null, name: null, amount: 30000 }],
    by_member: [{ user_id: 1, display_name: null, amount: 30000 }], by_week: [],
  });
  const result = await loadDashboardData(api, { period: "2026-10" });
  assert.equal(result.summary.by_category[0].name, "Chưa phân loại");
  assert.equal(result.summary.by_member[0].display_name, "Thành viên");
});

test("no household does not request protected financial endpoints", async () => {
  const calls = [];
  const result = await loadDashboardData(async (path) => {
    calls.push(path);
    return { user: { id: 1 }, household: null };
  }, { period: "2026-10" });
  assert.equal(result.household, null);
  assert.deepEqual(calls, ["/api/me"]);
});
