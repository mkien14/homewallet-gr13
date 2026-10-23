import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { STATUS_LABEL, uploadReceipt, waitForStatus } from "../image";
import { useMe } from "../useMe";

const MAX_FILES = 10;

export default function Upload() {
  const { me, error } = useMe();
  const [items, setItems] = useState([]);
  const uploadController = useRef(null);
  useEffect(() => {
    const controller = new AbortController();
    uploadController.current = controller;
    return () => controller.abort();
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!me) return <p>Đang tải...</p>;
  if (!me.household) {
    return <p>Bạn cần <Link to="/">tạo hoặc tham gia một hộ</Link> trước khi tải hóa đơn.</p>;
  }

  const busy = items.some((i) => !i.done);

  async function onPick(e) {
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
        const id = await uploadReceipt(files[i], (stage) => patch(key, { stage }), { signal });
        patch(key, { stage: "Đã tải lên, đang kiểm tra trạng thái", id });
        const status = await waitForStatus(id, (s) => patch(key, { stage: STATUS_LABEL[s] || s }), 60, { signal });
        patch(key, {
          stage: STATUS_LABEL[status] || status,
          error: status === "TIMEOUT" ? "Hệ thống vẫn đang xử lý. Bạn có thể theo dõi ở danh sách hóa đơn." : null,
          done: true,
        });
      } catch (err) {
        if (signal.aborted) return;
        patch(key, { stage: "Lỗi", error: err.message, done: true });
      }
    }
  }

  return (
    <div className="card">
      <h3>Tải ảnh hóa đơn</h3>
      <p>Tối đa {MAX_FILES} tệp (JPEG, PNG hoặc PDF dưới 5 MB). Ảnh được nén ngay trên máy bạn trước khi gửi.</p>
      <p><Link to="/receipts">Xem danh sách và xác nhận hóa đơn</Link></p>
      <label className="field">Chọn tệp hóa đơn
        <input type="file" multiple accept="image/jpeg,image/png,application/pdf" onChange={onPick} disabled={busy} />
      </label>
      <ul>
        {items.map((it) => (
          <li key={it.key}>
            {it.name}: <b>{it.stage}</b>
            {it.error && <span className="error"> ({it.error})</span>}
            {it.id && <> · <Link to={`/receipts/${it.id}`}>Xem hóa đơn</Link></>}
          </li>
        ))}
      </ul>
    </div>
  );
}
