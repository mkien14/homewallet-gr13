import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { formatVnd, parseVnd } from "../format";
import { buildRecurringBody, createNeedsReconciliation, matchingRecurringBills, recurringError, recurringFields, validRecurringBill } from "../recurringForm";
import "../recurring.css";

function ErrorNotice({ error }) {
  if (!error) return null;
  return <div className="notice error" role="alert"><p>{error.message}</p>{error.requestId && <p>Mã yêu cầu: <code>{error.requestId}</code></p>}</div>;
}

export default function RecurringBills() {
  const [setup, setSetup] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [reload, setReload] = useState(0);
  const [editor, setEditor] = useState(null);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  const [forbidden, setForbidden] = useState(false);
  const [filter, setFilter] = useState("all");
  const [uncertainCreate, setUncertainCreate] = useState(null);
  const pending = useRef(false);
  const canEdit = setup?.household?.role === "owner" && !forbidden;

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      const me = await api("/api/me", { signal: controller.signal });
      if (!me || !Object.hasOwn(me, "household")) throw new Error("Không đọc được thông tin hộ gia đình.");
      if (!me.household) return { household: null, categories: [], items: [] };
      const [categoryResult, result] = await Promise.all([
        api("/api/categories", { signal: controller.signal }),
        api("/api/recurring-bills", { signal: controller.signal }),
      ]);
      if (!Array.isArray(categoryResult?.categories) || !Array.isArray(result?.items) ||
          result.items.some((bill) => !validRecurringBill(bill, categoryResult.categories))) {
        throw new Error("Máy chủ trả về danh sách hóa đơn không hợp lệ. Hãy thử tải lại.");
      }
      return { household: me.household, categories: categoryResult.categories, items: result.items };
    }
    load().then((data) => {
      if (!controller.signal.aborted) { setSetup(data); setLoadError(null); }
    }).catch((err) => {
      if (!controller.signal.aborted) setLoadError(recurringError(err));
    });
    return () => controller.abort();
  }, [reload]);

  function openEditor(bill) {
    if (!canEdit || pending.current) return;
    setEditor({ id: bill?.id ?? null, fields: recurringFields(bill) });
    setUncertainCreate(null);
    setError(null);
    setSuccess("");
  }

  function updateField(name, value) {
    setEditor((current) => ({ ...current, fields: { ...current.fields, [name]: value } }));
    setError(null);
  }

  async function save(event) {
    event.preventDefault();
    if (!canEdit || pending.current || uncertainCreate) return;
    setError(null);
    setSuccess("");
    let body;
    try { body = buildRecurringBody(editor.fields, setup.categories); }
    catch (err) { setError(recurringError(err)); return; }
    pending.current = true;
    setBusy(true);
    try {
      const result = await api(editor.id ? `/api/recurring-bills/${editor.id}` : "/api/recurring-bills", {
        method: editor.id ? "PATCH" : "POST", body,
      });
      if (!validRecurringBill(result?.bill, setup.categories)) throw new Error("Chưa xác nhận được kết quả lưu. Nội dung bạn nhập vẫn được giữ lại.");
      setSetup((current) => ({ ...current, items: [...current.items.filter((item) => item.id !== result.bill.id), result.bill] }));
      setEditor(null);
      setSuccess(editor.id ? "Đã cập nhật hóa đơn định kỳ." : "Đã thêm hóa đơn định kỳ.");
    } catch (err) {
      if (err.status === 403) setForbidden(true);
      if (!editor.id && createNeedsReconciliation(err)) {
        setUncertainCreate({ body, previousIds: setup.items.map((bill) => bill.id), checked: false, matches: [] });
      }
      setError(recurringError(err));
    } finally { pending.current = false; setBusy(false); }
  }

  async function toggle(bill) {
    if (!canEdit || pending.current) return;
    pending.current = true;
    setBusy(true);
    setError(null);
    setSuccess("");
    try {
      const result = await api(`/api/recurring-bills/${bill.id}`, { method: "PATCH", body: { active: !bill.active } });
      if (!validRecurringBill(result?.bill, setup.categories)) throw new Error("Chưa xác nhận được trạng thái hóa đơn. Hãy tải lại trang để kiểm tra.");
      setSetup((current) => ({ ...current, items: current.items.map((item) => item.id === bill.id ? result.bill : item) }));
      setSuccess(result.bill.active ? `Đã bật lại “${bill.name}”.` : `Đã tạm dừng “${bill.name}”.`);
    } catch (err) {
      if (err.status === 403) setForbidden(true);
      setError(recurringError(err));
    } finally { pending.current = false; setBusy(false); }
  }

  async function reconcileCreate() {
    if (pending.current || !uncertainCreate) return;
    pending.current = true;
    setBusy(true);
    setError(null);
    try {
      const result = await api("/api/recurring-bills");
      if (!Array.isArray(result?.items) || result.items.some((bill) => !validRecurringBill(bill, setup.categories))) {
        throw new Error("Không đọc được danh sách mới nhất. Nội dung đang nhập vẫn được giữ.");
      }
      setSetup((current) => ({ ...current, items: result.items }));
      setUncertainCreate((current) => ({ ...current, checked: true, matches: matchingRecurringBills(result.items, current.body, current.previousIds) }));
    } catch (err) {
      if (err.status === 403) setForbidden(true);
      setError(recurringError(err));
    } finally { pending.current = false; setBusy(false); }
  }

  const heading = <div className="page-heading"><div><p className="eyebrow">Kế hoạch gia đình</p><h1>Hóa đơn định kỳ</h1><p>Ghi nhớ những khoản cần thanh toán mỗi tháng.</p></div>{canEdit && !editor && <button type="button" onClick={() => openEditor()} disabled={busy}>+ Thêm hóa đơn</button>}</div>;
  if (loadError) return <>{heading}<section className="card"><ErrorNotice error={loadError} /><button type="button" onClick={() => { setLoadError(null); setReload((value) => value + 1); }}>Thử lại</button></section></>;
  if (!setup) return <>{heading}<p role="status">Đang tải hóa đơn định kỳ…</p></>;
  if (!setup.household) return <>{heading}<section className="card"><p>Bạn cần <Link to="/">tạo hoặc tham gia một hộ</Link> để quản lý hóa đơn định kỳ.</p></section></>;

  const activeBills = setup.items.filter((item) => item.active);
  const pricedBills = activeBills.filter((bill) => bill.expected_amount !== null);
  const unknownAmountCount = activeBills.length - pricedBills.length;
  const shown = setup.items.filter((item) => filter === "all" || item.active === (filter === "active"))
    .sort((a, b) => a.due_day - b.due_day || a.id - b.id);
  const categoryName = (id) => id === null ? "Chưa phân loại" : setup.categories.find((category) => category.id === id)?.name || "Danh mục đã ngừng sử dụng";

  return <>
    {heading}
    {!canEdit && <p className="notice">Bạn đang ở chế độ chỉ xem. Chủ hộ có thể quản lý các hóa đơn định kỳ.</p>}
    <div className="metrics-grid recurring-metrics">
      <section className="card metric"><h2>Đang hoạt động</h2><strong>{activeBills.length}<span className="recurring-metric-unit"> hóa đơn</span></strong><p>{setup.items.length - activeBills.length} hóa đơn đang tạm dừng</p></section>
      <section className="card metric"><h2>Dự kiến mỗi tháng</h2><strong>{activeBills.length > 0 && pricedBills.length === 0 ? "Chưa có số tiền" : formatVnd(pricedBills.reduce((sum, bill) => sum + bill.expected_amount, 0))}</strong><p>{unknownAmountCount ? `Chưa gồm ${unknownAmountCount} hóa đơn chưa nhập số tiền` : "Chỉ tính các hóa đơn đang hoạt động"}</p></section>
    </div>
    <p className="muted recurring-job-note">Chưa có xác nhận gửi lời nhắc. Danh sách này giúp bạn lập kế hoạch; khoản dự kiến chưa được tính vào chi tiêu.</p>
    {success && <p className="success" role="status">{success}</p>}
    {!editor && <ErrorNotice error={error} />}
    <div className={`recurring-layout${editor ? " has-editor" : ""}`}>
      {editor && <section className="card recurring-editor" aria-labelledby="recurring-form-title">
        <h2 id="recurring-form-title">{editor.id ? "Sửa hóa đơn" : "Thêm hóa đơn"}</h2>
        <form onSubmit={save}>
          <fieldset disabled={busy || !canEdit || Boolean(uncertainCreate)} className="recurring-fields">
            <label className="field" htmlFor="bill-name">Tên hóa đơn<input id="bill-name" value={editor.fields.name} onChange={(e) => updateField("name", e.target.value)} maxLength={100} required placeholder="Ví dụ: Tiền điện" /></label>
            <label className="field" htmlFor="bill-category">Danh mục (không bắt buộc)<select id="bill-category" value={editor.fields.categoryId} onChange={(e) => updateField("categoryId", e.target.value)}><option value="">Chưa phân loại</option>{setup.categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>
            <label className="field" htmlFor="bill-amount">Số tiền dự kiến (đồng, không bắt buộc)<input id="bill-amount" type="text" inputMode="numeric" value={editor.fields.amount} onChange={(e) => updateField("amount", e.target.value)} placeholder="Để trống nếu chưa biết" aria-describedby="bill-amount-preview" /><small id="bill-amount-preview">{!editor.fields.amount.trim() ? "Chưa có số tiền dự kiến." : parseVnd(editor.fields.amount) === null ? "Nhập số nguyên đồng từ 0 trở lên hoặc để trống." : formatVnd(parseVnd(editor.fields.amount))}</small></label>
            <div className="form-grid">
              <label className="field" htmlFor="bill-due-day">Ngày đến hạn<input id="bill-due-day" type="number" inputMode="numeric" min="1" max="31" step="1" value={editor.fields.dueDay} onChange={(e) => updateField("dueDay", e.target.value)} required /><small>Ngày trong tháng, từ 1 đến 31.</small></label>
              <label className="field" htmlFor="bill-remind">Nhắc trước (ngày)<input id="bill-remind" type="number" inputMode="numeric" min="0" max="30" step="1" value={editor.fields.remindDays} onChange={(e) => updateField("remindDays", e.target.value)} required /><small>0 là nhắc đúng ngày đến hạn.</small></label>
            </div>
            {Number(editor.fields.dueDay) > 28 && <p className="muted">Với ngày 29–31, lịch nhắc trong tháng ngắn hơn cần được xác nhận khi dịch vụ nhắc được triển khai.</p>}
            <label className="recurring-checkbox" htmlFor="bill-active"><input id="bill-active" type="checkbox" checked={editor.fields.active} onChange={(e) => updateField("active", e.target.checked)} />Đang hoạt động</label>
          </fieldset>
          {!setup.categories.length && <p className="notice">Hộ chưa có danh mục. Bạn vẫn có thể lưu hóa đơn ở trạng thái Chưa phân loại.</p>}
          <ErrorNotice error={error} />
          {uncertainCreate && <div className="notice" role="status"><p>Chưa xác nhận được lần tạo hóa đơn vừa rồi. Nội dung đang nhập được giữ; cần kiểm tra danh sách trước khi gửi lại để tránh tạo trùng.</p><button type="button" className="button-secondary" disabled={busy} onClick={reconcileCreate}>{busy ? "Đang kiểm tra…" : "Kiểm tra danh sách đã lưu"}</button>{uncertainCreate.checked && <><p>{uncertainCreate.matches.length ? `Đã tìm thấy ${uncertainCreate.matches.length} hóa đơn mới khớp nội dung trong danh sách.` : "Chưa thấy hóa đơn mới khớp nội dung. Nếu bạn chọn gửi lại, máy chủ vẫn có thể hoàn tất yêu cầu trước đó."}</p>{uncertainCreate.matches.length ? <button type="button" disabled={busy} onClick={() => { setEditor(null); setUncertainCreate(null); setError(null); setSuccess("Đã giữ hóa đơn tìm thấy trong danh sách; không gửi thêm yêu cầu tạo."); }}>Dùng hóa đơn đã tìm thấy</button> : <button type="button" disabled={busy || !canEdit} onClick={() => { setUncertainCreate(null); setError(null); }}>Cho phép gửi lại sau khi kiểm tra</button>}</>}</div>}
          <div className="actions"><button type="submit" disabled={busy || !canEdit || Boolean(uncertainCreate)}>{busy ? "Đang xử lý…" : "Lưu hóa đơn"}</button><button type="button" className="button-secondary" disabled={busy} onClick={() => { setEditor(null); setUncertainCreate(null); setError(null); }}>Hủy</button></div>
        </form>
      </section>}
      <section className="card recurring-list-panel" aria-labelledby="recurring-list-title">
        <div className="recurring-list-heading"><h2 id="recurring-list-title">Danh sách hóa đơn</h2><label className="field" htmlFor="bill-filter"><span className="muted">Hiển thị</span><select id="bill-filter" value={filter} onChange={(e) => setFilter(e.target.value)}><option value="all">Tất cả</option><option value="active">Đang hoạt động</option><option value="paused">Đang tạm dừng</option></select></label></div>
        {shown.length ? <ul className="recurring-list">{shown.map((bill) => <li key={bill.id} className={`recurring-item${bill.active ? "" : " is-paused"}`}>
          <div className="recurring-day" aria-label={`Đến hạn ngày ${bill.due_day} hằng tháng`}><span>Ngày</span><strong>{bill.due_day}</strong></div>
          <div className="recurring-item-body"><div className="recurring-item-heading"><h3>{bill.name}</h3><span className={`status-badge ${bill.active ? "status-confirmed" : ""}`}>{bill.active ? "Đang hoạt động" : "Tạm dừng"}</span></div><p className="muted">{categoryName(bill.category_id)} · {bill.remind_days_before === 0 ? "Nhắc đúng ngày" : `Nhắc trước ${bill.remind_days_before} ngày`}</p><strong className="recurring-amount money">{bill.expected_amount === null ? "Chưa có số tiền dự kiến" : <>{formatVnd(bill.expected_amount)}<small> / tháng</small></>}</strong>{canEdit && <div className="actions recurring-item-actions"><button type="button" className="button-secondary" disabled={busy || Boolean(editor)} onClick={() => openEditor(bill)} aria-label={`Sửa ${bill.name}`}>Sửa</button><button type="button" className="button-secondary" disabled={busy || Boolean(editor)} onClick={() => toggle(bill)} aria-label={`${bill.active ? "Tạm dừng" : "Bật lại"} ${bill.name}`}>{bill.active ? "Tạm dừng" : "Bật lại"}</button></div>}</div>
        </li>)}</ul> : <div className="empty-state"><h3>{setup.items.length ? "Không có hóa đơn trong bộ lọc này" : "Chưa có hóa đơn định kỳ"}</h3><p>{setup.items.length ? "Chọn bộ lọc khác để xem các hóa đơn còn lại." : "Thêm tiền nhà, điện nước hoặc các khoản thanh toán hằng tháng của gia đình."}</p>{canEdit && !editor && !setup.items.length && <button type="button" onClick={() => openEditor()}>Thêm hóa đơn đầu tiên</button>}</div>}
      </section>
    </div>
  </>;
}
