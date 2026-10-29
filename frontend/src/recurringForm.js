import { parseVnd } from "./format.js";

export function recurringFields(bill = {}) {
  return {
    name: bill.name ?? "",
    categoryId: bill.category_id == null ? "" : String(bill.category_id),
    dueDay: bill.due_day == null ? "" : String(bill.due_day),
    amount: bill.expected_amount == null ? "" : String(bill.expected_amount),
    remindDays: String(bill.remind_days_before ?? 3),
    active: bill.active ?? true,
  };
}

function wholeNumber(value, min, max, label) {
  if (!/^\d+$/.test(String(value))) throw new Error(`${label} phải là số nguyên từ ${min} đến ${max}.`);
  const number = Number(value);
  if (!Number.isSafeInteger(number) || number < min || number > max) {
    throw new Error(`${label} phải là số nguyên từ ${min} đến ${max}.`);
  }
  return number;
}

export function buildRecurringBody(fields, categories) {
  if (typeof fields.name !== "string" || !fields.name.trim() || fields.name.trim().length > 100) {
    throw new Error("Tên hóa đơn cần từ 1 đến 100 ký tự.");
  }
  const categoryId = fields.categoryId == null || fields.categoryId === "" ? null : Number(fields.categoryId);
  if (categoryId !== null && (!/^\d+$/.test(String(fields.categoryId)) || !Number.isSafeInteger(categoryId) || categoryId <= 0 ||
      !categories.some((category) => category.id === categoryId))) throw new Error("Hãy chọn một danh mục hợp lệ hoặc để Chưa phân loại.");
  const emptyAmount = fields.amount == null || String(fields.amount).trim() === "";
  const amount = emptyAmount ? null : parseVnd(fields.amount);
  if (!emptyAmount && (amount === null || amount < 0)) throw new Error("Số tiền dự kiến phải là số nguyên đồng không âm hoặc để trống.");
  if (typeof fields.active !== "boolean") throw new Error("Trạng thái hóa đơn không hợp lệ.");
  return {
    name: fields.name.trim(),
    category_id: categoryId,
    due_day: wholeNumber(fields.dueDay, 1, 31, "Ngày đến hạn"),
    expected_amount: amount,
    remind_days_before: wholeNumber(fields.remindDays, 0, 30, "Số ngày nhắc trước"),
    active: fields.active,
  };
}

export function validRecurringBill(bill, categories) {
  if (!bill || !Number.isSafeInteger(bill.id) || bill.id <= 0) return false;
  try {
    buildRecurringBody(recurringFields(bill), categories);
    return typeof bill.active === "boolean" && (bill.category_id === null || Number.isSafeInteger(bill.category_id)) &&
      (bill.expected_amount === null || Number.isSafeInteger(bill.expected_amount)) &&
      Number.isSafeInteger(bill.due_day) && Number.isSafeInteger(bill.remind_days_before);
  } catch {
    return false;
  }
}

export function recurringError(error) {
  let message = error.message || "Chưa thực hiện được yêu cầu. Hãy thử lại.";
  if ((error.status === 404 && error.code === "HTTP_404") || error.status === 501) {
    message = "Máy chủ đang kết nối chưa phục vụ API hóa đơn định kỳ. Hãy kiểm tra địa chỉ API và khởi động lại backend sau khi cập nhật mã.";
  } else if (error.status === 403) {
    message = "Bạn không có quyền thay đổi hóa đơn định kỳ. Chỉ Chủ hộ được thêm, sửa hoặc tạm dừng.";
  } else if (error.status === 409) {
    message = "Dữ liệu có xung đột. Nội dung bạn nhập vẫn được giữ lại; hãy kiểm tra danh sách trước khi lưu lại.";
  }
  return { message, requestId: error.requestId, status: error.status };
}

export function createNeedsReconciliation(error) {
  return !error.status || error.status >= 500;
}

export function matchingRecurringBills(items, body, previousIds) {
  const fields = ["name", "category_id", "due_day", "expected_amount", "remind_days_before", "active"];
  return items.filter((bill) => !previousIds.includes(bill.id) && fields.every((field) => bill[field] === body[field]));
}
