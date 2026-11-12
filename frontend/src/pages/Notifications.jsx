import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { usePreferences } from "../preferences";
import { config } from "../config";
import { getBrowserPushSubscription, pushPermission, pushSupport, subscribeBrowserPush, unsubscribeBrowserPush } from "../push";
import { USE_MOCK } from "../mode";
import { notificationDate, notificationText } from "../notificationContent";
import Icon from "../components/Icon";

function PushSettings() {
  const { locale, t } = usePreferences();
  const [supported, setSupported] = useState(false);
  const [permission, setPermission] = useState("default");
  const [enabled, setEnabled] = useState(false);
  const [subscriptionId, setSubscriptionId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const syncExisting = useCallback(async () => {
    if (USE_MOCK) {
      setSupported(true);
      setPermission("granted");
      setEnabled(localStorage.getItem("hw.mock.push.enabled") === "1");
      setSubscriptionId(localStorage.getItem("hw.mock.push.id") || null);
      return;
    }
    setSupported(pushSupport());
    setPermission(pushPermission());
    if (!pushSupport()) return;
    const existing = await getBrowserPushSubscription();
    if (!existing) { setEnabled(false); setSubscriptionId(null); return; }
    const result = await api("/api/push/subscriptions", { method: "POST", body: existing.toJSON() });
    setEnabled(true);
    setSubscriptionId(result.subscription?.id ?? null);
  }, []);

  useEffect(() => { queueMicrotask(() => { void syncExisting().catch((err) => setError(err.message)); }); }, [syncExisting]);

  useEffect(() => {
    if (!enabled || USE_MOCK) return;
    navigator.serviceWorker?.ready.then((registration) => {
      registration.active?.postMessage({ type: "SET_LOCALE", locale });
    }).catch(() => {});
  }, [enabled, locale]);

  async function toggle() {
    setBusy(true); setError("");
    try {
      if (enabled) {
        if (USE_MOCK) {
          if (subscriptionId) await api(`/api/push/subscriptions/${subscriptionId}`, { method: "DELETE" });
          localStorage.removeItem("hw.mock.push.enabled"); localStorage.removeItem("hw.mock.push.id");
        } else {
          if (!subscriptionId) throw new Error("Không tìm thấy đăng ký push đã lưu để tắt. Hãy thử tải lại trạng thái.");
          await api(`/api/push/subscriptions/${subscriptionId}`, { method: "DELETE" });
          await unsubscribeBrowserPush();
        }
        setEnabled(false); setSubscriptionId(null);
      } else if (USE_MOCK) {
        const result = await api("/api/push/subscriptions", { method: "POST", body: { browser_id: "mock-browser" } });
        setSubscriptionId(result.subscription.id); setEnabled(true);
        localStorage.setItem("hw.mock.push.enabled", "1"); localStorage.setItem("hw.mock.push.id", String(result.subscription.id));
      } else {
        if (!config.vapidPublicKey) throw new Error("Thiếu VITE_VAPID_PUBLIC_KEY. Thông báo trong ứng dụng vẫn dùng được.");
        const result = await subscribeBrowserPush();
        setPermission(result.permission);
        if (!result.subscription) return;
        const saved = await api("/api/push/subscriptions", { method: "POST", body: result.subscription.toJSON() });
        setSubscriptionId(saved.subscription.id); setEnabled(true);
      }
    } catch (err) { setError(err.message || t("Không thể cập nhật cài đặt thông báo.")); }
    finally { setBusy(false); }
  }

  const permissionLabel = !supported ? t("Không được hỗ trợ trên trình duyệt này") : permission === "denied" ? t("Đã bị chặn trong cài đặt trình duyệt") : permission === "granted" ? t("Được phép") : t("Chưa hỏi quyền");
  const canToggle = supported && (enabled || USE_MOCK || Boolean(config.vapidPublicKey)) && (enabled || permission !== "denied");

  return <section className="card push-settings">
    <div className="community-heading"><div><p className="eyebrow">{t("Thông báo trên thiết bị")}</p><h2>{t("Web Push")}</h2></div><span className={`status-badge ${enabled ? "status-confirmed" : ""}`}>{enabled ? t("Đã bật") : t("Đang tắt")}</span></div>
    <p>{t("Nhận lời nhắc hóa đơn và cảnh báo ngân sách trên thiết bị này.")}</p>
    <p className="muted">{t("Trạng thái trình duyệt")}: {permissionLabel}</p>
    {!config.vapidPublicKey && !USE_MOCK && <p className="notice">{t("Chưa cấu hình khóa VAPID công khai. Bạn vẫn xem được thông báo trong ứng dụng và nhận email theo cài đặt hiện có.")}</p>}
    {error && <p className="error" role="alert">{t(error)}</p>}
    <button type="button" className={enabled ? "button-secondary" : ""} disabled={!canToggle || busy} onClick={toggle}>
      {busy ? t("Đang lưu…") : enabled ? t("Tắt thông báo trên thiết bị này") : t("Bật thông báo trên thiết bị này")}
    </button>
    {!supported && <p className="muted">{t("Thông báo trong ứng dụng và email vẫn tiếp tục hoạt động.")}</p>}
    {supported && permission === "denied" && <p className="muted">{t("Hãy cấp quyền thông báo trong cài đặt trình duyệt rồi tải lại trang.")}</p>}
  </section>;
}

function NotificationList() {
  const { locale, t } = usePreferences();
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const result = await api("/api/notifications?limit=50");
      setItems(Array.isArray(result.items) ? result.items : []);
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { queueMicrotask(() => { void load(); }); }, [load]);

  async function open(item) {
    setBusyId(item.id);
    try {
      if (!item.read) {
        await api(`/api/notifications/${item.id}`, { method: "PATCH", body: { read: true } });
        setItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, read: true } : entry));
      }
      const target = typeof item.deep_link === "string" && item.deep_link.startsWith("/") && !item.deep_link.startsWith("//") ? item.deep_link : "/";
      navigate(target);
    } catch (err) { setError(err.message); }
    finally { setBusyId(null); }
  }

  return <section className="card notification-list-card">
    <div className="community-heading notification-heading"><div><p className="eyebrow">{t("Hộ gia đình")}</p><h2>{t("Thông báo trong ứng dụng")}</h2></div><button type="button" className="button-secondary" onClick={load} disabled={loading}>{t("Làm mới")}</button></div>
    {!loading && items.length > 0 && <p className="notification-summary">{t("Chưa đọc")}: <b>{items.filter((item) => !item.read).length}</b> / {items.length}</p>}
    {error && <div className="notice error" role="alert"><p>{t(error)}</p><button className="button-secondary" type="button" onClick={load}>{t("Thử lại")}</button></div>}
    {loading ? <p role="status">{t("Đang tải thông báo…")}</p> : items.length === 0 ? <p className="empty-state">{t("Bạn chưa có thông báo.")}</p> : <ul className="notification-list">{items.map((item) => <li className={item.read ? "notification-item is-read" : "notification-item"} key={item.id}>
      <span className="notification-dot" aria-hidden="true"></span><div className="notification-copy"><div className="notification-title-row"><strong>{notificationText(item.title, locale, t, "Thông báo")}</strong><span className={`status-badge ${item.read ? "" : "status-confirmed"}`}>{t(item.read ? "Đã đọc" : "Mới")}</span></div><p>{notificationText(item.body, locale, t)}</p><small>{notificationDate(item.created_at, locale)}</small></div><button type="button" className="button-secondary notification-open" onClick={() => open(item)} disabled={busyId !== null}>{busyId === item.id ? t("Đang mở…") : <>{t("Mở")}<Icon name="arrow-right" /></>}</button>
    </li>)}</ul>}
  </section>;
}

export default function Notifications() {
  const { t } = usePreferences();
  return <><div className="page-heading"><div><p className="eyebrow">HomeWallet</p><h1>{t("Thông báo")}</h1><p>{t("Thông tin về ngân sách và hóa đơn định kỳ của gia đình.")}</p></div></div><div className="notification-workspace"><NotificationList /><PushSettings /></div></>;
}
