import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { localPeriod } from "../dashboardData";
import { formatVnd } from "../format";
import { checkBudget } from "../budgetForm";
import "../budgets.css";

export default function Budgets() {
  const [searchParams] = useSearchParams();
  const [period, setPeriod] = useState(() => /^(?!0000)\d{4}-(0[1-9]|1[0-2])$/.test(searchParams.get("period") || "") ? searchParams.get("period") : localPeriod());
  const [reload, setReload] = useState(0);
  const [result, setResult] = useState(null);
  const key = `${period}:${reload}`;
  useEffect(() => {
    const controller = new AbortController();
    const options = { signal: controller.signal };
    async function load() {
      const me = await api("/api/me", options);
      if (!me?.household) return { household: null };
      const [categoryResult, budgetResult, summary] = await Promise.all([
        api("/api/categories", options), api(`/api/budgets/${period}`, options), api(`/api/dashboard?period=${period}`, options),
      ]);
      const categories = categoryResult?.categories;
      if (!Array.isArray(categories) || !budgetResult || !Object.hasOwn(budgetResult, "budget") || !Array.isArray(summary?.by_category)) throw new Error("Không đọc được dữ liệu ngân sách từ máy chủ.");
      const budget = budgetResult.budget === null ? null : checkBudget(budgetResult.budget, categories, period);
      return { household: me.household, categories, budget, summary };
    }
    load().then((data) => { if (!controller.signal.aborted) setResult({ key, data }); }).catch((error) => { if (!controller.signal.aborted) setResult({ key, error }); });
    return () => controller.abort();
  }, [period, key]);
  const loading = result?.key !== key;
  const data = !loading ? result?.data : null;
  const budget = data?.budget;
  const allocated = budget?.allocations.reduce((sum, line) => sum + line.amount, 0) ?? 0;
  return <>
    <div className="page-heading"><div><p className="eyebrow">Kế hoạch gia đình</p><h1>Ngân sách theo tháng</h1><p>Theo dõi ngân sách và chi tiêu theo danh mục.</p></div><Link to="/dashboard">Xem thống kê</Link></div>
    <div className="card dashboard-filters"><label className="field" htmlFor="budget-period">Tháng ngân sách<input id="budget-period" type="month" min="0001-01" max="9998-12" value={period} onChange={(event) => { if (/^(?!0000)\d{4}-(0[1-9]|1[0-2])$/.test(event.target.value)) setPeriod(event.target.value); }} /></label><button type="button" className="button-secondary" disabled={loading} onClick={() => setReload((value) => value + 1)}>Tải lại dữ liệu</button></div>
    {loading ? <p role="status">Đang tải ngân sách…</p> : result.error ? <section className="card"><p className="error" role="alert">{result.error.message}</p><button type="button" onClick={() => setReload((value) => value + 1)}>Thử lại</button></section> : !data.household ? <p>Bạn cần <Link to="/">tạo hoặc tham gia một hộ</Link> để xem ngân sách.</p> : !budget ? <section className="card empty-state"><h2>Tháng này chưa có ngân sách</h2></section> : <>
      <p className="budget-role"><span className="status-badge">{data.household.role === "owner" ? "Chủ hộ" : "Thành viên · Chỉ xem"}</span>{data.household.name}</p>
      <div className="metrics-grid budget-metrics">
        <section className="card metric"><h2>Thu nhập dự kiến</h2><strong>{formatVnd(budget.income_estimate)}</strong></section>
        <section className="card metric"><h2>Ngân sách chi tiêu</h2><strong>{formatVnd(allocated)}</strong></section>
        <section className="card metric budget-savings"><h2>Mục tiêu tiết kiệm</h2><strong>{formatVnd(budget.savings_goal)}</strong></section>
      </div>
      <section className="card"><h2>Chi tiêu so với ngân sách</h2><div className="allocation-grid">{data.categories.map((category) => {
        const amount = budget.allocations.find((line) => line.category_id === category.id)?.amount ?? 0;
        const spent = data.summary.by_category.find((line) => line.category_id === category.id)?.amount ?? 0;
        return <div className="allocation-item" key={category.id}><h3>{category.name}</h3><p>{formatVnd(spent)} / {formatVnd(amount)}</p><progress aria-label={`Mức sử dụng ngân sách ${category.name}`} max={Math.max(amount, 1)} value={Math.min(spent, Math.max(amount, 1))} /></div>;
      })}</div></section>
    </>}
  </>;
}
