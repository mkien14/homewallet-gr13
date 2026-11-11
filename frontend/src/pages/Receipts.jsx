import { useEffect, useRef, useState } from "react";
import { t as translate } from "../preferences";
import { Link, useLocation } from "react-router-dom";
import { api } from "../api";
import { formatDate, formatVnd } from "../format";
import { t } from "../preferences";
import { STATUS_LABEL } from "../image";

const PENDING = new Set(["UPLOADING", "UPLOADED", "PROCESSING"]);
const PAGE_SIZE = 50;

function DeleteReceiptDialog({ receipt, deleting, error, onCancel, onConfirm }) {
  const dialogRef = useRef(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    dialog.showModal();
    return () => { if (dialog.open) dialog.close(); };
  }, []);

  return <dialog ref={dialogRef} className="confirm-dialog" aria-labelledby="delete-receipt-title" aria-describedby="delete-receipt-description" onCancel={(event) => { event.preventDefault(); if (!deleting) onCancel(); }}>
    <div className="confirm-dialog-icon" aria-hidden="true">!</div>
    <h2 id="delete-receipt-title">{t("Xóa hóa đơn")} #{receipt.id}?</h2>
    <p id="delete-receipt-description">{t("Bạn sẽ không thể khôi phục hóa đơn sau khi xóa.")}</p>
    {error && <p className="error" role="alert">{t(error)}</p>}
    <div className="confirm-dialog-actions">
      <button type="button" className="button-secondary" onClick={onCancel} disabled={deleting} autoFocus>{translate("Hủy")}</button>
      <button type="button" className="confirm-delete" onClick={onConfirm} disabled={deleting}>{deleting ? t("Đang xóa…") : t("Xóa hóa đơn")}</button>
    </div>
  </dialog>;
}

function ReceiptList({ status }) {
  const [items, setItems] = useState([]);
  const [nextCursor, setNextCursor] = useState(null);
  const [pageCount, setPageCount] = useState(1);
  const [reload, setReload] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState(null);
  const [receiptToDelete, setReceiptToDelete] = useState(null);
  const [deleteError, setDeleteError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    let timer;

    async function load() {
      try {
        let cursor = null;
        const rows = [];
        for (let page = 0; page < pageCount; page += 1) {
          const query = new URLSearchParams({ limit: String(PAGE_SIZE) });
          if (status) query.set("status", status);
          if (cursor) query.set("cursor", cursor);
          const result = await api(`/api/receipts?${query}`, { signal: controller.signal });
          if (!Array.isArray(result?.items)) throw new Error("Dữ liệu danh sách hóa đơn không hợp lệ. Hãy thử tải lại.");
          rows.push(...result.items);
          cursor = result.next_cursor ?? null;
          if (!cursor) break;
        }
        if (controller.signal.aborted) return;
        setItems(rows);
        setNextCursor(cursor);
        if (rows.some((receipt) => PENDING.has(receipt.status))) {
          timer = window.setTimeout(load, 1000);
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(err.status === 404
            ? t("Không truy cập được danh sách hóa đơn của hộ. Hãy kiểm tra hộ đang tham gia rồi thử lại.")
            : t(err.message));
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }

    void load();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [status, pageCount, reload]);

  function refresh() {
    setError("");
    setLoading(true);
    setReload((value) => value + 1);
  }

  async function removeReceipt(receipt) {
    if (deleting !== null) return;
    setDeleting(receipt.id);
    setDeleteError("");
    try {
      await api(`/api/receipts/${receipt.id}`, { method: "DELETE" });
      setItems((current) => current.filter((item) => item.id !== receipt.id));
      setError("");
      setReceiptToDelete(null);
      setReload((value) => value + 1);
    } catch (err) {
      setDeleteError(err.status === 405
        ? t("Máy chủ API hiện chưa hỗ trợ xóa hóa đơn. Hãy cập nhật backend rồi thử lại.")
        : err.message);
    }
    finally { setDeleting(null); }
  }

  return (
    <section className="card" aria-label={translate("Danh sách hóa đơn")} aria-busy={loading || deleting !== null}>
      <div className="toolbar">
        <p className="muted">{items.length} {t("hóa đơn")}{items.some((item) => PENDING.has(item.status)) ? ` · ${t("Tự cập nhật mỗi 3 giây khi còn hóa đơn đang xử lý")}` : ""}</p>
        <button type="button" className="button-secondary" onClick={refresh} disabled={loading}>{translate("Làm mới")}</button>
      </div>
      {error && <p className="error" role="alert">{t(error)}</p>}
      {loading && items.length === 0 && <p role="status">{translate("Đang tải hóa đơn…")}</p>}
      {!loading && !error && items.length === 0 && (
        <div className="empty-state">
          <h2>{translate("Chưa có hóa đơn phù hợp")}</h2>
          <p>{translate("Tải ảnh hóa đơn lên để bắt đầu đọc và kiểm tra chi tiêu.")}</p>
          <Link className="button" to="/upload">{translate("+ Tải hóa đơn")}</Link>
        </div>
      )}
      {items.length > 0 && <div className="table-scroll"><table className="receipt-table"><thead><tr><th>{translate("Hóa đơn")}</th><th>{translate("Cửa hàng")}</th><th>{translate("Ngày hóa đơn")}</th><th>{translate("Trạng thái")}</th><th className="text-right">{translate("Tổng tiền")}</th><th></th></tr></thead><tbody>{items.map((receipt) => <tr key={receipt.id}><td data-label={t("Hóa đơn")}><Link to={`/receipts/${receipt.id}`}>#{receipt.id}</Link></td><td data-label={t("Cửa hàng")}><Link to={`/receipts/${receipt.id}`}><strong>{receipt.merchant || t("Chưa xác định")}</strong></Link>{receipt.status !== "CONFIRMED" && receipt.warnings?.length > 0 && <small className="receipt-warning">{receipt.warnings.length} {t("cảnh báo cần kiểm tra")}</small>}</td><td data-label={t("Ngày hóa đơn")}>{receipt.occurred_on ? formatDate(receipt.occurred_on) : "—"}</td><td data-label={t("Trạng thái")}><span className={`status-badge status-${String(receipt.status).toLowerCase()}`}>{deleting === receipt.id ? t("Đang xóa…") : t(STATUS_LABEL[receipt.status] || receipt.status)}</span></td><td data-label={t("Tổng tiền")} className="text-right">{receipt.total_amount == null ? "—" : formatVnd(receipt.total_amount)}</td><td><button type="button" className="button-danger receipt-table-delete" aria-label={`${t("Xóa hóa đơn")} #${receipt.id}`} disabled={deleting !== null} onClick={() => { setDeleteError(""); setReceiptToDelete(receipt); }}>{t("Xóa")}</button></td></tr>)}</tbody></table></div>}
      {receiptToDelete && <DeleteReceiptDialog receipt={receiptToDelete} deleting={deleting !== null} error={deleteError} onCancel={() => setReceiptToDelete(null)} onConfirm={() => void removeReceipt(receiptToDelete)} />}
      {nextCursor && (
        <div className="form-actions">
          <button type="button" className="button-secondary" disabled={loading} onClick={() => { setLoading(true); setPageCount((count) => count + 1); }}>
            {loading ? t("Đang tải…") : t("Xem thêm hóa đơn")}
          </button>
        </div>
      )}
    </section>
  );
}

export default function Receipts() {
  const [status, setStatus] = useState("");
  const [membership, setMembership] = useState(null);
  const [reloadVersion, setReloadVersion] = useState(0);
  const location = useLocation();

  useEffect(() => {
    const controller = new AbortController();
    api("/api/me", { signal: controller.signal })
      .then((me) => { if (!controller.signal.aborted) setMembership(me); })
      .catch((error) => { if (!controller.signal.aborted) setMembership({ error: error.message }); });
    return () => controller.abort();
  }, [reloadVersion]);

  return (
    <>
      <div className="page-heading">
        <div><h1>{translate("Hóa đơn")}</h1><p className="muted">{translate("Theo dõi ảnh đã tải lên và kiểm tra kết quả đọc hóa đơn.")}</p></div>
        <Link className="button" to="/upload">{translate("+ Tải hóa đơn")}</Link>
      </div>
      {location.state?.message && <p className="notice success" role="status">{location.state.message}</p>}
      {!membership ? <p role="status">{translate("Đang kiểm tra hộ gia đình…")}</p> : membership.error ? (
        <div className="notice" role="alert"><p className="error">{membership.error}</p><button type="button" onClick={() => { setMembership(null); setReloadVersion((version) => version + 1); }}>{translate("Thử lại")}</button></div>
      ) : !membership.household ? <p>{translate("Bạn cần ")}<Link to="/">{translate("tạo hoặc tham gia một hộ")}</Link>{translate(" để xem hóa đơn.")}</p> : <>
      <div className="filter-pills receipt-filters" aria-label={translate("Lọc trạng thái hóa đơn")}>{[["", translate("Tất cả")], ...Object.entries(STATUS_LABEL).filter(([key]) => key !== "TIMEOUT")].map(([value, label]) => <button type="button" key={value} className={status === value ? "selected" : ""} aria-pressed={status === value} onClick={() => setStatus(value)}>{t(label)}</button>)}</div>
      <ReceiptList key={status} status={status} />
      </>}
    </>
  );
}
