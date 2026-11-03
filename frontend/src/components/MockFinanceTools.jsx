import { useEffect, useState } from "react";
import { mockApi, setMockRole, setFinanceFailure } from "../mocks/index.js";
import { usePreferences } from "../preferences";

export default function MockFinanceTools() {
  const { t } = usePreferences();
  const [role, setRole] = useState("");
  const [scenario, setScenario] = useState("none");
  const [message, setMessage] = useState("");
  useEffect(() => { mockApi("/api/me").then((me) => setRole(me.household?.role || "owner")); }, []);
  return <details className="mock-finance-tools"><summary>{t("Thử quyền và lỗi")}</summary><div className="mock-finance-options">
    <label>{t("Vai trò thử nghiệm")}<select aria-label={t("Vai trò thử nghiệm")} value={role} onChange={(event) => { setMockRole(event.target.value); window.location.reload(); }}><option value="owner">{t("Chủ hộ")}</option><option value="member">{t("Thành viên")}</option></select></label>
    <label>{t("Lần lưu / gợi ý tiếp theo")}<select aria-label={t("Lỗi mô phỏng tiếp theo")} value={scenario} onChange={(event) => setScenario(event.target.value)}><option value="none">{t("Mặc định")}</option><option value="network">{t("Mất kết nối")}</option><option value="validation">{t("Dữ liệu không hợp lệ (422)")}</option><option value="conflict">{t("Xung đột dữ liệu (409)")}</option></select></label>
    <button type="button" className="button-secondary" onClick={() => { setFinanceFailure(scenario); setMessage(t(scenario === "none" ? "Đã tắt lỗi mô phỏng." : "Đã đặt lỗi cho lần lưu hoặc gợi ý tiếp theo. Bấm lại nút này để thử lại cùng lỗi.")); }}>{t("Áp dụng kịch bản")}</button>
    {message && <p role="status">{message}</p>}
    <p>{t("Chọn lỗi rồi bấm “Áp dụng kịch bản”. Mỗi lỗi chỉ xảy ra một lần cho ngân sách hoặc hóa đơn định kỳ. Đổi vai trò sẽ tải lại trang.")}</p>
  </div></details>;
}
