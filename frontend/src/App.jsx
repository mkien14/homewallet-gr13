import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { BrowserRouter, Link, NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { isLoggedIn, login, logout } from "./auth/auth";
import { isReactAuthSession, reactSignOut } from "./auth/cognito";
import { USE_MOCK } from "./mode";
import { PreferenceProvider, usePreferences } from "./preferences";
import { api } from "./api";
import { readCognitoPreferredLocale, writeCognitoPreferredLocale } from "./auth/locale";
import { config } from "./config";
import Callback from "./pages/Callback";
import Home from "./pages/Home";
import Upload from "./pages/Upload";

const Receipts = lazy(() => import("./pages/Receipts"));
const ReceiptDetail = lazy(() => import("./pages/ReceiptDetail"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const TransactionNew = lazy(() => import("./pages/TransactionNew"));
const Budgets = lazy(() => import("./pages/Budgets"));
const RecurringBills = lazy(() => import("./pages/RecurringBills"));
const MockFinanceTools = lazy(() => import("./components/MockFinanceTools"));
const ReactAuth = lazy(() => import("./pages/ReactAuth"));
const Notifications = lazy(() => import("./pages/Notifications"));
const Community = lazy(() => import("./pages/Community"));
const LOCALE_PENDING_KEY = "hw.locale.pending";

function pendingLocaleFor(userId) {
  const pending = localStorage.getItem(`${LOCALE_PENDING_KEY}.${userId}`);
  return pending === "vi" || pending === "en" ? pending : null;
}

function Protected({ children }) {
  const { t } = usePreferences();
  if (!USE_MOCK && !isLoggedIn()) {
    const loginAction = config.reactAuthEnabled
      ? <Link className="button" to="/auth/react">{t("Đăng nhập hoặc đăng ký")}</Link>
      : <button type="button" onClick={login}>{t("Đăng nhập hoặc đăng ký")}</button>;
    return <section className="guest-landing">
      <div className="guest-hero">
        <div className="guest-copy">
          <p className="eyebrow">{t("Tài chính gia đình, dễ theo dõi")}</p>
          <h1>{t("Cùng gia đình làm chủ chi tiêu mỗi ngày")}</h1>
          <p>{t("Ghi lại chi tiêu, theo dõi ngân sách và quản lý hóa đơn trong một không gian chung.")}</p>
          <div className="guest-actions">{loginAction}<span>{t("Bắt đầu miễn phí với tài khoản của bạn")}</span></div>
        </div>
        <div className="guest-highlights">
          <div><span className="guest-highlight-icon">↗</span><b>{t("Chi tiêu rõ ràng")}</b><small>{t("Xem khoản nào đang chiếm nhiều nhất.")}</small></div>
          <div><span className="guest-highlight-icon">▤</span><b>{t("Ngân sách chung")}</b><small>{t("Cả nhà cùng theo dõi kế hoạch tháng.")}</small></div>
          <div><span className="guest-highlight-icon">✓</span><b>{t("Hóa đơn gọn gàng")}</b><small>{t("Lưu và xác nhận hóa đơn tại một nơi.")}</small></div>
        </div>
      </div>
      <section className="guest-demo" aria-label={t("Bản xem trước giao diện HomeWallet")}>
        <div className="guest-demo-heading"><div><p className="eyebrow">HomeWallet</p><h2>{t("Tổng quan gia đình")}</h2></div><span className="status-badge">{t("Dữ liệu minh họa")}</span></div>
        <div className="guest-demo-metrics">
          <div><small>{t("Chi tiêu tháng này")}</small><strong>12.480.000 ₫</strong><span>{t("8 giao dịch")}</span></div>
          <div><small>{t("Ngân sách còn lại")}</small><strong>7.520.000 ₫</strong><span>{t("Của kế hoạch tháng")}</span></div>
          <div><small>{t("Hóa đơn cần kiểm tra")}</small><strong>2</strong><span>{t("Đang chờ xác nhận")}</span></div>
        </div>
        <div className="guest-demo-bottom">
          <div className="guest-chart-card"><div className="guest-demo-card-title"><b>{t("Diễn biến chi tiêu")}</b><span>{t("7 ngày qua")}</span></div><svg viewBox="0 0 600 150" role="img" aria-label={t("Biểu đồ chi tiêu minh họa")} preserveAspectRatio="none"><defs><linearGradient id="guest-chart-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#1d5fe0" stopOpacity=".2"/><stop offset="100%" stopColor="#1d5fe0" stopOpacity="0"/></linearGradient></defs><path d="M0 120 C45 110 55 85 100 95 S160 108 200 70 S265 92 300 58 S360 75 400 42 S470 68 500 32 S560 52 600 18 V150 H0Z" fill="url(#guest-chart-fill)"/><path d="M0 120 C45 110 55 85 100 95 S160 108 200 70 S265 92 300 58 S360 75 400 42 S470 68 500 32 S560 52 600 18" fill="none" stroke="#1d5fe0" strokeWidth="4" strokeLinecap="round"/></svg><div className="guest-chart-labels"><span>{t("T.2")}</span><span>{t("T.4")}</span><span>{t("T.6")}</span><span>{t("Hôm nay")}</span></div></div>
          <div className="guest-budget-card"><div className="guest-demo-card-title"><b>{t("Ngân sách tháng")}</b><span>62%</span></div><p>{t("Đã sử dụng")}</p><div className="guest-budget-track"><span /></div><strong>12.480.000 ₫ <small>/ 20.000.000 ₫</small></strong><div className="guest-demo-note">{t("Bản xem trước chỉ sử dụng dữ liệu minh họa.")}</div></div>
        </div>
      </section>
    </section>;
  }
  return children;
}

function AppContent() {
  const [toolsOpen, setToolsOpen] = useState(false);
  const navigate = useNavigate();
  const { locale, setLocale, theme, setTheme, t } = usePreferences();
  const authenticated = USE_MOCK || isLoggedIn();
  const localeUserId = useRef(null);
  const [localeSyncStatus, setLocaleSyncStatus] = useState("ready");

  const persistLocale = useCallback(async (next, userId) => {
    localStorage.setItem(`${LOCALE_PENDING_KEY}.${userId}`, next);
    setLocaleSyncStatus("saving");
    const [profile, cognito] = await Promise.allSettled([
      api("/api/me", { method: "PATCH", body: { preferred_locale: next } }),
      writeCognitoPreferredLocale(next),
    ]);
    if (profile.status === "fulfilled" && cognito.status === "fulfilled") {
      if (pendingLocaleFor(userId) === next) localStorage.removeItem(`${LOCALE_PENDING_KEY}.${userId}`);
      setLocaleSyncStatus("ready");
    } else {
      setLocaleSyncStatus(profile.status !== cognito.status ? "partial" : "failed");
    }
  }, []);

  useEffect(() => {
    let active = true;
    import("./push").then(({ serviceWorkerRegistration, setWorkerLocale }) => {
      setWorkerLocale(locale);
      return serviceWorkerRegistration();
    }).catch(() => {});
    const onMessage = (event) => {
      if (!active || event.data?.type !== "OPEN_NOTIFICATION_LINK") return;
      const href = event.data.href;
      if (typeof href === "string" && href.startsWith("/") && !href.startsWith("//")) navigate(href);
    };
    navigator.serviceWorker?.addEventListener("message", onMessage);
    return () => { active = false; navigator.serviceWorker?.removeEventListener("message", onMessage); };
  }, [navigate, locale]);

  useEffect(() => {
    if (!authenticated || USE_MOCK) { localeUserId.current = null; return undefined; }
    let active = true;
    queueMicrotask(() => { if (active) setLocaleSyncStatus("loading"); });
    api("/api/me").then(async ({ user }) => {
      if (!active) return;
      const userId = String(user.id);
      localeUserId.current = userId;
      const pending = pendingLocaleFor(userId);
      const profileLocale = user.preferred_locale === "en" ? "en" : "vi";
      if (pending) {
        setLocale(pending, { selected: false });
        await persistLocale(pending, userId);
        return;
      }
      try {
        const cognitoLocale = await readCognitoPreferredLocale();
        if (!active) return;
        const next = cognitoLocale === "en" || cognitoLocale === "vi" ? cognitoLocale : profileLocale;
        setLocale(next, { selected: false });
        if (profileLocale !== next || cognitoLocale !== next) await persistLocale(next, userId);
        else setLocaleSyncStatus("ready");
      } catch {
        if (!active) return;
        setLocale(profileLocale, { selected: false });
        setLocaleSyncStatus("cognito-unavailable");
      }
    }).catch(() => { if (active) setLocaleSyncStatus("profile-unavailable"); });
    return () => { active = false; };
  }, [authenticated, persistLocale, setLocale]);

  const changeLocale = (next) => {
    setLocale(next);
    if (authenticated && !USE_MOCK && localeUserId.current) void persistLocale(next, localeUserId.current);
  };

  return (
    <div className="app-window">
      <a className="skip-link" href="#main-content">{t("Bỏ qua đến nội dung chính")}</a>
      <header className="app-header">
        <Link className="brand" to="/">HomeWallet</Link>
        <span className="workspace-tab">⌂ &nbsp;{t("Cả hộ")}</span>
        <div className="header-preferences">
          <label><span>{t("Ngôn ngữ")}</span><select aria-label={t("Ngôn ngữ")} value={locale} disabled={authenticated && !USE_MOCK && ["loading", "saving", "cognito-unavailable", "profile-unavailable"].includes(localeSyncStatus)} onChange={(event) => changeLocale(event.target.value)}><option value="vi">Tiếng Việt</option><option value="en">English</option></select></label>
          <label><span>{t("Giao diện")}</span><select aria-label={t("Giao diện")} value={theme} onChange={(event) => setTheme(event.target.value)}><option value="light">{t("Sáng")}</option><option value="dark">{t("Tối")}</option></select></label>
        </div>
        {!USE_MOCK && (authenticated
          ? <button type="button" className="button-secondary header-logout" onClick={logout}>{t("Đăng xuất")}</button>
          : config.reactAuthEnabled
            ? <Link className="button button-secondary header-logout" to="/auth/react">{t("Đăng nhập hoặc đăng ký")}</Link>
            : <button type="button" className="button-secondary header-logout" onClick={login}>{t("Đăng nhập hoặc đăng ký")}</button>)}
      </header>
      {authenticated && !USE_MOCK && ["partial", "failed", "cognito-unavailable", "profile-unavailable"].includes(localeSyncStatus) && (
        <div className="notice" role="alert">
          {t({
            partial: "Ngôn ngữ mới chỉ được lưu một phần. Hãy thử lại.",
            failed: "Chưa đồng bộ được ngôn ngữ tài khoản. Hãy thử lại.",
            "cognito-unavailable": "Không đọc được ngôn ngữ tài khoản. Hãy đăng nhập lại.",
            "profile-unavailable": "Không tải được hồ sơ tài khoản. Hãy thử lại.",
          }[localeSyncStatus])}{" "}
          <button type="button" onClick={() => {
            if (localeSyncStatus === "profile-unavailable") window.location.reload();
            else if (localeSyncStatus === "cognito-unavailable") {
              if (isReactAuthSession()) void reactSignOut().then(() => navigate("/auth/react", { replace: true }));
              else void login();
            }
            else if (localeUserId.current) void persistLocale(locale, localeUserId.current);
          }}>{t(localeSyncStatus === "cognito-unavailable" ? "Đăng nhập lại" : "Thử lại")}</button>
        </div>
      )}
      {authenticated && (
          <nav className="workspace-nav" aria-label={t("Điều hướng chính")}>
            <div className="workspace-tools">
              <button className="workspace-tools-trigger" type="button" aria-expanded={toolsOpen} aria-haspopup="true" onClick={() => setToolsOpen((open) => !open)}>
                {t("Menu")} <span className="workspace-tools-icon" aria-hidden="true"><i></i><i></i><i></i></span>
              </button>
              {toolsOpen && <div className="workspace-tools-menu">
                <NavLink onClick={() => setToolsOpen(false)} to="/dashboard">{t("Thống kê")}</NavLink>
                <NavLink onClick={() => setToolsOpen(false)} to="/budgets">{t("Ngân sách")}</NavLink>
                <NavLink onClick={() => setToolsOpen(false)} to="/recurring-bills">{t("Định kỳ")}</NavLink>
                <NavLink onClick={() => setToolsOpen(false)} to="/transactions/new">{t("Nhập chi tiêu")}</NavLink>
                <NavLink onClick={() => setToolsOpen(false)} to="/receipts">{t("Hóa đơn")}</NavLink>
                <NavLink onClick={() => setToolsOpen(false)} to="/upload">{t("Tải ảnh")}</NavLink>
                <NavLink onClick={() => setToolsOpen(false)} to="/notifications">{t("Thông báo")}</NavLink>
                <NavLink onClick={() => setToolsOpen(false)} to="/community">{t("Cộng đồng")}</NavLink>
                <NavLink onClick={() => setToolsOpen(false)} to="/" end>{t("Hộ gia đình")}</NavLink>
              </div>}
            </div>
          </nav>
        )}
      {USE_MOCK && (
        <aside className="mock-banner" aria-label={t("Chế độ thử nghiệm")}>
          <strong>{t("Dữ liệu giả")}</strong>
          <span>{t("Bạn đang thử giao diện. Hóa đơn và chi tiêu được lưu riêng trên trình duyệt, không gửi lên AWS.")}</span>
          <button className="button-secondary" type="button" onClick={async () => {
            const { resetMockData } = await import("./mocks/index.js");
            resetMockData();
            window.location.reload();
          }}>{t("Đặt lại dữ liệu mẫu")}</button>
          <Suspense fallback={null}><MockFinanceTools /></Suspense>
        </aside>
      )}
      <main id="main-content">
        <Suspense fallback={<p role="status">Đang tải trang…</p>}>
        <Routes>
          <Route path="/auth/callback" element={<Callback />} />
          <Route path="/auth/react" element={<ReactAuth />} />
          <Route path="/" element={<Protected><Home /></Protected>} />
          <Route path="/upload" element={<Protected><Upload /></Protected>} />
          <Route path="/receipts" element={<Protected><Receipts /></Protected>} />
          <Route path="/receipts/:id" element={<Protected><ReceiptDetail /></Protected>} />
          <Route path="/dashboard" element={<Protected><Dashboard /></Protected>} />
          <Route path="/budgets" element={<Protected><Budgets /></Protected>} />
          <Route path="/recurring-bills" element={<Protected><RecurringBills /></Protected>} />
          <Route path="/transactions/new" element={<Protected><TransactionNew /></Protected>} />
          <Route path="/notifications" element={<Protected><Notifications /></Protected>} />
          <Route path="/community" element={<Protected><Community /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
      </main>
    </div>
  );
}

export default function App() {
  return <BrowserRouter><PreferenceProvider><AppContent /></PreferenceProvider></BrowserRouter>;
}
