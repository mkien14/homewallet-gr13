import { useEffect, useRef, useState } from "react";
import { t as translate } from "../preferences";
import { useNavigate } from "react-router-dom";
import { handleCallback, login } from "../auth/auth";

export default function Callback() {
  const navigate = useNavigate();
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const ran = useRef(false); 
  useEffect(() => {
    if (ran.current) return;
    ran.current = true;
    handleCallback()
      .then(() => navigate("/", { replace: true }))
      .catch((e) => setError(e.message));
  }, [navigate]);

  if (error) {
    return (
      <div className="card">
        <p className="error">{error}</p>
        <button disabled={busy} onClick={async () => {
          setBusy(true);
          try { await login(); }
          catch { setError(translate("Không kết nối được dịch vụ xác thực. Hãy thử lại.")); }
          finally { setBusy(false); }
        }}>{translate("Đăng nhập lại")}</button>
      </div>
    );
  }
  return <p>{translate("Đang đăng nhập...")}</p>;
}
