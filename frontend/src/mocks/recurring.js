function fail(status, code, message) {
  throw Object.assign(new Error(message), { status, code });
}

function nonnegative(value, label) {
  if (!Number.isSafeInteger(value) || value < 0) fail(422, "VALIDATION", `${label} phải là số nguyên đồng không âm.`);
  return value;
}

function objectBody(body, fields) {
  if (!body || typeof body !== "object" || Array.isArray(body) || Object.keys(body).some((key) => !fields.includes(key))) {
    fail(422, "VALIDATION", "Dữ liệu thiếu hoặc có trường không được hỗ trợ.");
  }
}

function category(state, id) {
  if (!Number.isSafeInteger(id) || id <= 0 || !state.categories.some((item) => item.id === id)) fail(422, "VALIDATION", "Danh mục không hợp lệ.");
}

function billBody(state, body, previous) {
  const fields = ["name", "category_id", "due_day", "expected_amount", "remind_days_before", "active"];
  objectBody(body, fields);
  if (previous && !Object.keys(body).length) fail(422, "VALIDATION", "Chưa có thay đổi để lưu.");
  const bill = { category_id: null, expected_amount: null, remind_days_before: 3, active: true, ...previous, ...body };
  if (typeof bill.name !== "string" || !bill.name.trim() || [...bill.name.trim()].length > 100) fail(422, "VALIDATION", "Tên hóa đơn cần có từ 1 đến 100 ký tự.");
  if (bill.category_id !== null) category(state, bill.category_id);
  if (!Number.isInteger(bill.due_day) || bill.due_day < 1 || bill.due_day > 31) fail(422, "VALIDATION", "Ngày đến hạn phải từ 1 đến 31.");
  if (bill.expected_amount !== null) nonnegative(bill.expected_amount, "Số tiền dự kiến");
  if (!Number.isInteger(bill.remind_days_before) || bill.remind_days_before < 0 || bill.remind_days_before > 30) fail(422, "VALIDATION", "Số ngày nhắc trước phải từ 0 đến 30.");
  if (typeof bill.active !== "boolean") fail(422, "VALIDATION", "Trạng thái hoạt động không hợp lệ.");
  return { ...bill, name: bill.name.trim() };
}

export function dispatchRecurringMock(state, route, verb, body) {
  const detail = /^\/api\/recurring-bills\/(\d+)$/.exec(route);
  if (!detail && route !== "/api/recurring-bills") return { handled: false };
  if (!state.household) fail(404, "NOT_FOUND", "Bạn cần tham gia một hộ gia đình.");
  if (verb !== "GET" && state.household.role !== "owner") fail(403, "FORBIDDEN", "Chỉ Chủ hộ được chỉnh sửa hóa đơn định kỳ.");
  state.recurringByHousehold ??= {};
  const key = String(state.household.id);
  if (!Object.hasOwn(state.recurringByHousehold, key)) {
    state.recurringByHousehold[key] = state.household.id === 1 ? [
      { id: 1, name: "Tiền điện nước", category_id: 4, due_day: 15, expected_amount: 850000, remind_days_before: 3, active: true },
      { id: 2, name: "Vé xe tháng", category_id: 2, due_day: 1, expected_amount: 200000, remind_days_before: 2, active: false },
    ] : [];
  }
  const bills = state.recurringByHousehold[key];
  if (route === "/api/recurring-bills" && verb === "GET") return { handled: true, result: { items: [...bills].sort((a, b) => a.due_day - b.due_day || a.id - b.id) } };
  if (route === "/api/recurring-bills" && verb === "POST") {
    const saved = { ...billBody(state, body), id: Math.max(0, ...bills.map((item) => item.id)) + 1 };
    bills.push(saved);
    return { handled: true, result: { bill: saved } };
  }
  if (detail && (verb === "PATCH" || verb === "DELETE")) {
    const index = bills.findIndex((item) => item.id === Number(detail[1]));
    if (index < 0) fail(404, "NOT_FOUND", "Không tìm thấy hóa đơn định kỳ trong hộ của bạn.");
    if (verb === "DELETE") { bills.splice(index, 1); return { handled: true, result: null }; }
    bills[index] = billBody(state, body, bills[index]);
    return { handled: true, result: { bill: bills[index] } };
  }
  fail(405, "METHOD_NOT_ALLOWED", "Thao tác không được hỗ trợ.");
}
