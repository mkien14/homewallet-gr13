import { lazy, Suspense } from "react";
import { BrowserRouter, Link, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { isLoggedIn, login, logout } from "./auth/auth";
import { USE_MOCK } from "./mode";
import Callback from "./pages/Callback";
import Home from "./pages/Home";
import Upload from "./pages/Upload";

const TransactionNew = lazy(() => import("./pages/TransactionNew"));

function Protected({ children }) {
  if (!USE_MOCK && !isLoggedIn()) {
    return (
      <div className="card">
        <h2>HomeWallet</h2>
        <p>Quản lý chi tiêu gia đình.</p>
        <button onClick={login}>Đăng nhập hoặc đăng ký</button>
      </div>
    );
  }
  return children;
}

function AppContent() {
  useLocation();
  const authenticated = USE_MOCK || isLoggedIn();
  return (
    <>
      <a className="skip-link" href="#main-content">Đến nội dung chính</a>
      <header className="app-header">
        <Link className="brand" to="/">HomeWallet</Link>
        {authenticated && (
          <nav aria-label="Điều hướng chính">
            <NavLink to="/transactions/new">Nhập chi tiêu</NavLink>
            <NavLink to="/upload">Tải ảnh</NavLink>
            <NavLink to="/" end>Hộ gia đình</NavLink>
            {!USE_MOCK && <button className="button-secondary" onClick={logout}>Đăng xuất</button>}
          </nav>
        )}
      </header>
      {USE_MOCK && (
        <aside className="mock-banner" aria-label="Chế độ thử nghiệm">
          <strong>Dữ liệu giả</strong>
          <span>Bạn đang thử giao diện. Hóa đơn và chi tiêu được lưu riêng trên trình duyệt, không gửi lên AWS.</span>
          <button className="button-secondary" type="button" onClick={async () => {
            const { resetMockData } = await import("./mocks/index.js");
            resetMockData();
            window.location.reload();
          }}>Đặt lại dữ liệu mẫu</button>
        </aside>
      )}
      <main id="main-content">
        <Suspense fallback={<p role="status">Đang tải trang…</p>}>
        <Routes>
          <Route path="/auth/callback" element={<Callback />} />
          <Route path="/" element={<Protected><Home /></Protected>} />
          <Route path="/upload" element={<Protected><Upload /></Protected>} />
          <Route path="/transactions/new" element={<Protected><TransactionNew /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
      </main>
    </>
  );
}

export default function App() {
  return <BrowserRouter><AppContent /></BrowserRouter>;
}
