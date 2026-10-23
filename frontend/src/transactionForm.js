import { parseVnd, todayIso } from "./format.js";

export function transactionDateLimit(now = new Date()) {
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  return todayIso(tomorrow);
}

function validDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value) || Number(value.slice(0, 4)) < 1) return false;
  const parsed = new Date(`${value}T12:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

export function buildTransactionBody({ occurredOn, amount, categoryId, note }, categories, now = new Date()) {
  const totalAmount = parseVnd(amount);
  if (!Number.isSafeInteger(totalAmount) || totalAmount <= 0) {
    throw new Error("Nhập số tiền là số nguyên đồng lớn hơn 0.");
  }
  if (!validDate(occurredOn) || occurredOn > transactionDateLimit(now)) {
    throw new Error("Ngày chi tiêu phải hợp lệ và không quá ngày mai.");
  }
  const category = categoryId === "" || categoryId == null ? null : Number(categoryId);
  if (category !== null && (!Number.isSafeInteger(category) || category <= 0 || !categories.some((item) => String(item.id) === String(categoryId)))) {
    throw new Error("Danh mục không hợp lệ. Hãy chọn lại danh mục hoặc để Chưa phân loại.");
  }
  if (note != null && (typeof note !== "string" || note.length > 500)) {
    throw new Error("Ghi chú tối đa 500 ký tự.");
  }
  return {
    occurred_on: occurredOn,
    total_amount: totalAmount,
    category_id: category,
    note: note?.trim() || null,
  };
}
