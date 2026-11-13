import { useEffect, useRef, useState } from "react";
import { usePreferences } from "../preferences";
import { Link } from "react-router-dom";
import { uploadReceipt } from "../image";
import { useMe } from "../useMe";
import Icon from "../components/Icon";
import { config } from "../config";

const MAX_FILES = 10;

export default function Upload() {
  const { t: translate } = usePreferences();
  const { me, error } = useMe();
  const [items, setItems] = useState([]);
  const [processingConsent, setProcessingConsent] = useState(false);
  const uploadController = useRef(null);
  useEffect(() => {
    const controller = new AbortController();
    uploadController.current = controller;
    return () => controller.abort();
  }, []);

  if (error) return <p className="error">{translate(error)}</p>;
  if (!me) return <p>{translate("Đang tải...")}</p>;
  if (!me.household) {
    return <p>{translate("Bạn cần ")}<Link to="/">{translate("tạo hoặc tham gia một hộ")}</Link>{translate(" trước khi tải hóa đơn.")}</p>;
  }

  const busy = items.some((i) => !i.done);

  async function onPick(e) {
    if (!processingConsent || !config.ocrEnabled) { e.target.value = ""; return; }
    const signal = uploadController.current.signal;
    const files = Array.from(e.target.files).slice(0, MAX_FILES);
    e.target.value = "";
    const base = files.map((f, i) => ({ key: `${Date.now()}-${i}`, name: f.name, stage: "Chờ xử lý", done: false, error: null }));
    setItems(base);
    const patch = (key, p) => { if (!signal.aborted) setItems((cur) => cur.map((it) => (it.key === key ? { ...it, ...p } : it))); };

    // Xử lý lần lượt để không dồn nhiều yêu cầu cùng lúc
    for (let i = 0; i < files.length; i++) {
      if (signal.aborted) return;
      const key = base[i].key;
      try {
        const id = await uploadReceipt(files[i], (stage) => patch(key, { stage }), { signal, processingConsent });
        patch(key, { stage: "Đã tải lên. Xem hóa đơn để theo dõi xử lý", id, done: true });
      } catch (err) {
        if (signal.aborted) return;
        patch(key, { stage: "Lỗi", error: err.message, done: true });
      }
    }
  }

  return <>
    <div className="page-heading"><div><p className="eyebrow">{translate("Giao dịch / Hóa đơn")}</p><h1>{translate("Tải ảnh hóa đơn")}</h1></div><Link className="button button-secondary" to="/receipts">{translate("Xem và xác nhận hóa đơn")}</Link></div>
    <div className="workspace-columns"><section className="card"><div className="dashboard-card-head"><h2 className="icon-heading"><Icon name="upload" />{translate("Chọn tệp")}</h2><span className="status-badge">JPEG · PNG · PDF</span></div>
      {!config.ocrEnabled ? <p className="notice">{translate("Tải và đọc hóa đơn đang tạm tắt. Bạn vẫn có thể nhập chi tiêu.")} <Link to="/transactions/new">{translate("Nhập chi tiêu")}</Link></p> : <>
      <label className="processing-consent"><input type="checkbox" checked={processingConsent} disabled={busy} onChange={(event) => setProcessingConsent(event.target.checked)} /><span>{translate("Tôi đồng ý gửi nội dung hóa đơn tới dịch vụ xử lý để tạo bản nháp và sẽ kiểm tra trước khi xác nhận.")} <Link to="/privacy">{translate("Quyền riêng tư và dữ liệu")}</Link></span></label>
      <label className="upload-drop"><span className="upload-icon"><Icon name="upload" /></span><strong>{translate("Chọn ảnh hóa đơn từ máy")}</strong><span>{translate("Chụp rõ nội dung và tổng tiền trên hóa đơn")}</span><span className="button">{translate("Chọn tệp hóa đơn")}</span><input type="file" multiple accept="image/jpeg,image/png,application/pdf" onChange={onPick} disabled={busy || !processingConsent} /><small>{translate("Tối đa ")}{MAX_FILES}{translate(" tệp · Dưới 5 MB mỗi tệp · Ảnh được nén trên máy")}</small></label>
      </>}
      <div className="upload-queue">{items.map((it) => <div className="upload-item" key={it.key}><span className="upload-file-icon">▤</span><div><strong>{it.name}</strong><small>{translate(it.stage)}{it.error && <span className="error"> · {translate(it.error)}</span>}</small></div>{it.id && <Link className="icon-link" to={`/receipts/${it.id}`}>{translate("Xem")}<Icon name="arrow-right" /></Link>}</div>)}</div>
    </section><aside className="workspace-stack"><section className="card"><h2>{translate("☷  Quy trình")}</h2><ol className="process-list"><li><b>{translate("Chọn ảnh hóa đơn")}</b><small>{translate("Chọn tối đa 10 tệp mỗi lượt")}</small></li><li><b>{translate("Nén trên máy")}</b><small>{translate("Giảm dung lượng trước khi gửi")}</small></li><li><b>{translate("Tải lên và đọc")}</b><small>{translate("Hệ thống xử lý nội dung hóa đơn")}</small></li><li><b>{translate("Kiểm tra và xác nhận")}</b><small>{translate("Kiểm tra bản nháp trước khi ghi nhận")}</small></li></ol></section><section className="card"><h2>{translate("✦  Mẹo chụp rõ nét")}</h2><p>{translate("✓  Đặt hóa đơn trên nền phẳng, đủ sáng")}</p><p>{translate("✓  Chụp thẳng, thấy rõ dòng tổng cộng")}</p><p>{translate("✓  Mỗi ảnh chỉ một hóa đơn")}</p></section></aside></div>
  </>;
}
