import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { loadDashboardData, localPeriod } from "../dashboardData";
import { formatDate, formatVnd } from "../format";
import { usePreferences } from "../preferences";

const compactMoney = (value) => new Intl.NumberFormat(document.documentElement.lang === "en" ? "en-US" : "vi-VN", { notation: "compact", maximumFractionDigits: 1 }).format(value);

export default function Dashboard() {
  const location = useLocation();
  const { t, locale } = usePreferences();
  const requestedPeriod = new URLSearchParams(location.search).get("period");
  const [period, setPeriod] = useState(() => /^\d{4}-(0[1-9]|1[0-2])$/.test(requestedPeriod || "") ? requestedPeriod : localPeriod());
  const [memberId, setMemberId] = useState("");
  const [reloadVersion, setReloadVersion] = useState(0);
  const [result, setResult] = useState(null);
  const [search, setSearch] = useState("");
  const [source, setSource] = useState("all");
  const queryKey = `${period}:${memberId}:${reloadVersion}`;

  useEffect(() => {
    const controller = new AbortController();
    loadDashboardData(api, { period, memberId, signal: controller.signal }).then((data) => {
      if (!controller.signal.aborted) setResult({ ...data, key: queryKey });
    }).catch((error) => {
      if (!controller.signal.aborted) setResult({ key: queryKey, error: error.message, requestId: error.requestId });
    });
    return () => controller.abort();
  }, [period, memberId, reloadVersion, queryKey]);

  const loading = result?.key !== queryKey;
  const summary = !loading ? result?.summary : null;
  const transactions = !loading ? result?.transactions || [] : [];
  const categoryData = summary?.by_category?.filter((category) => Number(category.amount) > 0) || [];
  const weeklyData = summary?.by_week?.map((week) => ({ ...week, label: formatDate(week.week_start).slice(0, 5) })) || [];
  const members = result?.members || [];
  const largestCategory = [...categoryData].sort((a, b) => Number(b.amount) - Number(a.amount))[0];
  const categoryName = (id) => result?.categories?.find((category) => String(category.id) === String(id))?.name || t("Chưa phân loại");
  const memberName = (id) => members.find((member) => String(member.id) === String(id))?.display_name
    || summary?.by_member?.find((member) => String(member.user_id) === String(id))?.display_name || t("Thành viên");

  const daily = Object.entries(transactions.reduce((acc, transaction) => {
    const day = transaction.occurred_on?.slice(0, 10);
    if (day) acc[day] = (acc[day] || 0) + Number(transaction.total_amount);
    return acc;
  }, {})).sort(([a], [b]) => a.localeCompare(b)).map(([date, amount]) => ({ date, label: formatDate(date).slice(0, 5), amount }));
  const cumulative = daily.map((day, index) => ({ ...day, total: daily.slice(0, index + 1).reduce((sum, item) => sum + item.amount, 0) }));
  const visibleTransactions = transactions.filter((transaction) => {
    const matchesSource = source === "all" || (source === "OCR" ? transaction.source === "OCR" : transaction.source !== "OCR");
    const text = `${transaction.merchant || ""} ${transaction.note || ""}`.toLocaleLowerCase(locale === "en" ? "en" : "vi");
    return matchesSource && text.includes(search.toLocaleLowerCase(locale === "en" ? "en" : "vi"));
  });
  const maxCategory = Math.max(1, ...categoryData.map((category) => Number(category.amount)));

  return <>
    <div className="page-heading dashboard-heading">
      <div><p className="eyebrow">● {result?.household?.name || t("Hộ gia đình")} · {transactions.length} {t("giao dịch đã xác nhận")}</p><h1>{t("Chi tiêu tháng")} {period.split("-")[1]}</h1></div>
      <div className="dashboard-total"><span>{t("Tổng chi trong tháng")}</span><strong>{summary ? formatVnd(summary.total) : "—"}</strong><small>{t("Giao dịch đã xác nhận")}</small></div>
    </div>
    <div className="dashboard-toolbar">
      <div className="dashboard-filters">
        <label className="field" htmlFor="dashboard-period">Tháng<input id="dashboard-period" type="month" min="0001-01" max="9998-12" value={period} required onChange={(e) => { if (/^\d{4}-(0[1-9]|1[0-2])$/.test(e.target.value)) setPeriod(e.target.value); }} /></label>
        <label className="field" htmlFor="dashboard-member">Thành viên<select id="dashboard-member" value={memberId} onChange={(e) => setMemberId(e.target.value)}><option value="">Tất cả thành viên</option>{members.map((member) => <option key={member.id} value={member.id}>{member.display_name}</option>)}</select></label>
        <button type="button" className="button-secondary" disabled={loading} onClick={() => setReloadVersion((value) => value + 1)}>Làm mới</button>
      </div>
      <div className="actions"><Link className="button button-secondary" to="/receipts">Xác nhận hóa đơn</Link><Link className="button" to="/transactions/new">+ Nhập giao dịch</Link></div>
    </div>
    {(location.state?.success || location.state?.receiptConfirmedId) && <p className="success" role="status">{location.state.receiptConfirmedId ? `${t("Đã xác nhận hóa đơn")} #${location.state.receiptConfirmedId}. ${t("Thống kê đang hiển thị đúng tháng trên hóa đơn.")}` : t(location.state.success)}</p>}
    {loading ? <p role="status">{t("Đang tải chi tiêu...")}</p> : result.error ? <section className="card"><p className="error" role="alert">{t(result.error)}</p>{result.requestId && <p className="muted">{t("Mã yêu cầu:")} <code>{result.requestId}</code></p>}<button type="button" onClick={() => setReloadVersion((value) => value + 1)}>{t("Thử lại")}</button></section> : !result.household ? <p>{t("Bạn cần")} <Link to="/">{t("tạo hoặc tham gia một hộ")}</Link> {t("để xem tổng quan.")}</p> : <>
      <div className="dashboard-overview">
        <section className="card dashboard-journey"><h2>↗ &nbsp;{t("Diễn biến chi tiêu")}</h2>{cumulative.length ? <><div className="chart-canvas" role="img" aria-label={t("Biểu đồ chi tiêu lũy kế theo ngày")}><ResponsiveContainer width="100%" height="100%"><AreaChart data={cumulative} margin={{ top: 14, right: 12, left: 0, bottom: 0 }}><CartesianGrid stroke="#eceef1" vertical={false} /><XAxis dataKey="label" tick={{ fontSize: 11 }} /><YAxis tickFormatter={compactMoney} width={50} tick={{ fontSize: 11 }} /><Tooltip formatter={(value) => [formatVnd(value), t("Lũy kế")]} /><Area type="monotone" dataKey="total" stroke="#1d5fe0" fill="#edf3fe" strokeWidth={2.5} isAnimationActive={false} /></AreaChart></ResponsiveContainer></div><div className="dashboard-insights"><div><small>{t("Chi nhiều nhất")}</small><b>{largestCategory?.name || "—"}</b></div><div><small>{t("Tổng chi")}</small><b>{formatVnd(summary.total)}</b></div><div><small>{t("Trung bình / giao dịch")}</small><b>{formatVnd(Math.round(summary.total / transactions.length))}</b></div><div><small>{t("Giao dịch")}</small><b>{transactions.length}</b></div></div></> : <p className="empty-state">{t("Chưa có chi tiêu để vẽ biểu đồ.")}</p>}</section>
        <section className="card dashboard-categories"><div className="dashboard-card-head"><h2>◉ &nbsp;Theo danh mục</h2><Link to={`/budgets?period=${period}`}>↗</Link></div>{categoryData.length ? <div className="category-bars">{[...categoryData].sort((a,b) => b.amount-a.amount).map((category) => <div key={category.category_id ?? "none"}><div className="category-bar-label"><span>{category.name}</span><b>{formatVnd(category.amount)} <small>{Math.round(category.amount / summary.total * 100)}%</small></b></div><div className="category-track"><span style={{ width: `${Number(category.amount) / maxCategory * 100}%` }} /></div></div>)}</div> : <p className="empty-state">Chưa có chi tiêu theo danh mục.</p>}</section>
        <div className="dashboard-stack"><section className="card"><div className="dashboard-card-head"><h2>♙ &nbsp;Theo thành viên</h2><Link to="/">↗</Link></div>{summary.by_member?.length ? <div className="member-list">{summary.by_member.map((member) => <div className="member-row" key={member.user_id}><span className="member-avatar">{member.display_name?.slice(0, 1).toUpperCase()}</span><span>{member.display_name}</span><b>{formatVnd(member.amount)}</b></div>)}</div> : <p className="empty-state">Chưa có giao dịch đã xác nhận.</p>}<div className="dashboard-tiles"><div><small>Giao dịch</small><b>{transactions.length}</b></div><div><small>Tổng chi</small><b>{formatVnd(summary.total)}</b></div></div></section><section className="card"><h2>✓ &nbsp;Việc cần làm</h2><div className="dashboard-quick-actions"><Link className="button button-secondary" to="/receipts">Kiểm tra và xác nhận hóa đơn →</Link><Link className="button button-secondary" to="/recurring-bills">Xem hóa đơn định kỳ →</Link><Link className="button button-secondary" to={`/budgets?period=${period}`}>Theo dõi ngân sách →</Link></div><div className="dashboard-note">Bản nháp hóa đơn chỉ được tính vào thống kê sau khi xác nhận.</div></section></div>
      </div>
      <div className="dashboard-bottom"><section className="card transaction-list"><div className="dashboard-card-head"><h2>☷ &nbsp;Giao dịch trong tháng</h2><Link className="button button-secondary" to="/transactions/new">+ Nhập giao dịch</Link></div><div className="transaction-filters"><div className="filter-pills">{[["all", "Tất cả"], ["OCR", "Hóa đơn"], ["manual", "Thủ công"]].map(([value,label]) => <button key={value} type="button" className={source === value ? "selected" : ""} onClick={() => setSource(value)}>{label}</button>)}</div><label><span className="sr-only">Tìm giao dịch</span><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Tìm giao dịch" /></label></div>{visibleTransactions.length ? <div className="table-scroll"><table><thead><tr><th>Ngày</th><th>Nội dung</th><th>Danh mục</th><th>Thành viên</th><th>Nguồn</th><th className="text-right">Số tiền</th></tr></thead><tbody>{visibleTransactions.map((transaction) => <tr key={transaction.id}><td>{formatDate(transaction.occurred_on)}</td><td>{transaction.merchant || transaction.note || "Chi tiêu thủ công"}</td><td>{categoryName(transaction.category_id)}</td><td>{memberName(transaction.member_id ?? transaction.user_id)}</td><td><span className="status-badge">{transaction.source === "OCR" ? "Hóa đơn" : "Thủ công"}</span></td><td className="text-right money">{formatVnd(transaction.total_amount)}</td></tr>)}</tbody></table></div> : <div className="empty-state">{transactions.length ? "Không có giao dịch phù hợp." : "Chưa có giao dịch đã xác nhận trong tháng này."}</div>}</section>
      <section className="card chart-panel"><div className="dashboard-card-head"><h2>▥ &nbsp;Theo tuần</h2><span className="status-badge">{period.split("-").reverse().join("/")}</span></div>{weeklyData.length ? <><div className="chart-canvas" role="img" aria-label="Biểu đồ chi tiêu từng tuần"><ResponsiveContainer width="100%" height="100%"><BarChart data={weeklyData} margin={{ top: 12, right: 8, bottom: 4, left: 0 }}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" tick={{ fontSize: 11 }} /><YAxis tickFormatter={compactMoney} width={52} tick={{ fontSize: 11 }} /><Tooltip formatter={(value) => [formatVnd(value), "Chi tiêu"]} /><Bar dataKey="amount" fill="#1d5fe0" radius={[6, 6, 0, 0]} isAnimationActive={false} /></BarChart></ResponsiveContainer></div><ul className="chart-legend">{weeklyData.map((week) => <li key={week.week_start}><span>Tuần từ {formatDate(week.week_start)}</span><b>{formatVnd(week.amount)}</b></li>)}</ul></> : <p className="empty-state">Chưa có chi tiêu theo tuần.</p>}</section></div>
    </>}
  </>;
}
