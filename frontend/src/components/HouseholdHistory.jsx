import { useEffect, useState } from "react";
import { api } from "../api";
import { formatDate } from "../format";
import { usePreferences } from "../preferences";
import "./household-history.css";

function historyTime(value) {
  if (!value) return "";
  const date = formatDate(value);
  const time = String(value).match(/^\d{4}-\d{2}-\d{2}T(\d{2}:\d{2})/);
  return date ? `${date}${time ? ` · ${time[1]}` : ""}` : "";
}

const reasonLabels = {
  left: "Đã rời hộ",
  removed: "Đã được chủ hộ xóa khỏi hộ",
  dissolved: "Hộ đã giải tán",
};

export default function HouseholdHistory({ refreshKey }) {
  const { t } = usePreferences();
  const [result, setResult] = useState({ items: null, error: "" });
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    api("/api/me/household-history", { signal: controller.signal }).then((data) => {
      if (!Array.isArray(data?.items)) throw new Error("Không đọc được lịch sử hộ. Hãy thử lại.");
      if (!controller.signal.aborted) setResult({ items: data.items, error: "" });
    }).catch((error) => {
      if (!controller.signal.aborted) setResult({ items: null, error: error.status === 404 ? "Chưa tải được lịch sử hộ. Hãy kiểm tra ứng dụng đã được cập nhật và thử lại." : error.message });
    });
    return () => controller.abort();
  }, [refreshKey, reload]);

  return <section className="card household-history" aria-labelledby="household-history-title">
    <div className="dashboard-card-head"><h2 id="household-history-title">{t("Lịch sử hộ đã tham gia")}</h2></div>
    <p className="muted">{t("Những lần rời hoặc giải tán trước khi có chức năng này có thể không xuất hiện.")}</p>
    {result.error ? <div role="alert"><p className="error">{t(result.error)}</p><button type="button" className="button-secondary" onClick={() => setReload((value) => value + 1)}>{t("Thử lại")}</button></div>
      : result.items === null ? <p role="status">{t("Đang tải lịch sử hộ…")}</p>
        : result.items.length === 0 ? <p>{t("Chưa có lịch sử hộ.")}</p>
          : <ul className="household-history-list">{result.items.map((item, index) => <li className="household-history-item" key={`${item.household_id}-${item.joined_at}-${item.ended_at || "current"}-${index}`}>
            <div className="household-history-heading"><strong>{item.household_name}</strong><span className="status-badge">{t(item.end_reason ? (reasonLabels[item.end_reason] || "Đã kết thúc") : "Đang tham gia")}</span></div>
            <p>{t("Vai trò")}: {t(item.role === "owner" ? "Chủ hộ" : "Thành viên")}</p>
            <p>{t("Tham gia")}: <time dateTime={item.joined_at}>{historyTime(item.joined_at)}</time></p>
            {item.ended_at && <p>{t("Kết thúc")}: <time dateTime={item.ended_at}>{historyTime(item.ended_at)}</time></p>}
          </li>)}</ul>}
  </section>;
}
