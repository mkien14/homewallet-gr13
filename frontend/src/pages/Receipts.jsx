import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api } from "../api";
import { formatDate, formatVnd } from "../format";
import { STATUS_LABEL } from "../image";

const PENDING = new Set(["UPLOADING", "UPLOADED", "PROCESSING"]);
const PAGE_SIZE = 50;

function ReceiptList({ status }) {
  const [items, setItems] = useState([]);
  const [nextCursor, setNextCursor] = useState(null);
  const [pageCount, setPageCount] = useState(1);
  const [reload, setReload] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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
        setError("");
        if (rows.some((receipt) => PENDING.has(receipt.status))) {
          timer = window.setTimeout(load, 3000);
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(err.status === 404
            ? "Không truy cập được danh sách hóa đơn của hộ. Hãy kiểm tra hộ đang tham gia rồi thử lại."
            : err.message);
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
    setLoading(true);
    setReload((value) => value + 1);
  }

  return (
    <section className="card" aria-label="Danh sách hóa đơn" aria-busy={loading}>
      <div className="toolbar">
        <p className="muted">{items.length} hóa đơn{items.some((item) => PENDING.has(item.status)) ? " · Tự cập nhật mỗi 3 giây khi còn hóa đơn đang xử lý" : ""}</p>
        <button type="button" className="button-secondary" onClick={refresh} disabled={loading}>Làm mới</button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {loading && items.length === 0 && <p role="status">Đang tải hóa đơn…</p>}
      {!loading && !error && items.length === 0 && (
        <div className="empty-state">
          <h2>Chưa có hóa đơn phù hợp</h2>
          <p>Tải ảnh hóa đơn lên để bắt đầu đọc và kiểm tra chi tiêu.</p>
          <Link className="button-link" to="/upload">Tải hóa đơn</Link>
        </div>
      )}
      <div className="receipt-list">
        {items.map((receipt) => (
          <article className="receipt-row" key={receipt.id}>
            <div className="receipt-summary">
              <Link to={`/receipts/${receipt.id}`}><strong>{receipt.merchant || `Hóa đơn #${receipt.id}`}</strong></Link>
              <span className="muted">{receipt.occurred_on ? formatDate(receipt.occurred_on) : "Chưa xác định ngày"}</span>
              {receipt.warnings?.length > 0 && <span className="muted">Có {receipt.warnings.length} cảnh báo cần kiểm tra</span>}
            </div>
            <strong>{receipt.total_amount == null ? "Chưa có tổng tiền" : formatVnd(receipt.total_amount)}</strong>
            <span className={`status-badge status-${String(receipt.status).toLowerCase()}`}>{STATUS_LABEL[receipt.status] || receipt.status}</span>
            <Link to={`/receipts/${receipt.id}`}>Xem hóa đơn <span aria-hidden="true">→</span></Link>
          </article>
        ))}
      </div>
      {nextCursor && (
        <div className="form-actions">
          <button type="button" className="button-secondary" disabled={loading} onClick={() => { setLoading(true); setPageCount((count) => count + 1); }}>
            {loading ? "Đang tải…" : "Xem thêm hóa đơn"}
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
        <div><h1>Hóa đơn</h1><p className="muted">Theo dõi ảnh đã tải lên và kiểm tra kết quả đọc hóa đơn.</p></div>
        <Link className="button-link" to="/upload">Tải hóa đơn</Link>
      </div>
      {location.state?.message && <p className="notice success" role="status">{location.state.message}</p>}
      {!membership ? <p role="status">Đang kiểm tra hộ gia đình…</p> : membership.error ? (
        <div className="notice" role="alert"><p className="error">{membership.error}</p><button type="button" onClick={() => { setMembership(null); setReloadVersion((version) => version + 1); }}>Thử lại</button></div>
      ) : !membership.household ? <p>Bạn cần <Link to="/">tạo hoặc tham gia một hộ</Link> để xem hóa đơn.</p> : <>
      <div className="toolbar">
        <label className="field" htmlFor="receipt-status-filter">Trạng thái
          <select id="receipt-status-filter" value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">Tất cả trạng thái</option>
            {Object.entries(STATUS_LABEL).filter(([key]) => key !== "TIMEOUT").map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
        </label>
      </div>
      <ReceiptList key={status} status={status} />
      </>}
    </>
  );
}
