import test from "node:test";
import assert from "node:assert/strict";
import { budgetToForm, buildBudgetBody, checkBudget } from "../src/budgetForm.js";

const categories = [{ id: 1, name: "Ăn uống" }, { id: 2, name: "Đi lại" }];
const budget = { period: "2026-10", income_estimate: 1000000, savings_goal: 200000, source: "MANUAL", status: "ACTIVE", allocations: [{ category_id: 1, name: "Ăn uống", amount: 500000 }, { category_id: 2, name: "Đi lại", amount: 300000 }] };

test("budget form sends the exact real PUT contract without version, metadata or household_id", () => {
  const form = budgetToForm(budget, categories);
  form.income = "1.000.000";
  const body = buildBudgetBody(form, categories);
  assert.deepEqual(body, { income_estimate: 1000000, savings_goal: 200000, allocations: [{ category_id: 1, amount: 500000 }, { category_id: 2, amount: 300000 }] });
  assert.deepEqual(Object.keys(body).sort(), ["allocations", "income_estimate", "savings_goal"]);
  assert.equal(checkBudget(budget, categories, "2026-10"), budget);
});

test("invalid or overallocated draft cannot be saved", () => {
  for (const amount of ["-1", "1.5", "", "9007199254740992"]) {
    const form = budgetToForm(budget, categories);
    form.allocations[1] = amount;
    assert.throws(() => buildBudgetBody(form, categories));
  }
  const form = budgetToForm(budget, categories);
  form.savings = "200001";
  assert.throws(() => buildBudgetBody(form, categories), /vượt thu nhập/);
  const emptyForm = budgetToForm(null, categories);
  emptyForm.income = "0";
  assert.deepEqual(buildBudgetBody(emptyForm, categories), { income_estimate: 0, savings_goal: 0, allocations: [{ category_id: 1, amount: 0 }, { category_id: 2, amount: 0 }] });
});

test("malformed server response is rejected instead of reporting save success", () => {
  for (const patch of [
    { period: "2026-11" }, { source: undefined }, { status: "DRAFT" }, { income_estimate: -1 },
    { allocations: [{ category_id: 99, name: "Lạ", amount: 0 }] },
    { allocations: [{ category_id: 1, name: "Ăn uống", amount: 1 }, { category_id: 1, name: "Ăn uống", amount: 2 }] },
    { allocations: [{ category_id: 1, name: "Ăn uống", amount: 1000000 }] },
    { allocations: [{ category_id: 1, amount: 10 }] },
  ]) assert.throws(() => checkBudget({ ...budget, ...patch }, categories, "2026-10"));
});

test("RULE and LLM suggestions are validated as drafts, not saved budgets", () => {
  for (const source of ["RULE", "LLM"]) {
    const suggestion = { ...budget, source, status: "DRAFT" };
    assert.equal(checkBudget(suggestion, categories, "2026-10", { suggestion: true }), suggestion);
    const form = budgetToForm(suggestion, categories);
    assert.equal(buildBudgetBody(form, categories).allocations[0].amount, 500000);
  }
  const empty = { ...budget, source: "RULE", status: "DRAFT", allocations: [] };
  assert.equal(checkBudget(empty, categories, "2026-10", { suggestion: true }), empty);
  assert.throws(() => checkBudget({ ...empty, source: "MANUAL" }, categories, "2026-10", { suggestion: true }));
  assert.throws(() => checkBudget({ ...empty, period: "2026-11" }, categories, "2026-10", { suggestion: true }));
  assert.throws(() => checkBudget(empty, categories, "2026-10"));
});

test("saved budgets containing only some categories fill missing categories with zero", () => {
  const sparse = { ...budget, allocations: budget.allocations.slice(0, 1) };
  checkBudget(sparse, categories, "2026-10");
  const form = budgetToForm(sparse, categories);
  assert.equal(form.allocations[2], "0");
  assert.deepEqual(buildBudgetBody(form, categories).allocations, [{ category_id: 1, amount: 500000 }, { category_id: 2, amount: 0 }]);
});
