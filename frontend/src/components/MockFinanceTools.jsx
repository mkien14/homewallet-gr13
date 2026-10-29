import { useEffect, useState } from "react";
import { mockApi, setMockRole, setFinanceFailure } from "../mocks/index.js";

export default function MockFinanceTools() {
  const [role, setRole] = useState("");
  const [scenario, setScenario] = useState("none");
  const [message, setMessage] = useState("");
  useEffect(() => { mockApi("/api/me").then((me) => setRole(me.household?.role || "owner")); }, []);
  return <details className="mock-finance-tools"><summary>Thử quyền và lỗi</summary><div className="mock-finance-options">
    <label>Vai trò thử nghiệm<select aria-label="Vai trò thử nghiệm" value={role} onChange={(event) => { setMockRole(event.target.value); window.location.reload(); }}><option value="owner">Chủ hộ</option><option value="member">Thành viên</option></select></label>
    <label>Lần lưu / gợi ý tiếp theo<select aria-label="Lỗi mô phỏng tiếp theo" value={scenario} onChange={(event) => setScenario(event.target.value)}><option value="none">Bình thường</option><option value="network">Mất kết nối</option><option value="validation">Dữ liệu không hợp lệ (422)</option><option value="conflict">Xung đột dữ liệu (409)</option></select></label>
    <button type="button" className="button-secondary" onClick={() => { setFinanceFailure(scenario); setMessage(scenario === "none" ? "Đã tắt lỗi mô phỏng." : "Đã đặt lỗi cho lần lưu hoặc gợi ý tiếp theo. Bấm lại nút này để thử lại cùng lỗi."); }}>Áp dụng kịch bản</button>
    {message && <p role="status">{message}</p>}
    <p>Chọn lỗi rồi bấm “Áp dụng kịch bản”. Mỗi lỗi chỉ xảy ra một lần cho ngân sách. Đổi vai trò sẽ tải lại trang.</p>
  </div></details>;
}
