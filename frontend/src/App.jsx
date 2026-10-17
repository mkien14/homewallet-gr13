import { BrowserRouter, Link, Navigate, Route, Routes } from "react-router-dom";
import { isLoggedIn, login, logout } from "./auth/auth";
import Callback from "./pages/Callback";
import Home from "./pages/Home";
import Upload from "./pages/Upload";

function Protected({ children }) {
  if (!isLoggedIn()) {
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

export default function App() {
  return (
    <BrowserRouter>
      <header>
        <b>HomeWallet</b>
        {isLoggedIn() && (
          <nav>
            <Link to="/">Hộ gia đình</Link>
            <Link to="/upload">Tải hóa đơn</Link>
            <button onClick={logout}>Đăng xuất</button>
          </nav>
        )}
      </header>
      <main>
        <Routes>
          <Route path="/auth/callback" element={<Callback />} />
          <Route path="/" element={<Protected><Home /></Protected>} />
          <Route path="/upload" element={<Protected><Upload /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}