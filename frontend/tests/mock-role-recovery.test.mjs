import test from "node:test";
import assert from "node:assert/strict";

test("a saved legacy member session restores the demo owner without losing other data", async () => {
  const originalStorage = globalThis.localStorage;
  const entries = new Map();
  globalThis.localStorage = {
    getItem: (key) => entries.get(key) ?? null,
    setItem: (key, value) => entries.set(key, String(value)),
  };
  try {
    const mock = await import("../src/mocks/index.js?legacy-role-setup");
    mock.resetMockData();
    const key = "homewallet.week2.mock.v1";
    const stored = JSON.parse(entries.get(key));
    stored.household.role = "member";
    stored.members[0].role = "member";
    stored.transactions[0].note = "keep saved demo data";
    entries.set(key, JSON.stringify(stored));

    const recovered = await import("../src/mocks/index.js?legacy-role-recovery");
    const { user, household } = await recovered.mockApi("/api/me");
    assert.equal(user.display_name, "Chi");
    assert.equal(household.role, "member");
    const { members } = await recovered.mockApi("/api/households/1/members");
    assert.deepEqual(members.map(({ display_name, role }) => [display_name, role]), [["Thức", "owner"], ["Chi", "member"]]);
    const persisted = JSON.parse(entries.get(key));
    assert.equal(persisted.transactions[0].note, "keep saved demo data");
  } finally {
    if (originalStorage === undefined) delete globalThis.localStorage;
    else globalThis.localStorage = originalStorage;
  }
});

test("saved dissolved demo can switch accounts without restoring the household or losing history", async () => {
  const originalStorage = globalThis.localStorage;
  const entries = new Map();
  globalThis.localStorage = {
    getItem: (key) => entries.get(key) ?? null,
    setItem: (key, value) => entries.set(key, String(value)),
  };
  try {
    const previous = await import("../src/mocks/index.js?dissolved-demo-setup");
    previous.resetMockData();
    await previous.mockApi("/api/households/1/delete", { method: "POST", body: { confirm: true, household_id: 1 } });
    const recovered = await import("../src/mocks/index.js?dissolved-demo-recovery");
    recovered.setMockRole("member");
    const afterReload = await import("../src/mocks/index.js?dissolved-demo-after-reload");
    const { user, household } = await afterReload.mockApi("/api/me");
    assert.equal(user.display_name, "Chi");
    assert.equal(household, null);
    const { items } = await afterReload.mockApi("/api/me/household-history");
    assert.equal(items.length, 1);
    assert.equal(items[0].role, "member");
    assert.equal(items[0].end_reason, "dissolved");
    await assert.rejects(afterReload.mockApi("/api/households/1/members"), { status: 404 });
  } finally {
    if (originalStorage === undefined) delete globalThis.localStorage;
    else globalThis.localStorage = originalStorage;
  }
});
