import { useState } from "react";
import { Link } from "react-router-dom";
import { STATUS_LABEL, uploadReceipt, waitForStatus } from "../image";
import { useMe } from "../useMe";

const MAX_FILES = 10;

export default function Upload() {
  const { me, error } = useMe();
  const [items, setItems] = useState([]);

  if (error) return <p className="error">{error}</p>;
  if (!me) return <p>Đang tải...</p>;
  if (!me.household) {
    return <p>Bạn cần <Link to="/">tạo hoặc tham gia một hộ</Link> trước khi tải hóa đơn.</p>;
  }

  const busy = items.some((i) => !i.done);

  async function onPick(e) {
    const files = Array.from(e.target.files).slice(0, MAX_FILES);
    e.target.value = "";
    const base = files.map((f, i) => ({ key: `${Date.now()}-${i}`, name: f.name, stage: "Chờ xử lý", done: false, error: null }));
    setItems(base);
    const patch = (key, p) => setItems((cur) => cur.map((it) => (it.key === key ? { ...it, ...p } : it)));

    // Xử lý lần lượt để không dồn nhiều yêu cầu cùng lúc
    for (let i = 0; i < files.length; i++) {
      const key = base[i].key;
      try {
        const id = await uploadReceipt(files[i], (stage) => patch(key, { stage }));
        patch(key, { stage: "Đã tải lên, đang kiểm tra trạng thái" });
        const status = await waitForStatus(id, (s) => patch(key, { stage: STATUS_LABEL[s] || s }));
        patch(key, { stage: STATUS_LABEL[status] || status, done: true });
      } catch (err) {
        patch(key, { stage: "Lỗi", error: err.message, done: true });
      }
    }
  }

  return (
    <div className="card">
      <h3>Tải ảnh hóa đơn</h3>
      <p>Tối đa {MAX_FILES} tệp (JPEG, PNG hoặc PDF dưới 5 MB). Ảnh được nén ngay trên máy bạn trước khi gửi.</p>
      <input type="file" multiple accept="image/jpeg,image/png,application/pdf" onChange={onPick} disabled={busy} />
      <ul>
        {items.map((it) => (
          <li key={it.key}>
            {it.name}: <b>{it.stage}</b>
            {it.error && <span className="error"> ({it.error})</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}