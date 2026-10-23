import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { loadDashboardData, localPeriod } from "../dashboardData";
import { formatDate, formatVnd } from "../format";

const COLORS = ["#2563eb", "#0d9488", "#d97706", "#7c3aed", "#db2777", "#64748b"];
const compactMoney = (value) => new Intl.NumberFormat("vi-VN", { notation: "compact", maximumFractionDigits: 1 }).format(value);

export default function Dashboard() {
  const location = useLocation();
  const [period, setPeriod] = useState(localPeriod);
  const [memberId, setMemberId] = useState("");
  const [reloadVersion, setReloadVersion] = useState(0);
  const [result, setResult] = useState(null);
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
  const categoryName = (id) => result?.categories?.find((category) => String(category.id) === String(id))?.name || "Chưa phân loại";
  const memberName = (id) => members.find((member) => String(member.id) === String(id))?.display_name
    || summary?.by_member?.find((member) => String(member.user_id) === String(id))?.display_name || "Thành viên";

  return (
    <>
      <div className="page-heading">
        <div><p className="eyebrow">Tổng quan</p><h1>Chi tiêu gia đình</h1><p className="muted">Theo dõi những khoản chi đã được xác nhận.</p></div>
        <Link className="button" to="/transactions/new">+ Nhập giao dịch</Link>
      </div>
      {location.state?.success && <p className="success" role="status">{location.state.success}</p>}
      <div className="card dashboard-filters">
        <label className="field" htmlFor="dashboard-period">Tháng
          <input id="dashboard-period" type="month" min="0001-01" max="9998-12" value={period} required onChange={(e) => { if (/^\d{4}-(0[1-9]|1[0-2])$/.test(e.target.value)) setPeriod(e.target.value); }} />
        </label>
        <label className="field" htmlFor="dashboard-member">Thành viên
          <select id="dashboard-member" value={memberId} onChange={(e) => setMemberId(e.target.value)}>
            <option value="">Tất cả thành viên</option>
            {members.map((member) => <option key={member.id} value={member.id}>{member.display_name}</option>)}
          </select>
        </label>
        <button type="button" className="button-secondary" disabled={loading} onClick={() => setReloadVersion((value) => value + 1)}>Làm mới</button>
      </div>
      {loading ? <p role="status">Đang tải chi tiêu...</p> : result.error ? (
        <section className="card"><p className="error" role="alert">{result.error}</p>{result.requestId && <p className="muted">Mã yêu cầu: <code>{result.requestId}</code></p>}<button type="button" onClick={() => setReloadVersion((value) => value + 1)}>Thử lại</button></section>
      ) : !result.household ? <p>Bạn cần <Link to="/">tạo hoặc tham gia một hộ</Link> để xem tổng quan.</p> : (
        <>
          <div className="metrics-grid">
            <section className="card metric"><h2>Tổng chi tháng {period.split("-").reverse().join("/")}</h2><strong>{formatVnd(summary.total)}</strong><p>Chỉ tính giao dịch đã xác nhận</p></section>
            <section className="card metric"><h2>Giao dịch đã xác nhận</h2><strong>{transactions.length}</strong><p>{memberId ? `Của ${memberName(memberId)}` : "Của tất cả thành viên"}</p></section>
            <section className="card metric"><h2>Danh mục chi nhiều nhất</h2><strong className="metric-name">{largestCategory?.name || "Chưa có"}</strong><p>{largestCategory ? formatVnd(largestCategory.amount) : "Chưa có chi tiêu trong kỳ này"}</p></section>
          </div>
          <div className="chart-grid">
            <section className="card chart-panel">
              <h2>Theo danh mục</h2>
              {categoryData.length ? <>
                <div className="chart-canvas" role="img" aria-label="Biểu đồ tỷ trọng chi tiêu theo danh mục. Số liệu chi tiết ở danh sách bên dưới.">
                  <ResponsiveContainer width="100%" height={240}>
                    <PieChart><Pie data={categoryData} dataKey="amount" nameKey="name" innerRadius="48%" outerRadius="80%" paddingAngle={2} isAnimationActive={false}>{categoryData.map((entry, index) => <Cell key={entry.category_id ?? "none"} fill={COLORS[index % COLORS.length]} />)}</Pie><Tooltip formatter={(value) => formatVnd(value)} /></PieChart>
                  </ResponsiveContainer>
                </div>
                <ul className="chart-legend">{categoryData.map((category, index) => <li key={category.category_id ?? "none"}><span className="legend-dot" style={{ background: COLORS[index % COLORS.length] }} /> <span>{category.name}</span><b>{formatVnd(category.amount)}</b></li>)}</ul>
              </> : <p className="empty-state">Chưa có chi tiêu để vẽ biểu đồ.</p>}
            </section>
            <section className="card chart-panel">
              <h2>Theo tuần</h2>
              {weeklyData.length ? <>
                <div className="chart-canvas" role="img" aria-label="Biểu đồ chi tiêu từng tuần. Bảng số liệu bên dưới.">
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart data={weeklyData} margin={{ top: 12, right: 8, bottom: 4, left: 0 }}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" tick={{ fontSize: 12 }} /><YAxis tickFormatter={compactMoney} width={52} tick={{ fontSize: 12 }} /><Tooltip formatter={(value) => [formatVnd(value), "Chi tiêu"]} labelFormatter={(_, payload) => payload?.[0] ? `Tuần từ ${formatDate(payload[0].payload.week_start)}` : ""} /><Bar dataKey="amount" name="Chi tiêu" fill="#2563eb" radius={[6, 6, 0, 0]} isAnimationActive={false} /></BarChart>
                  </ResponsiveContainer>
                </div>
                <ul className="chart-legend">{weeklyData.map((week) => <li key={week.week_start}><span>Tuần từ {formatDate(week.week_start)}</span><b>{formatVnd(week.amount)}</b></li>)}</ul>
              </> : <p className="empty-state">Chưa có chi tiêu theo tuần.</p>}
            </section>
          </div>
          <section className="card">
            <h2>Theo thành viên</h2>
            {summary.by_member?.length ? <ul className="chart-legend">{summary.by_member.map((member) => <li key={member.user_id}><span>{member.display_name}</span><b>{formatVnd(member.amount)}</b></li>)}</ul> : <p className="empty-state">Chưa có giao dịch đã xác nhận.</p>}
          </section>
          <section className="card transaction-list">
            <h2>Giao dịch trong tháng</h2>
            <p className="muted">Bản nháp hóa đơn chưa được tính. <Link to="/receipts">Xem và xác nhận hóa đơn</Link>.</p>
            {transactions.length ? <div className="table-scroll"><table><thead><tr><th>Ngày</th><th>Khoản chi</th><th>Danh mục</th><th>Thành viên</th><th className="text-right">Số tiền</th></tr></thead><tbody>{transactions.map((transaction) => <tr key={transaction.id}><td>{formatDate(transaction.occurred_on)}</td><td>{transaction.merchant || transaction.note || "Chi tiêu thủ công"}<small className="muted">{transaction.source === "OCR" ? "Từ hóa đơn" : "Nhập tay"}</small></td><td>{categoryName(transaction.category_id)}</td><td>{memberName(transaction.member_id ?? transaction.user_id)}</td><td className="text-right money">{formatVnd(transaction.total_amount)}</td></tr>)}</tbody></table></div> : <div className="empty-state"><p>Chưa có giao dịch đã xác nhận trong tháng này.</p><Link to="/transactions/new">Nhập khoản chi đầu tiên</Link></div>}
          </section>
          <section className="card budget-placeholder"><h2>Ngân sách</h2><p className="muted">Khu vực ngân sách sẽ được bổ sung trong giai đoạn tiếp theo.</p></section>
        </>
      )}
    </>
  );
}
