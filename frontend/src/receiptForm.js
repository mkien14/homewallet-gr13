import { parseVnd, todayIso } from "./format.js";

export function receiptDateLimit(now = new Date()) {
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  return todayIso(tomorrow);
}

export function createReceiptForm(draft, keyFactory = () => crypto.randomUUID()) {
  return {
    merchant: draft.merchant ?? "",
    occurred_on: draft.occurred_on ?? "",
    total_amount: String(draft.total_amount ?? ""),
    category_id: String(draft.category_id ?? ""),
    items: (draft.items ?? []).map((item) => ({
      ...item,
      key: keyFactory(),
      description: item.description ?? "",
      quantity: String(item.quantity ?? ""),
      amount: String(item.amount ?? ""),
      category_id: String(item.category_id ?? ""),
    })),
  };
}

function nullableText(value, label) {
  const text = String(value ?? "").trim();
  if (text.length > 255) throw new Error(`${label} tối đa 255 ký tự.`);
  return text || null;
}

function categoryValue(value, categories) {
  if (value === "" || value == null) return null;
  const id = Number(value);
  if (!Number.isSafeInteger(id) || id <= 0 || !categories.some((category) => Number(category.id) === id)) {
    throw new Error("Danh mục không còn khả dụng. Hãy chọn lại hoặc chọn Chưa phân loại.");
  }
  return id;
}

export function receiptConfirmationBody(form, categories, { now = new Date() } = {}) {
  const date = new Date(`${form.occurred_on}T12:00:00Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(form.occurred_on)
    || Number(form.occurred_on.slice(0, 4)) < 1
    || !Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== form.occurred_on
    || form.occurred_on > receiptDateLimit(now)) {
    throw new Error("Ngày hóa đơn phải hợp lệ và không được quá một ngày trong tương lai.");
  }
  const total = parseVnd(form.total_amount);
  if (total === null || total <= 0) throw new Error("Tổng tiền phải là số nguyên đồng lớn hơn 0.");
  const items = form.items.map((item, index) => {
    const amount = parseVnd(item.amount);
    if (amount === null || amount <= 0) throw new Error(`Thành tiền dòng ${index + 1} phải là số nguyên đồng lớn hơn 0.`);
    const quantity = item.quantity === "" || item.quantity == null ? null : Number(item.quantity);
    if (quantity !== null && (!Number.isFinite(quantity) || quantity <= 0 || quantity > 9_999_999.999)) {
      throw new Error(`Số lượng dòng ${index + 1} phải lớn hơn 0 và không quá 9.999.999,999.`);
    }
    const result = {
      description: nullableText(item.description, "Mô tả mặt hàng"),
      quantity,
      amount,
      category_id: categoryValue(item.category_id, categories),
    };
    if (Object.hasOwn(item, "unit_price")) {
      const unitPrice = item.unit_price == null ? null : parseVnd(item.unit_price);
      if (item.unit_price != null && unitPrice === null) throw new Error(`Đơn giá dòng ${index + 1} phải là số nguyên đồng không âm.`);
      result.unit_price = unitPrice;
    }
    return result;
  });
  return {
    occurred_on: form.occurred_on,
    total_amount: total,
    merchant: nullableText(form.merchant, "Tên cửa hàng"),
    category_id: categoryValue(form.category_id, categories),
    items,
  };
}
