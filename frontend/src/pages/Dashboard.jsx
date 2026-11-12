import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { loadDashboardData, localPeriod } from "../dashboardData";
import { formatDate, formatVnd } from "../format";
import { usePreferences } from "../preferences";
import MonthPicker from "../components/MonthPicker";

const compactMoney = (value, locale) => new Intl.NumberFormat(locale === "en" ? "en-US" : "vi-VN", { notation: "compact", maximumFractionDigits: 1 }).format(value);

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
  const categoryName = (id) => t(result?.categories?.find((category) => String(category.id) === String(id))?.name || "Chưa phân loại");
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
        <label className="field month-field" htmlFor="dashboard-period">{t("Tháng")}<MonthPicker key={period} id="dashboard-period" value={period} onChange={(nextPeriod) => { if (/^(?!0000)\d{4}-(0[1-9]|1[0-2])$/.test(nextPeriod)) setPeriod(nextPeriod); }} /></label>
        <label className="field" htmlFor="dashboard-member">{t("Thành viên")}<select id="dashboard-member" value={memberId} onChange={(e) => setMemberId(e.target.value)}><option value="">{t("Tất cả thành viên")}</option>{members.map((member) => <option key={member.id} value={member.id}>{member.display_name}</option>)}</select></label>
        <button type="button" className="button-secondary" disabled={loading} onClick={() => setReloadVersion((value) => value + 1)}>{t("Làm mới")}</button>
      </div>
      <div className="actions"><Link className="button button-secondary" to="/receipts">{t("Xác nhận hóa đơn")}</Link><Link className="button" to="/transactions/new">{t("+ Nhập giao dịch")}</Link></div>
    </div>
    {(location.state?.success || location.state?.receiptConfirmedId) && <p className="success" role="status">{location.state.receiptConfirmedId ? `${t("Đã xác nhận hóa đơn")} #${location.state.receiptConfirmedId}. ${t("Thống kê đang hiển thị đúng tháng trên hóa đơn.")}` : t(location.state.success)}</p>}
    {loading ? <p role="status">{t("Đang tải chi tiêu...")}</p> : result.error ? <section className="card"><p className="error" role="alert">{t(result.error)}</p>{result.requestId && <p className="muted">{t("Mã yêu cầu:")} <code>{result.requestId}</code></p>}<button type="button" onClick={() => setReloadVersion((value) => value + 1)}>{t("Thử lại")}</button></section> : !result.household ? <p>{t("Bạn cần")} <Link to="/">{t("tạo hoặc tham gia một hộ")}</Link> {t("để xem tổng quan.")}</p> : <>
      <div className="dashboard-overview">
        <section className="card dashboard-journey"><h2>↗ &nbsp;{t("Diễn biến chi tiêu")}</h2>{cumulative.length ? <><div className="chart-canvas" role="img" aria-label={t("Biểu đồ chi tiêu lũy kế theo ngày")}><ResponsiveContainer width="100%" height="100%"><AreaChart data={cumulative} margin={{ top: 14, right: 12, left: 0, bottom: 0 }}><CartesianGrid stroke="#eceef1" vertical={false} /><XAxis dataKey="label" tick={{ fontSize: 11 }} /><YAxis tickFormatter={(value) => compactMoney(value, locale)} width={50} tick={{ fontSize: 11 }} /><Tooltip formatter={(value) => [formatVnd(value), t("Lũy kế")]} /><Area type="monotone" dataKey="total" stroke="#1d5fe0" fill="#edf3fe" strokeWidth={2.5} isAnimationActive={false} /></AreaChart></ResponsiveContainer></div><div className="dashboard-insights"><div><small>{t("Chi nhiều nhất")}</small><b>{t(largestCategory?.name || "—")}</b></div><div><small>{t("Tổng chi")}</small><b>{formatVnd(summary.total)}</b></div><div><small>{t("Trung bình / giao dịch")}</small><b>{formatVnd(Math.round(summary.total / transactions.length))}</b></div><div><small>{t("Giao dịch")}</small><b>{transactions.length}</b></div></div></> : <p className="empty-state">{t("Chưa có chi tiêu để vẽ biểu đồ.")}</p>}</section>
        <section className="card dashboard-categories"><div className="dashboard-card-head"><h2>{t("◉  Theo danh mục")}</h2><Link to={`/budgets?period=${period}`}>↗</Link></div>{categoryData.length ? <div className="category-bars">{[...categoryData].sort((a,b) => b.amount-a.amount).map((category) => <div key={category.category_id ?? "none"}><div className="category-bar-label"><span>{t(category.name)}</span><b>{formatVnd(category.amount)} <small>{Math.round(category.amount / summary.total * 100)}%</small></b></div><div className="category-track"><span style={{ width: `${Number(category.amount) / maxCategory * 100}%` }} /></div></div>)}</div> : <p className="empty-state">{t("Chưa có chi tiêu theo danh mục.")}</p>}</section>
        <div className="dashboard-stack"><section className="card"><div className="dashboard-card-head"><h2>{t("♙  Theo thành viên")}</h2><Link to="/">↗</Link></div>{summary.by_member?.length ? <div className="member-list">{summary.by_member.map((member) => <div className="member-row" key={member.user_id}><span className="member-avatar">{member.display_name?.slice(0, 1).toUpperCase()}</span><span>{member.display_name}</span><b>{formatVnd(member.amount)}</b></div>)}</div> : <p className="empty-state">{t("Chưa có giao dịch đã xác nhận.")}</p>}<div className="dashboard-tiles"><div><small>{t("Giao dịch")}</small><b>{transactions.length}</b></div><div><small>{t("Tổng chi")}</small><b>{formatVnd(summary.total)}</b></div></div></section><section className="card"><h2>{t("✓  Việc cần làm")}</h2><div className="dashboard-quick-actions"><Link className="button button-secondary" to="/receipts">{t("Kiểm tra và xác nhận hóa đơn →")}</Link><Link className="button button-secondary" to="/recurring-bills">{t("Xem hóa đơn định kỳ →")}</Link><Link className="button button-secondary" to={`/budgets?period=${period}`}>{t("Theo dõi ngân sách →")}</Link></div><div className="dashboard-note">{t("Bản nháp hóa đơn chỉ được tính vào thống kê sau khi xác nhận.")}</div></section></div>
      </div>
      <div className="dashboard-bottom"><section className="card transaction-list"><div className="dashboard-card-head"><h2>{t("☷  Giao dịch trong tháng")}</h2><Link className="button button-secondary" to="/transactions/new">{t("+ Nhập giao dịch")}</Link></div><div className="transaction-filters"><div className="filter-pills">{[["all", t("Tất cả")], ["OCR", t("Hóa đơn")], ["manual", t("Thủ công")]].map(([value,label]) => <button key={value} type="button" className={source === value ? "selected" : ""} onClick={() => setSource(value)}>{label}</button>)}</div><label><span className="sr-only">{t("Tìm giao dịch")}</span><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("Tìm giao dịch")} /></label></div>{visibleTransactions.length ? <div className="table-scroll"><table><thead><tr><th>{t("Ngày")}</th><th>{t("Nội dung")}</th><th>{t("Danh mục")}</th><th>{t("Thành viên")}</th><th>{t("Nguồn")}</th><th className="text-right">{t("Số tiền")}</th></tr></thead><tbody>{visibleTransactions.map((transaction) => <tr key={transaction.id}><td>{formatDate(transaction.occurred_on)}</td><td>{transaction.merchant || transaction.note || t("Chi tiêu thủ công")}</td><td>{categoryName(transaction.category_id)}</td><td>{memberName(transaction.member_id ?? transaction.user_id)}</td><td><span className="status-badge">{transaction.source === "OCR" ? t("Hóa đơn") : t("Thủ công")}</span></td><td className="text-right money">{formatVnd(transaction.total_amount)}</td></tr>)}</tbody></table></div> : <div className="empty-state">{transactions.length ? t("Không có giao dịch phù hợp.") : t("Chưa có giao dịch đã xác nhận trong tháng này.")}</div>}</section>
      <section className="card chart-panel"><div className="dashboard-card-head"><h2>{t("▥  Theo tuần")}</h2><span className="status-badge">{period.split("-").reverse().join("/")}</span></div>{weeklyData.length ? <><div className="chart-canvas" role="img" aria-label={t("Biểu đồ chi tiêu từng tuần")}><ResponsiveContainer width="100%" height="100%"><BarChart data={weeklyData} margin={{ top: 12, right: 8, bottom: 4, left: 0 }}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" tick={{ fontSize: 11 }} /><YAxis tickFormatter={(value) => compactMoney(value, locale)} width={52} tick={{ fontSize: 11 }} /><Tooltip formatter={(value) => [formatVnd(value), t("Chi tiêu")]} /><Bar dataKey="amount" fill="#1d5fe0" radius={[6, 6, 0, 0]} isAnimationActive={false} /></BarChart></ResponsiveContainer></div><ul className="chart-legend">{weeklyData.map((week) => <li key={week.week_start}><span>{t("Tuần từ ")}{formatDate(week.week_start)}</span><b>{formatVnd(week.amount)}</b></li>)}</ul></> : <p className="empty-state">{t("Chưa có chi tiêu theo tuần.")}</p>}</section></div>
    </>}
  </>;
}
