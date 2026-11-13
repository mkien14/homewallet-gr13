import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { isReactAuthSession, reactMfaPreference, reactPreferTOTP, reactSetUpTOTP, reactVerifyTOTP } from "../auth/cognito";
import { usePreferences } from "../preferences";
import { USE_MOCK } from "../mode";

export default function AccountSecurity() {
  const { t } = usePreferences();
  const [state, setState] = useState("loading");
  const [secret, setSecret] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const available = !USE_MOCK && isReactAuthSession();

  useEffect(() => {
    let active = true;
    if (available) reactMfaPreference().then((preference) => {
      if (active) setState(preference.preferred === "TOTP" ? "enabled" : preference.enabled?.includes("TOTP") ? "enrolled" : "ready");
    }).catch(() => { if (active) setState("unavailable"); });
    return () => { active = false; };
  }, [available]);

  async function start() {
    setBusy(true); setError("");
    try {
      if (state === "enrolled") {
        await reactPreferTOTP();
        setState("enabled");
        return;
      }
      const details = await reactSetUpTOTP();
      setSecret(details.sharedSecret);
    } catch { setError("Không thể thiết lập xác thực. Hãy đăng nhập lại rồi thử lại."); }
    finally { setBusy(false); }
  }

  async function confirm(event) {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      await reactVerifyTOTP(code.trim());
      await reactPreferTOTP();
      setSecret(""); setCode(""); setState("enabled");
    } catch { setError("Mã xác thực chưa đúng hoặc đã hết hạn. Hãy thử mã mới."); }
    finally { setBusy(false); }
  }

  return <section className="card privacy-page">
    <h1>{t("Bảo mật tài khoản")}</h1>
    <p>{t("Dùng ứng dụng xác thực để bảo vệ những lần đăng nhập tiếp theo.")}</p>
    {error && <p className="error" role="alert">{t(error)}</p>}
    {!available || state === "unavailable" ? <p>{t("Hãy đăng xuất và đăng nhập bằng màn HomeWallet để thiết lập bảo mật.")} <Link to="/auth/react">{t("Đăng nhập")}</Link></p>
      : state === "loading" ? <p role="status">{t("Đang tải...")}</p>
      : state === "enabled" ? <p className="success" role="status">{t("Ứng dụng xác thực đã được bật và ưu tiên. Hãy đăng xuất, đăng nhập lại và kiểm tra yêu cầu mã.")}</p>
      : secret ? <form onSubmit={confirm}>
        <p>{t("Thêm khóa này vào ứng dụng xác thực của bạn:")}</p><code className="totp-secret">{secret}</code>
        <p>{t("Giữ kín khóa này. Không gửi khóa hoặc mã xác thực cho người khác.")}</p>
        <label className="field">{t("Mã xác thực MFA")}<input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={code} onChange={(event) => setCode(event.target.value)} required disabled={busy} /></label>
        <button disabled={busy}>{t("Xác nhận")}</button>
      </form> : <button onClick={start} disabled={busy}>{t("Bật ứng dụng xác thực")}</button>}
  </section>;
}
