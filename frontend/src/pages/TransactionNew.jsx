import { useEffect, useRef, useState } from "react";
import { t as translate } from "../preferences";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { formatVnd, parseVnd } from "../format";
import { t } from "../preferences";
import { buildTransactionBody, transactionDateLimit } from "../transactionForm";

function localToday() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

export default function TransactionNew() {
  const navigate = useNavigate();
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const [occurredOn, setOccurredOn] = useState(localToday);
  const [amount, setAmount] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [note, setNote] = useState("");
  const [setup, setSetup] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [retryBody, setRetryBody] = useState(null);
  const [reloadVersion, setReloadVersion] = useState(0);
  const submitting = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      const me = await api("/api/me", { signal: controller.signal });
      if (!me || typeof me !== "object") throw new Error("Không đọc được thông tin hộ gia đình. Hãy thử tải lại.");
      if (!me.household) return { household: null, categories: [] };
      const result = await api("/api/categories", { signal: controller.signal });
      if (!Array.isArray(result?.categories) || result.categories.some((category) => !category || !Number.isSafeInteger(category.id) || category.id <= 0 || typeof category.name !== "string")) {
        throw new Error("Không đọc được danh mục từ máy chủ. Hãy thử tải lại.");
      }
      return { household: me.household, categories: result.categories };
    }
    load().then((result) => {
      if (!controller.signal.aborted) {
        setSetup(result);
        setLoadError("");
      }
    }).catch((err) => {
      if (!controller.signal.aborted) setLoadError(err.message);
    });
    return () => controller.abort();
  }, [reloadVersion]);

  async function submit(event) {
    event.preventDefault();
    if (submitting.current) return;
    setError("");
    let body;
    try {
      body = retryBody || buildTransactionBody({ occurredOn, amount, categoryId, note }, setup?.categories || []);
    } catch (err) {
      setError(err.message);
      return;
    }
    submitting.current = true;
    setBusy(true);
    try {
      const result = await api("/api/transactions", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body,
      });
      if (!Number.isSafeInteger(result?.transaction?.id) || result.transaction.id <= 0 || result.transaction.status !== "CONFIRMED") {
        throw new Error("Máy chủ chưa trả về kết quả lưu giao dịch hợp lệ. Hãy gửi lại cùng nội dung để kiểm tra.");
      }
      navigate("/dashboard", { replace: true, state: { success: t("Đã thêm giao dịch thủ công.") } });
    } catch (err) {
      const uncertain = !err.status || err.status >= 500 || err.status === 409;
      if (uncertain) setRetryBody(body);
      setError(err.message);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  if (loadError) return (
    <section className="card">
      <h1>{t("Nhập giao dịch")}</h1>
      <p className="error" role="alert">{t(loadError)}</p>
      <button type="button" onClick={() => { setLoadError(""); setReloadVersion((v) => v + 1); }}>{translate("Thử lại")}</button>
    </section>
  );
  if (!setup) return <p role="status">{t("Đang tải danh mục...")}</p>;
  if (!setup.household) return <p>{t("Bạn cần")} <Link to="/">{t("tạo hoặc tham gia một hộ")}</Link> {t("trước khi nhập giao dịch.")}</p>;

  const formattedAmount = parseVnd(amount);
  const locked = busy || Boolean(retryBody);

  return (
    <>
      <div className="page-heading">
        <div><p className="eyebrow">{translate("Giao dịch")}</p><h1>{translate("Nhập chi tiêu thủ công")}</h1></div>
        <Link className="button button-secondary" to="/dashboard">{translate("Xem tổng quan")}</Link>
      </div>
      <div className="workspace-columns"><form className="card transaction-form" onSubmit={submit}>
        <p>{translate("Ghi lại khoản chi không có hóa đơn hoặc hóa đơn chưa đọc được.")}</p>
        {retryBody && <p className="notice" role="status">{t("Chưa xác nhận được kết quả gửi. Dữ liệu được giữ nguyên; bấm “Gửi lại giao dịch” để kiểm tra và gửi lại cùng mã, tránh tạo trùng.")}</p>}
        <div className="form-grid">
          <label className="field" htmlFor="transaction-date">{translate("Ngày chi tiêu")}<input id="transaction-date" type="date" min="0001-01-01" max={transactionDateLimit()} value={occurredOn} onChange={(e) => setOccurredOn(e.target.value)} required disabled={locked} />
          </label>
          <label className="field" htmlFor="transaction-amount">{translate("Số tiền (đồng)")}<input id="transaction-amount" type="text" inputMode="numeric" placeholder={translate("Ví dụ: 150.000")} value={amount} onChange={(e) => setAmount(e.target.value)} required disabled={locked} aria-describedby="amount-preview" />
            <small id="amount-preview">{formattedAmount !== null ? formatVnd(formattedAmount) : t("Nhập số nguyên đồng, không có phần thập phân.")}</small>
          </label>
          <label className="field" htmlFor="transaction-category">{translate("Danh mục")}<select id="transaction-category" value={categoryId} onChange={(e) => setCategoryId(e.target.value)} disabled={locked}>
              <option value="">{translate("Chưa phân loại")}</option>
              {setup.categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
            </select>
          </label>
        </div>
        <label className="field" htmlFor="transaction-note">{translate("Ghi chú (không bắt buộc)")}<textarea id="transaction-note" rows={3} maxLength={500} placeholder={translate("Ví dụ: Mua thực phẩm cho bữa tối")} value={note} onChange={(e) => setNote(e.target.value)} disabled={locked} />
        </label>
        {!setup.categories.length && <p className="notice">{translate("Hộ chưa có danh mục. Bạn vẫn có thể lưu giao dịch ở trạng thái Chưa phân loại.")}</p>}
        {error && <p className="error" role="alert">{t(error)}</p>}
        <div className="actions">
          <button type="submit" disabled={busy}>{busy ? t("Đang lưu...") : retryBody ? t("Gửi lại giao dịch") : t("Lưu giao dịch")}</button>
          {!retryBody && <Link to="/dashboard" className="text-link">{translate("Hủy")}</Link>}
        </div>
        <p className="muted">{translate("Bấm gửi lại sau lỗi mạng vẫn sử dụng cùng một mã giao dịch.")}</p>
      </form><aside className="workspace-stack"><section className="card"><h2>{translate("Thông tin giao dịch")}</h2><div className="dashboard-note">{translate("Giao dịch được tính vào thống kê sau khi lưu thành công.")}</div><p>{translate("Chọn ngày, số tiền và danh mục để gia đình dễ theo dõi.")}</p></section><section className="card"><h2>{translate("Có hóa đơn?")}</h2><p>{translate("Tải ảnh để đọc thông tin và kiểm tra trước khi xác nhận.")}</p><Link className="button button-secondary" to="/upload">{translate("Tải ảnh hóa đơn")}</Link></section></aside></div>
    </>
  );
}
