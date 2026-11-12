import { dispatchRecurringMock } from "./recurring.js";
import { todayIso } from "../format.js";
import { dispatchFinance, setFinanceFailure } from "./finance.js";

export { setFinanceFailure } from "./finance.js";

const STORAGE_KEY = "homewallet.week2.mock.v1";
const DEMO_ACCOUNTS = {
  owner: { id: 1, email: "thuc.demo@example.com", display_name: "Thức" },
  member: { id: 2, email: "chi.demo@example.com", display_name: "Chi" },
};
const ACTIVE_STATUSES = ["UPLOADING", "UPLOADED", "PROCESSING"];
const RECEIPT_STATUSES = [...ACTIVE_STATUSES, "DRAFT_READY", "NEEDS_REVIEW", "CONFIRMED", "FAILED"];
let memoryState;
const uploadedImages = new Map();

function fail(status, code, message) {
  throw Object.assign(new Error(message), { status, code });
}

function clone(value) {
  return structuredClone(value);
}

function seed() {
  const now = new Date().toISOString();
  const day = todayIso();
  const draft = (transaction_id, total_amount = 147000) => ({
    transaction_id,
    merchant: "Cà phê Gia Đình",
    occurred_on: day,
    total_amount,
    category_id: 1,
    items: [
      { description: "Cà phê sữa", quantity: 2, amount: 98000, category_id: 1 },
      { description: "Bánh ngọt", quantity: 1, amount: 49000, category_id: 1 },
    ],
  });
  const receipts = [
    ["UPLOADING", [], null],
    ["UPLOADED", [], null],
    ["PROCESSING", [], null],
    ["DRAFT_READY", [], draft(3)],
    ["NEEDS_REVIEW", ["TOTAL_MISMATCH", "DUPLICATE_FILE", "DATE_MISSING"], draft(4, 150000)],
    ["FAILED", ["NOT_A_RECEIPT"], null],
    ["CONFIRMED", [], draft(1)],
  ].map(([status, warnings, data], i) => ({
    id: i + 1,
    status,
    content_type: "image/jpeg",
    error_code: status === "FAILED" ? "NOT_A_RECEIPT" : null,
    warnings,
    created_at: now,
    processed_at: ACTIVE_STATUSES.includes(status) ? null : now,
    accepted_at: ACTIVE_STATUSES.includes(status) ? Date.now() - i * 3000 : null,
    merchant: data?.merchant ?? `Hóa đơn mẫu ${i + 1}`,
    total_amount: data?.total_amount ?? null,
    occurred_on: data?.occurred_on ?? null,
    draft: data,
  }));
  return {
    version: 1,
    user: { ...DEMO_ACCOUNTS.owner },
    community_admin: false,
    community_posts: [
      { id: 1, type: "tip", title: "Chia ngân sách theo tuần để dễ theo dõi", body: "Chia khoản chi linh hoạt thành bốn tuần giúp gia đình nhận ra sớm khi một danh mục đang vượt kế hoạch.", status: "APPROVED", author: "Thức", updated_at: now, sample: true },
      { id: 2, type: "budget_template", title: "Mẫu ngân sách gia đình mới bắt đầu", body: "Bắt đầu với ăn uống, đi lại, hóa đơn cố định và tiết kiệm. Điều chỉnh tỷ lệ theo thu nhập thực tế của gia đình.", status: "APPROVED", author: "Chi", updated_at: now, sample: true },
      { id: 3, type: "tip", title: "Ghi chi tiêu ngay trong ngày", body: "Ghi lại các khoản nhỏ vào cuối ngày để không bỏ sót chi phí tiền mặt.", status: "PENDING", author: "Thức", updated_at: now, sample: true },
    ],
    notifications: [
      { id: 1, type: "budget_alert", title: "Cảnh báo ngân sách", body: "Một danh mục chi tiêu đã chạm ngưỡng thiết lập. Mở HomeWallet để xem chi tiết.", deep_link: "/budgets", created_at: now, read: false, read_at: null },
      { id: 2, type: "recurring_bill_reminder", title: "Nhắc hóa đơn", body: "Có hóa đơn định kỳ sắp đến hạn. Mở HomeWallet để xem lịch thanh toán.", deep_link: "/recurring-bills", created_at: now, read: true, read_at: now },
    ],
    push_subscriptions: [],
    household: { id: 1, name: "Gia đình HomeWallet", role: "owner", invite_code: "DEMO2026" },
    members: [
      { id: 1, display_name: "Thức", email: "thuc.demo@example.com", role: "owner", joined_at: now },
      { id: 2, display_name: "Chi", email: "chi.demo@example.com", role: "member", joined_at: now },
    ],
    categories: [
      { id: 1, name: "Ăn uống", icon: "utensils", is_fixed: false },
      { id: 2, name: "Đi lại", icon: "car", is_fixed: false },
      { id: 3, name: "Mua sắm", icon: "shopping-bag", is_fixed: false },
      { id: 4, name: "Điện nước", icon: "house", is_fixed: true },
    ],
    receipts,
    transactions: [
      { id: 1, receipt_id: 7, member_id: 1, status: "CONFIRMED", source: "OCR", ...draft(1), created_at: now },
      { id: 2, receipt_id: null, member_id: 2, status: "CONFIRMED", source: "MANUAL", merchant: "", occurred_on: day, total_amount: 80000, category_id: 2, note: "Đổ xăng", items: [], created_at: now },
      { id: 3, receipt_id: 4, member_id: 1, status: "DRAFT", source: "OCR", ...draft(3), created_at: now },
      { id: 4, receipt_id: 5, member_id: 1, status: "DRAFT", source: "OCR", ...draft(4, 150000), created_at: now },
    ],
    idempotency: {},
    membershipHistory: [],
  };
}

function readState() {
  if (memoryState) return memoryState;
  try {
    const stored = globalThis.localStorage?.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      if (parsed.version === 1 && Array.isArray(parsed.receipts)) memoryState = parsed;
    }
  } catch {
    // The demo also works when browser storage is unavailable.
  }
  memoryState ??= seed();
  // Repair demo sessions saved by the older role switcher, which changed the
  // seeded owner's role instead of switching to the member account.
  if (Array.isArray(memoryState.members) && memoryState.household?.role === "member" && memoryState.user?.id === 1 &&
      !memoryState.members.some((member) => member.role === "owner")) {
    const owner = memoryState.members.find((member) => member.id === 1 && member.email === "thuc.demo@example.com");
    const member = memoryState.members.find((entry) => entry.id === 2 && entry.email === "chi.demo@example.com" && entry.role === "member");
    if (owner && member) {
      owner.role = "owner";
      memoryState.user = { id: member.id, email: member.email, display_name: member.display_name };
      saveState();
    }
  }
  memoryState.community_admin ??= false;
  memoryState.community_posts ??= seed().community_posts;
  memoryState.notifications ??= seed().notifications;
  memoryState.push_subscriptions ??= [];
  memoryState.membershipHistory ??= [];
  return memoryState;
}

function saveState() {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify(memoryState));
  } catch {
    // Retain state for the current page when storage is disabled or full.
  }
}

export function resetMockData() {
  for (const url of uploadedImages.values()) URL.revokeObjectURL(url);
  uploadedImages.clear();
  memoryState = seed();
  setFinanceFailure("none");
  saveState();
}

export function setMockRole(role) {
  if (!Object.hasOwn(DEMO_ACCOUNTS, role)) throw new Error("Tài khoản thử nghiệm không hợp lệ.");
  const state = readState();
  const household = state.household || state.demo_household;
  const account = DEMO_ACCOUNTS[role];
  const member = state.members.find((item) => item.id === account.id);
  // Retain the existing household for other demo users even when the chosen
  // account has left. A dissolved household is removed from both locations.
  if (state.household) state.demo_household = { ...state.household };
  state.user = { ...account };
  state.household = household && member ? { ...household, role: member.role } : null;
  saveState();
}

function nextId(items) {
  return Math.max(0, ...items.map((item) => item.id)) + 1;
}

function endMockMembership(state, member, reason) {
  state.membershipHistory.push({
    id: nextId(state.membershipHistory),
    user_id: member.id,
    household_id: state.household.id,
    household_name: state.household.name,
    role: member.role,
    joined_at: member.joined_at,
    ended_at: new Date().toISOString(),
    end_reason: reason,
  });
}

function newDraft(state, receipt) {
  const transactionId = nextId(state.transactions);
  receipt.draft = {
    transaction_id: transactionId,
    merchant: "Cửa hàng mẫu HomeWallet",
    occurred_on: todayIso(),
    total_amount: 147000,
    category_id: 1,
    items: [
      { description: "Cà phê sữa", quantity: 2, amount: 98000, category_id: 1 },
      { description: "Bánh ngọt", quantity: 1, amount: 49000, category_id: 1 },
    ],
  };
  Object.assign(receipt, {
    merchant: receipt.draft.merchant,
    total_amount: receipt.draft.total_amount,
    occurred_on: receipt.draft.occurred_on,
    processed_at: new Date().toISOString(),
  });
  state.transactions.push({
    id: transactionId,
    receipt_id: receipt.id,
    member_id: state.user.id,
    status: "DRAFT",
    source: "OCR",
    ...clone(receipt.draft),
    created_at: receipt.created_at,
  });
}

function advance(state) {
  for (const receipt of state.receipts) {
    if (!ACTIVE_STATUSES.includes(receipt.status) || receipt.accepted_at == null) continue;
    const elapsed = Date.now() - receipt.accepted_at;
    if (elapsed >= 9000) {
      receipt.status = "DRAFT_READY";
      if (!receipt.draft) newDraft(state, receipt);
    } else if (elapsed >= 6000) receipt.status = "PROCESSING";
    else if (elapsed >= 3000) receipt.status = "UPLOADED";
  }
}

function receiptById(state, id) {
  const receipt = state.receipts.find((item) => item.id === Number(id));
  if (!receipt) fail(404, "NOT_FOUND", "Không tìm thấy hóa đơn.");
  return receipt;
}

function receiptDetail(receipt) {
  const { accepted_at: ignoredTime, ...detail } = receipt;
  void ignoredTime;
  return {
    ...detail,
    image_url: uploadedImages.get(receipt.id) ?? "/mock-receipt.svg",
    image_is_sample: !uploadedImages.has(receipt.id),
  };
}

function paginate(items, params) {
  const limitValue = params.get("limit") ?? "50";
  const cursorValue = params.get("cursor");
  const limit = Number(limitValue);
  const cursor = cursorValue ? Number(cursorValue) : null;
  if (!/^[+]?\d+$/.test(limitValue.trim()) || !Number.isSafeInteger(limit) || limit < 1 || limit > 100 ||
      (cursorValue && (!/^[+]?\d+$/.test(cursorValue.trim()) || !Number.isSafeInteger(cursor) || cursor <= 0))) {
    fail(422, "VALIDATION", "Thông tin phân trang không hợp lệ.");
  }
  const remaining = items.filter((item) => cursor === null || item.id < cursor).sort((a, b) => b.id - a.id);
  const page = remaining.slice(0, limit);
  return {
    items: page,
    next_cursor: remaining.length > limit ? String(page.at(-1).id) : null,
  };
}

function validDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T12:00:00Z`);
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  return value.slice(0, 4) !== "0000" && Number.isFinite(parsed.getTime()) &&
    parsed.toISOString().slice(0, 10) === value && value <= todayIso(tomorrow);
}

function validateMoney(value, label = "Số tiền") {
  if (!Number.isSafeInteger(value) || value <= 0) fail(422, "VALIDATION", `${label} phải là số nguyên đồng lớn hơn 0.`);
}

function validateCategory(state, id) {
  if (id == null) return;
  if (!state.categories.some((category) => category.id === id)) fail(422, "VALIDATION", "Danh mục không hợp lệ.");
}

function validateTransaction(state, body, isReceipt = false) {
  if (!body || typeof body !== "object" || Array.isArray(body)) fail(422, "VALIDATION", "Dữ liệu giao dịch không hợp lệ.");
  if (!isReceipt && (Object.keys(body).some((key) => !["occurred_on", "total_amount", "category_id", "note"].includes(key)) ||
      !["occurred_on", "total_amount", "category_id"].every((key) => Object.hasOwn(body, key)))) {
    fail(422, "VALIDATION", "Thiếu thông tin giao dịch hoặc có trường không được hỗ trợ.");
  }
  if (!validDate(body.occurred_on)) fail(422, "VALIDATION", "Ngày phải hợp lệ, có dạng YYYY-MM-DD và không quá một ngày trong tương lai.");
  validateMoney(body.total_amount);
  validateCategory(state, body.category_id);
  if (!isReceipt && body.note != null && (typeof body.note !== "string" || body.note.length > 500)) fail(422, "VALIDATION", "Ghi chú không quá 500 ký tự.");
  if (!isReceipt) return;
  if (body.merchant != null && typeof body.merchant !== "string") fail(422, "VALIDATION", "Tên cửa hàng không hợp lệ.");
  if (body.items != null && !Array.isArray(body.items)) fail(422, "VALIDATION", "Danh sách dòng hàng không hợp lệ.");
  for (const item of body.items ?? []) {
    if (!item || typeof item !== "object" || Array.isArray(item)) fail(422, "VALIDATION", "Dòng hàng không hợp lệ.");
    if (item.description != null && typeof item.description !== "string") fail(422, "VALIDATION", "Mô tả dòng hàng không hợp lệ.");
    if (item.quantity != null && (typeof item.quantity !== "number" || !Number.isFinite(item.quantity) || item.quantity <= 0 || item.quantity > 9999999.999)) fail(422, "VALIDATION", "Số lượng phải lớn hơn 0 và không quá 9999999.999.");
    if (item.unit_price != null && (!Number.isSafeInteger(item.unit_price) || item.unit_price < 0)) fail(422, "VALIDATION", "Đơn giá phải là số nguyên đồng không âm.");
    validateMoney(item.amount, "Thành tiền dòng hàng");
    validateCategory(state, item.category_id);
  }
}

function headerValue(headers, name) {
  if (typeof headers?.get === "function") return headers.get(name);
  const pair = Object.entries(headers ?? {}).find(([key]) => key.toLowerCase() === name.toLowerCase());
  return pair?.[1];
}

function periodValue(params) {
  const period = params.get("period") || todayIso().slice(0, 7);
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(period)) fail(422, "VALIDATION", "Kỳ phải có dạng YYYY-MM.");
  return period;
}

function filteredTransactions(state, params) {
  const period = periodValue(params);
  for (const field of ["member_id", "category_id"]) {
    const value = params.get(field);
    if (value && (!/^[+]?\d+$/.test(value.trim()) || !Number.isSafeInteger(Number(value)) || Number(value) <= 0)) {
      fail(422, "VALIDATION", "Tham số lọc không hợp lệ.");
    }
  }
  return state.transactions.filter((transaction) =>
    transaction.occurred_on.startsWith(period) &&
    (!params.get("member_id") || transaction.member_id === Number(params.get("member_id"))) &&
    (!params.get("category_id") || transaction.category_id === Number(params.get("category_id")))
  );
}

function dashboard(state, params) {
  if (!params.get("period")) fail(422, "VALIDATION", "Cần chọn kỳ báo cáo dạng YYYY-MM.");
  const period = periodValue(params);
  if (period.startsWith("0000") || period === "9999-12") fail(422, "VALIDATION", "Kỳ báo cáo không hợp lệ.");
  const transactions = state.transactions.filter((transaction) => transaction.occurred_on.startsWith(`${period}-`) && transaction.status === "CONFIRMED");
  const categories = [...state.categories];
  if (transactions.some((transaction) => transaction.category_id == null)) categories.push({ id: null, name: null });
  const members = [...state.members];
  for (const transaction of transactions) {
    if (!members.some((member) => member.id === transaction.member_id)) members.push({ id: transaction.member_id, display_name: "Thành viên" });
  }
  const weeks = new Map();
  for (const transaction of transactions) {
    const date = new Date(`${transaction.occurred_on}T12:00:00Z`);
    date.setUTCDate(date.getUTCDate() - (date.getUTCDay() + 6) % 7);
    const week = date.toISOString().slice(0, 10);
    weeks.set(week, (weeks.get(week) ?? 0) + transaction.total_amount);
  }
  return {
    period,
    total: transactions.reduce((sum, transaction) => sum + transaction.total_amount, 0),
    by_category: categories.map((category) => ({
      category_id: category.id,
      name: category.name,
      amount: transactions.filter((transaction) => transaction.category_id === category.id).reduce((sum, transaction) => sum + transaction.total_amount, 0),
    })).filter((row) => transactions.some((transaction) => transaction.category_id === row.category_id)),
    by_member: members.map((member) => ({
      user_id: member.id,
      display_name: member.display_name,
      amount: transactions.filter((transaction) => transaction.member_id === member.id).reduce((sum, transaction) => sum + transaction.total_amount, 0),
    })).filter((row) => transactions.some((transaction) => transaction.member_id === row.user_id)),
    by_week: [...weeks.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([week_start, amount]) => ({ week_start, amount })),
  };
}

export async function completeMockUpload(id, blob) {
  const state = readState();
  const receipt = receiptById(state, id);
  if (blob && typeof URL.createObjectURL === "function") {
    const oldUrl = uploadedImages.get(receipt.id);
    if (oldUrl) URL.revokeObjectURL(oldUrl);
    uploadedImages.set(receipt.id, URL.createObjectURL(blob));
  }
  receipt.accepted_at = Date.now() - 3000;
  receipt.status = "UPLOADED";
  saveState();
  return receipt.id;
}

function dispatch(path, { method = "GET", body, headers } = {}) {
  const state = readState();
  advance(state);
  const url = new URL(path, "https://homewallet.mock");
  const route = url.pathname;
  const verb = method.toUpperCase();
  const finance = dispatchFinance(state, route, verb, body, headers);
  if (finance.handled) return finance.result;
  const detail = /^\/api\/receipts\/(\d+)$/.exec(route);
  const confirm = /^\/api\/receipts\/(\d+)\/confirm$/.exec(route);
  if (route === "/api/me" && verb === "GET") {
    const household = state.household && { ...state.household };
    if (household && household.role !== "owner") delete household.invite_code;
    return { user: state.user, household };
  }
  if (route === "/api/me/household-history" && verb === "GET") {
    const current = state.household && state.members.find((member) => member.id === state.user.id);
    const items = current ? [{ household_id: state.household.id, household_name: state.household.name, role: current.role, joined_at: current.joined_at, ended_at: null, end_reason: null }] : [];
    for (const entry of [...state.membershipHistory].reverse()) {
      if (entry.user_id === state.user.id) items.push({ household_id: entry.household_id, household_name: entry.household_name, role: entry.role, joined_at: entry.joined_at, ended_at: entry.ended_at, end_reason: entry.end_reason });
    }
    return { items };
  }
  if (route === "/api/notifications" && verb === "GET") return { items: state.notifications };
  const notification = /^\/api\/notifications\/(\d+)$/.exec(route);
  if (notification && verb === "PATCH") {
    const item = state.notifications.find((entry) => entry.id === Number(notification[1]));
    if (!item) fail(404, "NOT_FOUND", "Không tìm thấy thông báo.");
    item.read = true; item.read_at ??= new Date().toISOString();
    return { id: item.id, read: true, read_at: item.read_at };
  }
  if (route === "/api/push/subscriptions" && verb === "POST") {
    const saved = state.push_subscriptions.find((entry) => entry.browser_id === body?.browser_id);
    if (saved) return { subscription: { id: saved.id } };
    const item = { id: nextId(state.push_subscriptions), browser_id: body?.browser_id || "mock-browser" };
    state.push_subscriptions.push(item);
    return { subscription: { id: item.id } };
  }
  const pushSubscription = /^\/api\/push\/subscriptions\/(\d+)$/.exec(route);
  if (pushSubscription && verb === "DELETE") {
    state.push_subscriptions = state.push_subscriptions.filter((entry) => entry.id !== Number(pushSubscription[1]));
    return null;
  }
  if (route === "/api/mock/community/admin" && verb === "POST") {
    state.community_admin = Boolean(body?.enabled);
    return { is_admin: state.community_admin };
  }
  if (route === "/api/community/posts" && verb === "GET") {
    return { items: state.community_posts.filter((post) => post.status === "APPROVED").sort((a, b) => b.id - a.id) };
  }
  if (route === "/api/community/posts" && verb === "POST") {
    if (!body?.title?.trim() || !body?.body?.trim() || !["tip", "budget_template"].includes(body.type)) fail(422, "VALIDATION", "Hãy nhập tiêu đề, nội dung và loại bài hợp lệ.");
    const post = { id: nextId(state.community_posts), type: body.type, title: body.title.trim(), body: body.body.trim(), status: "PENDING", author: state.user.display_name, updated_at: new Date().toISOString() };
    state.community_posts.push(post);
    return { post };
  }
  if (route === "/api/admin/community/posts" && verb === "GET") {
    if (!state.community_admin) fail(403, "FORBIDDEN", "Bạn không có quyền quản trị cộng đồng.");
    const status = url.searchParams.get("status");
    return { items: state.community_posts.filter((post) => !status || post.status === status).sort((a, b) => b.id - a.id) };
  }
  const communityPost = /^\/api\/admin\/community\/posts\/(\d+)$/.exec(route);
  if (communityPost && verb === "PATCH") {
    if (!state.community_admin) fail(403, "FORBIDDEN", "Bạn không có quyền quản trị cộng đồng.");
    const post = state.community_posts.find((entry) => entry.id === Number(communityPost[1]));
    if (!post) fail(404, "NOT_FOUND", "Không tìm thấy bài viết.");
    if (body?.title !== undefined) post.title = body.title.trim();
    if (body?.body !== undefined) post.body = body.body.trim();
    if (body?.status !== undefined && !["PENDING", "APPROVED", "HIDDEN"].includes(body.status)) fail(422, "VALIDATION", "Trạng thái bài viết không hợp lệ.");
    if (body?.status !== undefined) post.status = body.status;
    post.updated_at = new Date().toISOString();
    return { post };
  }
  if (route === "/api/categories" && verb === "GET") return { categories: state.categories };
  if (route === "/api/households/1/delete" && verb === "POST") {
    if (state.household?.id !== 1) fail(404, "NOT_FOUND", "Không tìm thấy");
    if (state.household.role !== "owner") fail(403, "FORBIDDEN", "Chỉ Chủ hộ được thực hiện thao tác này");
    if (!body || body.confirm !== true) fail(400, "CONFIRMATION_REQUIRED", "Cần xác nhận xóa vĩnh viễn hộ này");
    if (body.household_id != null && body.household_id !== 1) fail(422, "VALIDATION", "household_id không khớp");
    const receiptCount = state.receipts.length;
    for (const member of state.members) endMockMembership(state, member, "dissolved");
    for (const objectUrl of uploadedImages.values()) URL.revokeObjectURL(objectUrl);
    uploadedImages.clear();
    state.members = [];
    state.receipts = [];
    state.transactions = [];
    state.idempotency = {};
    if (state.financeByHousehold) delete state.financeByHousehold["1"];
    if (state.recurringByHousehold) delete state.recurringByHousehold["1"];
    delete state.demo_household;
    state.household = null;
    return { deleted: true, household_id: 1, s3_deleted: receiptCount, status: "deleted" };
  }
  if (route === "/api/households/1/members" && verb === "GET") {
    if (state.household?.id !== 1) fail(404, "NOT_FOUND", "Không tìm thấy");
    return { members: state.members };
  }
  if (route === "/api/households/1/invite-code" && verb === "POST") {
    if (state.household?.id !== 1) fail(404, "NOT_FOUND", "Không tìm thấy");
    if (state.household.role !== "owner") fail(403, "FORBIDDEN", "Chỉ Chủ hộ được thực hiện thao tác này");
    state.household.invite_code = crypto.randomUUID().replaceAll("-", "").slice(0, 8).toUpperCase();
    return { invite_code: state.household.invite_code };
  }
  if (route === "/api/households/1/members/me" && verb === "DELETE") {
    if (state.household?.id !== 1) fail(404, "NOT_FOUND", "Không tìm thấy");
    if (state.household.role !== "member") fail(403, "FORBIDDEN", "Chủ hộ không thể tự rời hộ");
    const member = state.members.find((item) => item.id === state.user.id);
    if (!member || member.role !== "member") fail(409, "MEMBERSHIP_CHANGED", "Quyền trong hộ đã thay đổi. Hãy tải lại trang");
    endMockMembership(state, member, "left");
    state.demo_household = { ...state.household };
    state.members = state.members.filter((item) => item.id !== state.user.id);
    state.household = null;
    return null;
  }
  const removeMember = /^\/api\/households\/1\/members\/(\d+)$/.exec(route);
  if (removeMember && verb === "DELETE") {
    if (state.household?.id !== 1) fail(404, "NOT_FOUND", "Không tìm thấy");
    if (state.household.role !== "owner") fail(403, "FORBIDDEN", "Chỉ Chủ hộ được thực hiện thao tác này");
    const member = state.members.find((item) => item.id === Number(removeMember[1]));
    if (!member) fail(404, "NOT_FOUND", "Không tìm thấy thành viên.");
    if (member.role === "owner") fail(422, "VALIDATION", "Không thể xóa Chủ hộ.");
    endMockMembership(state, member, "removed");
    state.members = state.members.filter((item) => item.id !== member.id);
    return null;
  }
  if (route === "/api/receipts" && verb === "GET") {
    const status = url.searchParams.get("status");
    if (status && !RECEIPT_STATUSES.includes(status)) fail(422, "VALIDATION", "Trạng thái hóa đơn không hợp lệ.");
    const receipts = state.receipts.filter((receipt) => !status || receipt.status === status).sort((a, b) => b.id - a.id);
    return paginate(receipts.map((receipt) => ({
      id: receipt.id, status: receipt.status, merchant: receipt.merchant,
      total_amount: receipt.total_amount, occurred_on: receipt.occurred_on,
      created_at: receipt.created_at, warnings: receipt.warnings,
    })), url.searchParams);
  }
  if (route === "/api/receipts" && verb === "POST") {
    if (!body || !["image/jpeg", "image/png", "application/pdf"].includes(body.content_type) || !Number.isInteger(body.size) || body.size <= 0 || body.size > 5 * 1024 * 1024) fail(422, "VALIDATION", "Chỉ nhận JPEG, PNG hoặc PDF dưới 5 MB.");
    const receipt = {
      id: nextId(state.receipts), status: "UPLOADING", error_code: null, warnings: [],
      created_at: new Date().toISOString(), processed_at: null, accepted_at: null,
      merchant: "", total_amount: null, occurred_on: null, draft: null, content_type: body.content_type,
    };
    state.receipts.push(receipt);
    return { receipt: { id: receipt.id, status: receipt.status }, upload: { url: `mock://receipts/${receipt.id}`, fields: {} } };
  }
  if (detail && verb === "GET") return receiptDetail(receiptById(state, detail[1]));
  if (detail && verb === "DELETE") {
    const receipt = receiptById(state, detail[1]);
    state.transactions = state.transactions.filter((item) => item.receipt_id !== receipt.id);
    state.receipts = state.receipts.filter((item) => item.id !== receipt.id);
    return { deleted: true };
  }
  if (confirm && verb === "POST") {
    validateTransaction(state, body, true);
    const receipt = receiptById(state, confirm[1]);
    if (receipt.status === "CONFIRMED") fail(409, "ALREADY_CONFIRMED", "Hóa đơn đã được xác nhận.");
    if (!["DRAFT_READY", "NEEDS_REVIEW"].includes(receipt.status)) fail(409, "DRAFT_NOT_READY", "Hóa đơn chưa sẵn sàng xác nhận.");
    const transaction = state.transactions.find((item) => item.id === receipt.draft?.transaction_id);
    if (!transaction || transaction.status !== "DRAFT") fail(409, "DRAFT_NOT_FOUND", "Chưa có giao dịch nháp cho hóa đơn.");
    Object.assign(transaction, {
      occurred_on: body.occurred_on,
      total_amount: body.total_amount,
      merchant: body.merchant ?? null,
      category_id: body.category_id ?? null,
      status: "CONFIRMED",
    });
    if (body.items != null) transaction.items = body.items.map((item) => ({
      description: item.description ?? null,
      quantity: item.quantity ?? null,
      unit_price: item.unit_price ?? null,
      amount: item.amount,
      category_id: item.category_id ?? null,
    }));
    receipt.status = "CONFIRMED";
    receipt.draft = {
      transaction_id: transaction.id,
      occurred_on: transaction.occurred_on,
      total_amount: transaction.total_amount,
      merchant: transaction.merchant,
      category_id: transaction.category_id,
      items: clone(transaction.items),
    };
    Object.assign(receipt, { merchant: transaction.merchant, total_amount: transaction.total_amount, occurred_on: transaction.occurred_on });
    return { transaction };
  }
  if (route === "/api/transactions" && verb === "GET") return paginate(filteredTransactions(state, url.searchParams), url.searchParams);
  if (route === "/api/transactions" && verb === "POST") {
    const key = headerValue(headers, "Idempotency-Key");
    if (typeof key !== "string" || !/^[\x21-\x7e]{1,64}$/.test(key)) fail(422, "VALIDATION", "Idempotency-Key không hợp lệ.");
    validateTransaction(state, body);
    const payload = { occurred_on: body.occurred_on, total_amount: body.total_amount, category_id: body.category_id, note: body.note ?? null };
    const previous = Object.hasOwn(state.idempotency, key) ? state.idempotency[key] : null;
    if (previous) {
      return { transaction: state.transactions.find((item) => item.id === previous.id) };
    }
    const transaction = { id: nextId(state.transactions), ...payload, receipt_id: null, member_id: state.user.id, status: "CONFIRMED", source: "MANUAL", items: [], created_at: new Date().toISOString() };
    state.transactions.push(transaction);
    Object.defineProperty(state.idempotency, key, { value: { id: transaction.id }, enumerable: true, configurable: true, writable: true });
    return { transaction };
  }
  if (route === "/api/dashboard" && verb === "GET") return dashboard(state, url.searchParams);
  const recurring = dispatchRecurringMock(state, route, verb, body);
  if (recurring.handled) return recurring.result;
  fail(404, "MOCK_NOT_FOUND", "Chưa có dữ liệu giả cho yêu cầu này.");
}

export async function mockApi(path, options) {
  const result = dispatch(path, options);
  saveState();
  return clone(result);
}
