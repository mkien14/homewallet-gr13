import { useEffect, useRef, useState } from "react";
import { t as translate } from "../preferences";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { localPeriod } from "../dashboardData";
import { formatVnd, parseVnd } from "../format";
import { t } from "../preferences";
import { budgetToForm, buildBudgetBody, checkBudget } from "../budgetForm";
import "../budgets.css";

function failureMessage(error) {
  if (error.status === 404 && error.code === "HTTP_404") return "Máy chủ đang kết nối không có đường dẫn API ngân sách. Kiểm tra địa chỉ backend và khởi động lại backend sau khi cập nhật mã.";
  if (error.status === 404 && error.code === "NOT_FOUND") return "Máy chủ không tìm thấy dữ liệu hoặc đường dẫn ngân sách được yêu cầu. Hãy kiểm tra hộ hiện tại và backend đang kết nối.";
  if (error.status === 409) return `${error.message || "Chưa lưu được do xung đột dữ liệu."} Nội dung bạn nhập vẫn được giữ lại.`;
  return error.message || "Chưa thực hiện được yêu cầu. Hãy thử lại.";
}

function BudgetWorkspace({ period, data, onReload, onBusyChange, onDirtyChange }) {
  const { household, categories, summary } = data;
  const [saved, setSaved] = useState(data.budget);
  const [form, setForm] = useState(() => budgetToForm(data.budget, categories));
  const [suggestion, setSuggestion] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState("");
  const [forbidden, setForbidden] = useState(false);
  const [draftSource, setDraftSource] = useState("");
  const submitting = useRef(false);
  const owner = household.role === "owner" && !forbidden;
  const allocated = saved?.allocations.reduce((sum, line) => sum + line.amount, 0) ?? 0;
  const draftAllocated = categories.reduce((sum, category) => sum + (parseVnd(form.allocations[category.id]) ?? 0), 0);
  const remaining = (parseVnd(form.income) ?? 0) - (parseVnd(form.savings) ?? 0) - draftAllocated;
  const dirty = Boolean(draftSource) || JSON.stringify(form) !== JSON.stringify(budgetToForm(saved, categories));
  useEffect(() => { onDirtyChange(dirty); }, [dirty, onDirtyChange]);

  function update(patch) {
    setForm((previous) => ({ ...previous, ...patch }));
    if (Object.hasOwn(patch, "income") || Object.hasOwn(patch, "savings")) setSuggestion(null);
    setSuccess("");
  }

  async function run(kind, action) {
    if (submitting.current || !owner) return;
    submitting.current = true;
    onBusyChange(true);
    setBusy(kind);
    setError(null);
    setSuccess("");
    try { await action(); }
    catch (err) {
      setError({ status: err.status, message: failureMessage(err), requestId: err.requestId });
      if (err.status === 403) setForbidden(true);
    } finally { submitting.current = false; setBusy(""); onBusyChange(false); }
  }

  function save(event) {
    event.preventDefault();
    return run("save", async () => {
      const body = buildBudgetBody(form, categories);
      const result = await api(`/api/budgets/${period}`, { method: "PUT", body });
      const budget = checkBudget(result?.budget, categories, period);
      setSaved(budget);
      setForm(budgetToForm(budget, categories));
      setSuggestion(null);
      setDraftSource("");
      setSuccess("Đã lưu ngân sách. Số liệu tổng quan đã được cập nhật.");
    });
  }

  function suggest() {
    return run("suggest", async () => {
      const income_estimate = parseVnd(form.income);
      const savings_goal = parseVnd(form.savings);
      if (income_estimate === null || savings_goal === null || savings_goal > income_estimate) {
        throw new Error("Nhập thu nhập và tiết kiệm hợp lệ trước khi lấy gợi ý.");
      }
      setSuggestion(null);
      const result = await api(`/api/budgets/${period}/suggest`, {
        method: "POST",
        body: { income_estimate, savings_goal },
      });
      const draft = checkBudget(result?.suggestion, categories, period, { suggestion: true });
      setSuggestion(draft);
    });
  }

  return <>
    <div className="budget-role"><span className="status-badge">{owner ? t("Chủ hộ · Có thể chỉnh sửa") : t("Thành viên · Chỉ xem")}</span><span className="muted">{household.name}</span></div>
    {!owner && <p className="notice">{translate("Bạn đang xem ngân sách chung của hộ. Chủ hộ có thể chỉnh sửa và lưu phân bổ.")}</p>}
    <div className={`budget-workspace${owner && !saved ? " budget-setup" : ""}`}>
    {saved ? <>
      <div className="metrics-grid budget-metrics">
        <section className="card metric"><h2>{translate("Thu nhập dự kiến")}</h2><strong>{formatVnd(saved.income_estimate)}</strong><p>{translate("Cơ sở phân bổ trong tháng")}</p></section>
        <section className="card metric"><h2>{translate("Ngân sách chi tiêu")}</h2><strong>{formatVnd(allocated)}</strong><p>{categories.length} {t("danh mục trong hộ")}</p></section>
        <section className="card metric budget-savings"><h2>{translate("Mục tiêu tiết kiệm")}</h2><strong>{formatVnd(saved.savings_goal)}</strong><p>{t("Còn") } {formatVnd(saved.income_estimate - allocated - saved.savings_goal)} {t("chưa phân bổ")}</p></section>
      </div>
      <section className="card">
        <div className="budget-section-heading"><div><h2>{translate("Chi tiêu so với ngân sách")}</h2><p className="muted">{translate("Chỉ tính giao dịch đã xác nhận trong kỳ.")}</p></div><Link to="/dashboard">{translate("Xem thống kê")}</Link></div>
        <div className="allocation-grid">{categories.map((category) => {
          const amount = saved.allocations.find((line) => line.category_id === category.id)?.amount ?? 0;
          const spent = summary.by_category?.find((line) => line.category_id === category.id)?.amount ?? 0;
          const over = spent > amount;
          return <div className={`allocation-item${over ? " allocation-over" : ""}`} key={category.id}>
            <div className="allocation-top"><h3>{category.name}</h3><span>{amount ? `${Math.round(spent / amount * 100)}%` : spent ? t("Chưa phân bổ") : "0%"}</span></div>
            <p><b>{formatVnd(spent)}</b><span className="muted"> / {formatVnd(amount)}</span></p>
            <progress aria-label={`Mức sử dụng ngân sách ${category.name}`} max={Math.max(amount, 1)} value={Math.min(spent, Math.max(amount, 1))} />
            <small>{over ? `${t("Vượt")} ${formatVnd(spent - amount)}` : `${t("Còn")} ${formatVnd(amount - spent)}`}</small>
          </div>;
        })}</div>
      </section>
    </> : <section className="card empty-state"><h2>{translate("Tháng này chưa có ngân sách")}</h2><p>{owner ? t("Bắt đầu từ thu nhập dự kiến, đặt mục tiêu tiết kiệm rồi phân bổ cho từng danh mục bên dưới.") : t("Chủ hộ chưa tạo ngân sách cho kỳ này.")}</p></section>}
    {owner && <form className="card budget-editor" onSubmit={save}>
      <div className="budget-section-heading"><div><p className="eyebrow">{translate("Kế hoạch của bạn")}</p><h2>{saved ? t("Điều chỉnh ngân sách") : t("Tạo ngân sách tháng này")}</h2></div><span className="status-badge">{!saved || dirty ? t("Bản nháp · Chưa lưu") : t("Khớp bản đã lưu")}</span></div>
      <fieldset disabled={Boolean(busy)} className="budget-fields">
        <div className="form-grid">
          <label className="field" htmlFor="budget-income">{translate("Thu nhập dự kiến (đồng)")}<input id="budget-income" inputMode="numeric" value={form.income} onChange={(e) => update({ income: e.target.value })} placeholder={translate("Ví dụ: 12.000.000")} required /><small>{formatVnd(parseVnd(form.income) ?? 0)}</small></label>
          <label className="field" htmlFor="budget-savings">{translate("Mục tiêu tiết kiệm (đồng)")}<input id="budget-savings" inputMode="numeric" value={form.savings} onChange={(e) => update({ savings: e.target.value })} required /><small>{formatVnd(parseVnd(form.savings) ?? 0)}</small></label>
        </div>
        <div className="suggestion-toolbar"><div><b>{translate("Cần một điểm bắt đầu?")}</b><p className="muted">{translate("Lấy gợi ý phân bổ rồi chỉnh theo nhu cầu gia đình.")}</p></div><button type="button" className="button-secondary" onClick={suggest} disabled={Boolean(busy)}>{busy === "suggest" ? t("Đang lấy gợi ý…") : t("Gợi ý phân bổ")}</button></div>
        {suggestion && <section className="suggestion-preview" aria-label={translate("Bản nháp gợi ý")} aria-live="polite">
          <div className="budget-section-heading"><h3>{translate("Gợi ý để bạn cân nhắc")}</h3><span className="status-badge">{suggestion.source === "LLM" ? t("Gợi ý AI") : t("Theo quy tắc / dự phòng")}</span></div>
          <p>{suggestion.source === "RULE" ? t("Gợi ý dựa trên chi tiêu đã xác nhận của ba tháng trước. Phương án theo quy tắc cũng được dùng khi AI không trả được gợi ý hợp lệ.") : t("Gợi ý AI đã được máy chủ kiểm tra theo quy tắc ngân sách.")} {t("Bạn có thể điều chỉnh mọi khoản trước khi lưu.")}</p>
          {!suggestion.allocations.length && <p className="muted">{translate("Chưa có khoản phân bổ được gợi ý. Bạn có thể tự nhập ngân sách theo danh mục bên dưới.")}</p>}
          <ul className="suggestion-lines">{suggestion.allocations.map((line) => <li key={line.category_id}><span>{line.name}</span><b>{formatVnd(line.amount)}</b></li>)}</ul>
          <button type="button" className="button-secondary" onClick={() => { setForm(budgetToForm(suggestion, categories)); setDraftSource(translate("Đã đưa gợi ý vào form. Bạn có thể chỉnh sửa rồi bấm Lưu ngân sách.")); setSuccess(""); }}>{translate("Dùng gợi ý trong bản nháp")}</button>
          <p className="muted">{translate("Gợi ý chưa được lưu vào ngân sách.")}</p>
        </section>}
        <h3>{translate("Phân bổ theo danh mục")}</h3>
        <div className="form-grid">{categories.map((category) => <label className="field" key={category.id} htmlFor={`budget-category-${category.id}`}>{category.name} ({t("đồng")})<input id={`budget-category-${category.id}`} inputMode="numeric" value={form.allocations[category.id]} onChange={(e) => update({ allocations: { ...form.allocations, [category.id]: e.target.value } })} required /><small>{formatVnd(parseVnd(form.allocations[category.id]) ?? 0)}</small></label>)}</div>
        {!categories.length && <p className="notice">{translate("Hộ chưa có danh mục. Bạn vẫn có thể đặt mục tiêu tiết kiệm.")}</p>}
        <div className={`budget-balance${remaining < 0 ? " budget-balance-over" : ""}`} aria-live="polite"><span>{remaining < 0 ? t("Đang vượt thu nhập") : t("Còn có thể phân bổ")}</span><strong>{formatVnd(Math.abs(remaining))}</strong></div>
        {draftSource && <p className="notice" role="status">{t(draftSource)}</p>}
        <div className="actions"><button type="submit">{busy === "save" ? translate("Đang lưu…") : translate("Lưu ngân sách")}</button><button type="button" className="button-secondary" onClick={() => { setForm(budgetToForm(saved, categories)); setSuggestion(null); setDraftSource(""); setError(null); setSuccess(""); }}>{translate("Khôi phục form")}</button></div>
      </fieldset>
      <p className="muted">{translate("Tổng chi tiêu và tiết kiệm không vượt thu nhập dự kiến. Chỉ nút “Lưu ngân sách” mới ghi thay đổi.")}</p>
    </form>}
    </div>
    {error && <section className="card" role="alert"><p className="error">{t(error.message)}</p>{error.requestId && <p>{t("Mã yêu cầu:")} <code>{error.requestId}</code></p>}{error.status === 403 && <button type="button" onClick={onReload}>{t("Tải lại quyền truy cập")}</button>}</section>}
    {success && <p className="success" role="status">{t(success)}</p>}
  </>;
}

export default function Budgets() {
  const [searchParams] = useSearchParams();
  const [period, setPeriod] = useState(() => /^(?!0000)\d{4}-(0[1-9]|1[0-2])$/.test(searchParams.get("period") || "") ? searchParams.get("period") : localPeriod());
  const [reload, setReload] = useState(0);
  const [workspaceBusy, setWorkspaceBusy] = useState(false);
  const [workspaceDirty, setWorkspaceDirty] = useState(false);
  const [result, setResult] = useState(null);
  const key = `${period}:${reload}`;
  useEffect(() => {
    const controller = new AbortController();
    const options = { signal: controller.signal };
    async function load() {
      const me = await api("/api/me", options);
      if (!me?.household) return { household: null };
      const [categoryResult, budgetResult, summary] = await Promise.all([api("/api/categories", options), api(`/api/budgets/${period}`, options), api(`/api/dashboard?period=${period}`, options)]);
      const categories = categoryResult?.categories;
      if (!Array.isArray(categories) || categories.some((item) => !item || !Number.isSafeInteger(item.id) || item.id <= 0 || typeof item.name !== "string") || !budgetResult || !Object.hasOwn(budgetResult, "budget") || !Array.isArray(summary?.by_category)) throw new Error("Không đọc được dữ liệu ngân sách hợp lệ từ máy chủ.");
      const budget = budgetResult.budget === null ? null : checkBudget(budgetResult.budget, categories, period);
      return { household: me.household, categories, budget, summary };
    }
    load().then((data) => { if (!controller.signal.aborted) setResult({ key, data }); }).catch((error) => { if (!controller.signal.aborted) setResult({ key, error }); });
    return () => controller.abort();
  }, [period, key]);
  const loading = result?.key !== key;
  return <>
    <div className="page-heading"><div><p className="eyebrow">{translate("Kế hoạch gia đình")}</p><h1>{translate("Ngân sách theo tháng")}</h1><p>{translate("Chủ động chia khoản chi, dành chỗ cho những mục tiêu.")}</p></div><Link className="button button-secondary" to="/dashboard">{translate("Xem thống kê")}</Link></div>
      <div className="card dashboard-filters"><label className="field" htmlFor="budget-period">{translate("Tháng ngân sách")}<input id="budget-period" type="month" min="0001-01" max="9998-12" value={period} disabled={workspaceBusy} onChange={(e) => { if (/^(?!0000)\d{4}-(0[1-9]|1[0-2])$/.test(e.target.value) && (!workspaceDirty || window.confirm(t("Chuyển tháng sẽ đóng bản nháp đang mở. Tiếp tục?")))) setPeriod(e.target.value); }} /></label><button type="button" className="button-secondary" disabled={loading || workspaceBusy} onClick={() => { if (!workspaceDirty || window.confirm(t("Tải lại dữ liệu sẽ đóng bản nháp đang mở. Tiếp tục?"))) setReload((value) => value + 1); }}>{translate("Tải lại dữ liệu")}</button></div>
    {loading ? <p role="status">{translate("Đang tải ngân sách…")}</p> : result.error ? <section className="card"><p className="error" role="alert">{failureMessage(result.error)}</p>{result.error.requestId && <p>{translate("Mã yêu cầu: ")}<code>{result.error.requestId}</code></p>}<button type="button" onClick={() => setReload((value) => value + 1)}>{translate("Thử lại")}</button></section> : !result.data.household ? <section className="card"><p>{translate("Bạn cần ")}<Link to="/">{translate("tạo hoặc tham gia một hộ")}</Link>{translate(" để xem ngân sách.")}</p></section> : <BudgetWorkspace key={key} period={period} data={result.data} onReload={() => setReload((value) => value + 1)} onBusyChange={setWorkspaceBusy} onDirtyChange={setWorkspaceDirty} />}
  </>;
}
