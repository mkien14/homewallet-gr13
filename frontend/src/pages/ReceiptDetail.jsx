import { useEffect, useRef, useState } from "react";
import { t as translate } from "../preferences";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { formatDate, formatVnd, parseVnd } from "../format";
import { STATUS_LABEL } from "../image";
import { t } from "../preferences";
import { createReceiptForm, receiptConfirmationBody, receiptDateLimit } from "../receiptForm";

const PENDING = new Set(["UPLOADING", "UPLOADED", "PROCESSING"]);
const WARNINGS = {
  AUTO_REVIEW_REQUIRED: "Chưa đủ điều kiện tự xác nhận. Hãy đối chiếu danh sách món và tổng tiền với hóa đơn gốc.",
  TOTAL_MISMATCH: "Tổng các dòng hàng khác tổng hóa đơn. Hãy đối chiếu ảnh gốc và sửa số tiền.",
  DUPLICATE_FILE: "Ảnh này có thể trùng với một hóa đơn đã tải lên trong hộ.",
  POSSIBLE_DUPLICATE: "Thông tin hóa đơn có thể trùng với một giao dịch đã có.",
  DATE_MISSING: "Không đọc được ngày đáng tin cậy. Hãy kiểm tra lại ngày trên ảnh gốc.",
  NOT_A_RECEIPT: "Ảnh có thể không phải hóa đơn. Hãy kiểm tra trước khi xác nhận.",
};

function ConfirmationForm({ receipt, categories, categoriesReady }) {
  const [form, setForm] = useState(() => createReceiptForm(receipt.draft));
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const submission = useRef(false);
  const navigate = useNavigate();
  const lineTotal = form.items.reduce((sum, item) => sum + (parseVnd(item.amount) ?? 0), 0);
  const total = parseVnd(form.total_amount);
  const mismatch = form.items.length > 0 && total !== null && lineTotal !== total;

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function updateItem(key, field, value) {
    setForm((current) => ({ ...current, items: current.items.map((item) => item.key === key ? { ...item, [field]: value } : item) }));
  }

  async function confirm(event) {
    event.preventDefault();
    if (submission.current) return;
    setError("");
    let body;
    try {
      body = receiptConfirmationBody(form, categories);
    } catch (err) {
      setError(t(err.message));
      return;
    }
    submission.current = true;
    setSubmitting(true);
    try {
      const result = await api(`/api/receipts/${receipt.id}/confirm`, {
        method: "POST",
        body,
      });
      if (!result?.transaction?.id || result.transaction.status !== "CONFIRMED") {
        throw new Error("Máy chủ chưa trả về xác nhận hợp lệ. Hãy tải lại hóa đơn để kiểm tra trạng thái.");
      }
      const confirmedDate = result.transaction.occurred_on || body.occurred_on;
      navigate(`/dashboard?period=${confirmedDate.slice(0, 7)}`, { replace: true, state: { receiptConfirmedId: receipt.id } });
    } catch (err) {
      setError(t(err.code === "ALREADY_CONFIRMED"
        ? "Hóa đơn đã được xác nhận. Hãy quay về danh sách để xem trạng thái mới nhất."
        : err.status === 409 ? "Bản nháp không còn ở trạng thái có thể xác nhận. Hãy tải lại thông tin hóa đơn." : err.message));
    } finally {
      submission.current = false;
      setSubmitting(false);
    }
  }

  function categoryOptions(selected) {
    const unknown = selected !== "" && !categories.some((category) => String(category.id) === selected);
    return <><option value="">{translate("Chưa phân loại")}</option>{unknown && <option value={selected} disabled>{translate("Danh mục không còn khả dụng")}</option>}{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</>;
  }

  return (
    <form className="receipt-form" onSubmit={confirm}>
      <fieldset disabled={submitting}>
        <legend>{translate("Kiểm tra thông tin hóa đơn")}</legend>
        {!categoriesReady && <p className="notice">{translate("Đang chờ danh mục. Nếu không tải được, hãy bấm Thử tải lại ở phía trên.")}</p>}
        {categoriesReady && categories.length === 0 && <p className="notice">{translate("Hộ chưa có danh mục. Bạn vẫn có thể xác nhận dưới dạng Chưa phân loại.")}</p>}
        <div className="form-grid">
          <label className="field" htmlFor="receipt-merchant">{translate("Cửa hàng")}<input id="receipt-merchant" maxLength={255} value={form.merchant} onChange={(event) => update("merchant", event.target.value)} /></label>
          <label className="field date-highlight" htmlFor="receipt-date">{translate("Ngày hóa đơn ")}<strong>{translate("Hãy kiểm tra ngày")}</strong><input id="receipt-date" type="date" required max={receiptDateLimit()} value={form.occurred_on} onChange={(event) => update("occurred_on", event.target.value)} /><span className="muted">{formatDate(form.occurred_on) || translate("Chọn ngày trên ảnh gốc")}</span></label>
          <label className="field" htmlFor="receipt-total">{translate("Tổng tiền (VND)")}<input id="receipt-total" type="text" inputMode="numeric" required value={form.total_amount} onChange={(event) => update("total_amount", event.target.value)} /><span className="muted">{total !== null ? formatVnd(total) : translate("Nhập số tiền nguyên đồng")}</span></label>
          <label className="field" htmlFor="receipt-category">{translate("Danh mục giao dịch")}<select id="receipt-category" value={form.category_id} onChange={(event) => update("category_id", event.target.value)}>{categoryOptions(form.category_id)}</select></label>
        </div>
        <h2>{translate("Dòng hàng")}</h2>
        <p className="muted">{translate("Thành tiền là tổng của từng dòng, đã gồm số lượng. Có thể để trống tên hoặc số lượng khi ảnh không cung cấp; chỉ tổng tiền là bắt buộc nếu không có dòng hàng.")}</p>
        <div className="line-items">
          {form.items.map((item, index) => (
            <div className="line-item" key={item.key}>
              <label className="field" htmlFor={`item-description-${item.key}`}>{translate("Món hàng ")}{index + 1}<input id={`item-description-${item.key}`} maxLength={255} value={item.description || ""} onChange={(event) => updateItem(item.key, "description", event.target.value)} /></label>
              <label className="field" htmlFor={`item-quantity-${item.key}`}>{translate("Số lượng")}<input id={`item-quantity-${item.key}`} type="number" min="0.001" max="9999999.999" step="any" value={item.quantity} onChange={(event) => updateItem(item.key, "quantity", event.target.value)} /></label>
              <label className="field" htmlFor={`item-amount-${item.key}`}>{translate("Thành tiền (VND)")}<input id={`item-amount-${item.key}`} inputMode="numeric" required value={item.amount} onChange={(event) => updateItem(item.key, "amount", event.target.value)} /></label>
              <label className="field" htmlFor={`item-category-${item.key}`}>{translate("Danh mục")}<select id={`item-category-${item.key}`} value={item.category_id} onChange={(event) => updateItem(item.key, "category_id", event.target.value)}>{categoryOptions(item.category_id)}</select></label>
              <button type="button" className="button-secondary" aria-label={`Xóa dòng hàng ${index + 1}`} onClick={() => setForm((current) => ({ ...current, items: current.items.filter((row) => row.key !== item.key) }))}>{translate("Xóa dòng")}</button>
            </div>
          ))}
        </div>
        <button type="button" className="button-secondary" onClick={() => setForm((current) => ({ ...current, items: [...current.items, { key: crypto.randomUUID(), description: "", quantity: "1", amount: "", category_id: current.category_id }] }))}>{translate("Thêm dòng hàng")}</button>
        <p>{translate("Tổng các dòng: ")}<strong>{formatVnd(lineTotal)}</strong></p>
        {mismatch && <p className="notice" role="status">{translate("Tổng dòng hàng đang lệch tổng hóa đơn ")}{formatVnd(Math.abs(lineTotal - total))}{translate(". Hãy đối chiếu trước khi xác nhận.")}</p>}
        {error && <p className="error" role="alert">{error}</p>}
        <div className="form-actions"><button type="submit" disabled={submitting || !categoriesReady}>{submitting ? translate("Đang xác nhận…") : translate("Xác nhận hóa đơn")}</button><Link to="/receipts">{translate("Quay về danh sách")}</Link></div>
      </fieldset>
    </form>
  );
}

function ReceiptContent({ id }) {
  const [receipt, setReceipt] = useState(null);
  const [categories, setCategories] = useState([]);
  const [categoriesReady, setCategoriesReady] = useState(false);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let timer;
    async function load() {
      try {
        const result = await api(`/api/receipts/${id}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setReceipt(result);
        setError("");
        if (PENDING.has(result.status)) {
          timer = window.setTimeout(load, 1000);
        } else if (["DRAFT_READY", "NEEDS_REVIEW"].includes(result.status) && result.draft) {
          try {
            const resultCategories = await api("/api/categories", { signal: controller.signal });
            if (!Array.isArray(resultCategories?.categories)) throw new Error("API chưa cung cấp danh mục theo hợp đồng tuần 2.");
            if (!controller.signal.aborted) {
              setCategories(resultCategories.categories);
              setCategoriesReady(true);
            }
          } catch (err) {
            if (!controller.signal.aborted) setError(t(`Không tải được danh mục: ${err.message}`));
          }
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          if (err.status === 404) setReceipt(null);
          setError(t(err.status === 404 ? "Không tìm thấy hóa đơn trong hộ của bạn, hoặc bạn không có quyền truy cập hóa đơn này." : err.message));
        }
      }
    }
    void load();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [id, reload]);

  const editable = receipt && ["DRAFT_READY", "NEEDS_REVIEW"].includes(receipt.status) && receipt.draft;
  const previewUrl = receipt?.image_url;
  const safePreview = previewUrl && /^(https?:\/\/|blob:|\/[^/])/.test(previewUrl) ? previewUrl : null;
  const isPdf = !receipt?.image_is_sample && (receipt?.content_type === "application/pdf" || /\.pdf(?:[?#]|$)/i.test(safePreview || ""));

  return (
    <>
      <div className="page-heading"><div><Link to="/receipts">{translate("← Danh sách hóa đơn")}</Link><h1>{translate("Hóa đơn #")}{id}</h1></div>{receipt && <span className={`status-badge status-${String(receipt.status).toLowerCase()}`}>{t(STATUS_LABEL[receipt.status] || receipt.status)}</span>}</div>
      {error && <div className="notice" role="alert"><p className="error">{error}</p><button type="button" className="button-secondary" onClick={() => setReload((value) => value + 1)}>{translate("Thử tải lại")}</button></div>}
      {!receipt && !error && <p role="status">{translate("Đang tải hóa đơn…")}</p>}
      {receipt && <>
        {receipt.warnings?.length > 0 && <div className="notice"><h2>{translate("Cần kiểm tra")}</h2><ul className="warning-list">{receipt.warnings.map((warning) => <li key={warning}>{t(WARNINGS[warning] || warning)}</li>)}</ul></div>}
        {PENDING.has(receipt.status) && <p className="notice" role="status">{translate("Hóa đơn đang được xử lý. Trang tự cập nhật mỗi 3 giây; bản nháp sẽ xuất hiện khi đọc xong.")}</p>}
        {receipt.status === "FAILED" && <div className="notice"><h2>{translate("Chưa đọc được hóa đơn")}</h2><p>{receipt.error_code ? `Mã lỗi: ${receipt.error_code}. ` : ""}{translate("Bạn có thể nhập thông tin giao dịch thủ công.")}</p><Link className="button-link" to="/transactions/new">{translate("Nhập tay")}</Link></div>}
        {receipt.status === "CONFIRMED" && <p className="notice success">{translate("Hóa đơn đã được xác nhận. ")}<Link to="/dashboard">Xem dashboard</Link></p>}
        <div className="receipt-layout">
          <section className="card receipt-preview" aria-label={translate("Ảnh hóa đơn gốc")}>
            <h2>{translate("Hóa đơn gốc")}</h2>
            {receipt.image_is_sample && <p className="notice">{translate("Ảnh minh họa cho dữ liệu giả. Kết quả OCR trong chế độ này là dữ liệu mẫu.")}</p>}
            {safePreview ? <>{isPdf ? <p>{translate("Tệp PDF: mở bản gốc để kiểm tra các trang.")}</p> : <img src={safePreview} alt={`Ảnh gốc của hóa đơn ${id}`} onError={(event) => { event.currentTarget.alt = translate("Ảnh không tải được. Liên kết có thể đã hết hạn; hãy làm mới ảnh."); }} />}<p><a href={safePreview} target="_blank" rel="noopener noreferrer">{translate("Mở tệp gốc trong tab mới")}</a></p><button type="button" className="button-secondary" onClick={() => setReload((value) => value + 1)}>{translate("Làm mới liên kết ảnh")}</button><p className="muted">{translate("Liên kết ảnh có thời hạn. Làm mới nếu không mở được.")}</p></> : <p className="muted">{translate("Ảnh gốc chưa sẵn sàng. API cần cung cấp liên kết xem tệp khi xử lý xong.")}</p>}
          </section>
          <section className="card">
            {receipt.draft?.note && <p><strong>{translate("Ghi chú trên hóa đơn:")}</strong> {receipt.draft.note}</p>}
            {receipt.status === "CONFIRMED" && receipt.draft?.items?.length > 0 && <>
              <h2>{translate("Các khoản đã chi")}</h2>
              <ul>{receipt.draft.items.map((item, index) => <li key={index}>
                {item.description || translate("Mặt hàng")}{translate(" · Số lượng: ")}{item.quantity ?? "—"} · {formatVnd(item.amount)}
              </li>)}</ul>
            </>}
            {editable ? <ConfirmationForm receipt={receipt} categories={categories} categoriesReady={categoriesReady} /> : <><h2>{translate("Thông tin hóa đơn")}</h2><p>{receipt.merchant || receipt.draft?.merchant || translate("Chưa có thông tin cửa hàng")}</p><p>{receipt.occurred_on || receipt.draft?.occurred_on ? formatDate(receipt.occurred_on || receipt.draft.occurred_on) : translate("Chưa xác định ngày")}</p>{(receipt.total_amount ?? receipt.draft?.total_amount) != null && <p><strong>{formatVnd(receipt.total_amount ?? receipt.draft.total_amount)}</strong></p>}{["DRAFT_READY", "NEEDS_REVIEW"].includes(receipt.status) && !receipt.draft && <p className="error">{translate("Backend chưa cung cấp bản nháp để xác nhận.")}</p>}</>}
          </section>
        </div>
      </>}
    </>
  );
}

export default function ReceiptDetail() {
  const { id } = useParams();
  return <ReceiptContent key={id} id={id} />;
}
