import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { handleCallback, login } from "../auth/auth";

export default function Callback() {
  const navigate = useNavigate();
  const [error, setError] = useState(null);
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
        <button onClick={login}>Đăng nhập lại</button>
      </div>
    );
  }
  return <p>Đang đăng nhập...</p>;
}