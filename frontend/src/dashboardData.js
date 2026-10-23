export function localPeriod() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function weekStart(iso) {
  const date = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return null;
  date.setUTCDate(date.getUTCDate() - ((date.getUTCDay() + 6) % 7));
  return date.toISOString().slice(0, 10);
}

export function aggregateTransactions(transactions, period, categories, members) {
  const byCategory = new Map();
  const byMember = new Map();
  const byWeek = new Map();
  let total = 0;
  for (const transaction of transactions) {
    if (transaction.status !== "CONFIRMED" || !transaction.occurred_on?.startsWith(`${period}-`)) continue;
    const amount = Number(transaction.total_amount);
    if (!Number.isSafeInteger(amount) || amount <= 0) throw new Error("Dữ liệu giao dịch có số tiền không hợp lệ; chưa thể tính tổng chi.");
    total += amount;
    const categoryId = transaction.category_id ?? null;
    const memberId = transaction.member_id ?? transaction.user_id;
    byCategory.set(categoryId, (byCategory.get(categoryId) || 0) + amount);
    byMember.set(memberId, (byMember.get(memberId) || 0) + amount);
    const week = weekStart(transaction.occurred_on);
    if (week) byWeek.set(week, (byWeek.get(week) || 0) + amount);
  }
  return {
    period,
    total,
    by_category: Array.from(byCategory, ([category_id, amount]) => ({ category_id, amount, name: categories.find((c) => String(c.id) === String(category_id))?.name || "Chưa phân loại" })),
    by_member: Array.from(byMember, ([user_id, amount]) => ({ user_id, amount, display_name: members.find((m) => String(m.id) === String(user_id))?.display_name || "Thành viên" })),
    by_week: Array.from(byWeek, ([week_start, amount]) => ({ week_start, amount })).sort((a, b) => a.week_start.localeCompare(b.week_start)),
  };
}

export async function loadAllTransactions(api, query, signal) {
  const transactions = [];
  const cursors = new Set();
  let cursor;
  do {
    const params = new URLSearchParams({ ...query, limit: "50" });
    if (cursor) params.set("cursor", cursor);
    const result = await api(`/api/transactions?${params}`, { signal });
    if (signal?.aborted) throw new DOMException("Request aborted", "AbortError");
    if (!Array.isArray(result?.items)) throw new Error("Dữ liệu danh sách giao dịch không hợp lệ.");
    transactions.push(...result.items);
    cursor = result.next_cursor;
    if (cursor && cursors.has(cursor)) throw new Error("API trả lại con trỏ phân trang trùng. Chưa thể tính đủ tổng chi.");
    if (cursor) cursors.add(cursor);
  } while (cursor);
  return Array.from(new Map(transactions.map((transaction) => [transaction.id, transaction])).values());
}

export async function loadDashboardData(api, { period, memberId = "", signal }) {
  const me = await api("/api/me", { signal });
  if (!me?.user) throw new Error("Không tải được hồ sơ người dùng.");
  if (!me.household) return { household: null, members: [] };

  const query = { period };
  if (memberId) query.member_id = memberId;
  // The summary API supports a period only. Member filtering uses the complete
  // paginated transaction list rather than an unsupported dashboard parameter.
  const summaryRequest = memberId ? Promise.resolve(null)
    : api(`/api/dashboard?${new URLSearchParams({ period })}`, { signal });
  const [summary, categoriesResult, membersResult, rows] = await Promise.all([
    summaryRequest,
    api("/api/categories", { signal }),
    api(`/api/households/${me.household.id}/members`, { signal }),
    loadAllTransactions(api, query, signal),
  ]);
  if (!Array.isArray(categoriesResult?.categories) || !Array.isArray(membersResult?.members)) {
    throw new Error("Dữ liệu danh mục hoặc thành viên không hợp lệ.");
  }
  const transactions = rows.filter((row) => row.status === "CONFIRMED"
    && row.occurred_on?.startsWith(`${period}-`)
    && (!memberId || String(row.member_id) === String(memberId)));
  if (!memberId && (!summary || summary.period !== period || !Number.isSafeInteger(summary.total)
    || summary.total < 0 || ![summary.by_category, summary.by_member, summary.by_week].every(Array.isArray))) {
    throw new Error("Dữ liệu tổng quan không hợp lệ. Hãy thử tải lại.");
  }
  return {
    household: me.household,
    members: membersResult.members,
    categories: categoriesResult.categories,
    transactions,
    summary: memberId
      ? aggregateTransactions(transactions, period, categoriesResult.categories, membersResult.members)
      : {
        ...summary,
        by_category: summary.by_category.map((row) => ({ ...row, name: row.name?.trim() || "Chưa phân loại" })),
        by_member: summary.by_member.map((row) => ({ ...row, display_name: row.display_name?.trim() || "Thành viên" })),
      },
  };
}
