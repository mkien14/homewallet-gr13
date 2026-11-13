import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  hasReactAuthConfig,
  reactConfirmResetPassword,
  reactConfirmSignIn,
  reactConfirmSignUp,
  reactResendSignUpCode,
  reactResetPassword,
  reactSetUpTOTP,
  reactSignIn,
  reactSignUp,
  reactVerifyTOTP,
  saveReactAuthSession,
} from "../auth/cognito";
import { login } from "../auth/auth";
import { config } from "../config";
import { passwordMeetsPolicy, PASSWORD_POLICY_MESSAGE } from "../auth/passwordPolicy";
import { usePreferences } from "../preferences";

const ERROR_TEXT = {
  UserNotFoundException: "Không tìm thấy tài khoản với email này.",
  NotAuthorizedException: "Email hoặc mật khẩu chưa đúng.",
  UsernameExistsException: "Email này đã có tài khoản.",
  CodeMismatchException: "Mã xác minh không đúng.",
  ExpiredCodeException: "Mã đã hết hạn. Hãy gửi lại mã mới.",
  LimitExceededException: "Bạn đã thử quá nhiều lần. Hãy đợi rồi thử lại.",
  TooManyRequestsException: "Yêu cầu quá nhanh. Hãy thử lại sau ít phút.",
  PasswordResetRequiredException: "Tài khoản cần đặt lại mật khẩu trước khi đăng nhập.",
  InvalidPasswordException: "Mật khẩu chưa đáp ứng yêu cầu bảo mật của tài khoản.",
  CodeDeliveryFailureException: "Không gửi được mã. Hãy kiểm tra cấu hình email Cognito.",
};

export default function ReactAuth() {
  const { locale, t } = usePreferences();
  const navigate = useNavigate();
  const [flow, setFlow] = useState("signIn");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordAgain, setPasswordAgain] = useState("");
  const [code, setCode] = useState("");
  const [challenge, setChallenge] = useState("");
  const [totpSecret, setTotpSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const run = async (work) => {
    setBusy(true);
    setError("");
    setMessage("");
    try { await work(); }
    catch (err) { setError(ERROR_TEXT[err.name] || "Không thể hoàn thành yêu cầu."); }
    finally { setBusy(false); }
  };

  const finishOrContinue = async (result) => {
    if (result.isSignedIn || result.nextStep?.signInStep === "DONE") {
      await saveReactAuthSession();
      navigate("/", { replace: true });
      return;
    }
    const step = result.nextStep?.signInStep;
    if (step === "CONFIRM_SIGN_UP") setFlow("confirmSignUp");
    else if (step === "CONFIRM_SIGN_IN_WITH_SMS_CODE" || step === "CONFIRM_SIGN_IN_WITH_EMAIL_CODE" || step === "CONFIRM_SIGN_IN_WITH_TOTP_CODE" || step === "CONTINUE_SIGN_IN_WITH_MFA_SELECTION" || step === "CONTINUE_SIGN_IN_WITH_MFA_SETUP_SELECTION") {
      setChallenge(step);
      setFlow("mfa");
    } else if (step === "CONTINUE_SIGN_IN_WITH_TOTP_SETUP") {
      const details = await reactSetUpTOTP();
      setTotpSecret(details.sharedSecret);
      setFlow("totpSetup");
    } else if (step === "CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED") setFlow("newPassword");
    else setMessage(t("Hãy tiếp tục theo hướng dẫn xác minh được gửi đến email của bạn."));
  };

  const submit = (event) => {
    event.preventDefault();
    const username = email.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(username)) { setError("Hãy nhập email hợp lệ."); return; }

    if (flow === "signIn") return run(async () => finishOrContinue(await reactSignIn(username, password)));
    if (flow === "signUp") {
      if (!config.selfSignupEnabled) return;
      if (!passwordMeetsPolicy(password)) { setError(PASSWORD_POLICY_MESSAGE); return; }
      if (password !== passwordAgain) { setError("Hai mật khẩu chưa khớp."); return; }
      return run(async () => {
        const result = await reactSignUp(username, password, locale);
        if (result.isSignUpComplete) { setFlow("signIn"); setMessage(t("Tài khoản đã được tạo. Hãy đăng nhập.")); }
        else { setFlow("confirmSignUp"); setMessage(t("Mã xác minh đã được gửi đến email của bạn.")); }
      });
    }
    if (flow === "confirmSignUp") return run(async () => {
      await reactConfirmSignUp(username, code.trim());
      setFlow("signIn");
      setMessage(t("Đã xác minh email. Bạn có thể đăng nhập."));
    });
    if (flow === "mfa") return run(async () => finishOrContinue(await reactConfirmSignIn(challenge === "CONTINUE_SIGN_IN_WITH_MFA_SELECTION" || challenge === "CONTINUE_SIGN_IN_WITH_MFA_SETUP_SELECTION" ? code.trim().toUpperCase() : code.trim())));
    if (flow === "totpSetup") return run(async () => {
      await reactVerifyTOTP(code.trim());
      await finishOrContinue(await reactConfirmSignIn(code.trim()));
    });
    if (flow === "newPassword") {
      if (!passwordMeetsPolicy(password) || password !== passwordAgain) { setError(!passwordMeetsPolicy(password) ? PASSWORD_POLICY_MESSAGE : "Hai mật khẩu chưa khớp."); return; }
      return run(async () => finishOrContinue(await reactConfirmSignIn(password)));
    }
    if (flow === "forgot") return run(async () => {
      const result = await reactResetPassword(username);
      if (result.nextStep.resetPasswordStep === "CONFIRM_RESET_PASSWORD_WITH_CODE") {
        setFlow("confirmReset");
        setMessage(t("Đã gửi mã đặt lại mật khẩu."));
      } else {
        setFlow("signIn");
        setMessage(t("Đặt lại mật khẩu thành công. Hãy đăng nhập bằng mật khẩu mới."));
      }
    });
    if (flow === "confirmReset") {
      if (!passwordMeetsPolicy(password) || password !== passwordAgain) { setError(!passwordMeetsPolicy(password) ? PASSWORD_POLICY_MESSAGE : "Hai mật khẩu chưa khớp."); return; }
      return run(async () => {
        await reactConfirmResetPassword(username, code.trim(), password);
        setFlow("signIn");
        setMessage(t("Đặt lại mật khẩu thành công. Hãy đăng nhập bằng mật khẩu mới."));
      });
    }
  };

  const title = ({ signIn: "Đăng nhập HomeWallet", signUp: "Tạo tài khoản", confirmSignUp: "Xác minh email", mfa: "Xác minh đăng nhập", totpSetup: "Thiết lập ứng dụng xác thực", newPassword: "Mật khẩu mới bắt buộc", forgot: "Đặt lại mật khẩu", confirmReset: "Đặt lại mật khẩu" })[flow];
  const needsPassword = flow === "signIn" || flow === "signUp" || flow === "newPassword" || flow === "confirmReset";
  const needsCode = flow === "confirmSignUp" || (flow === "mfa" && !challenge.includes("SELECTION")) || flow === "totpSetup" || flow === "confirmReset";

  return <section className="auth-page">
    <div className="auth-shell">
      <aside className="auth-intro">
        <Link className="auth-brand" to="/">HomeWallet</Link>
        <span className="auth-intro-mark" aria-hidden="true">⌂</span>
        <p className="eyebrow">{t("Quản lý chi tiêu gia đình.")}</p>
        <h2>{t("Mọi khoản chi trong tầm mắt.")}</h2>
        <p>{t("Đăng nhập để cùng gia đình theo dõi ngân sách, hóa đơn và kế hoạch chi tiêu.")}</p>
        <div className="auth-intro-points"><span>✓ &nbsp;{t("An toàn với xác minh tài khoản")}</span><span>✓ &nbsp;{t("Dùng chung cho cả gia đình")}</span></div>
      </aside>
      <div className="auth-card">
        <div className="auth-card-heading"><p className="eyebrow">{t("Tài khoản HomeWallet")}</p><h1>{t(title)}</h1><p className="muted">{t("Nhập thông tin để tiếp tục.")}</p></div>
        {!hasReactAuthConfig() && <p className="notice auth-config-notice">{t("Không có cấu hình Cognito User Pool. Hãy thêm VITE_COGNITO_USER_POOL_ID để bật đăng nhập React.")}</p>}
        {message && <p className="success" role="status">{message}</p>}
        {error && <p className="error" role="alert">{t(error)}</p>}
        <form onSubmit={submit}>
          <label className="field">{t("Email")}<input type="email" autoComplete="email" placeholder="name@example.com" value={email} onChange={(event) => setEmail(event.target.value)} required disabled={busy} /></label>
          {needsPassword && <label className="field">{t(flow === "newPassword" || flow === "confirmReset" ? "Mật khẩu mới" : "Mật khẩu")}<input type="password" autoComplete={flow === "signIn" ? "current-password" : "new-password"} placeholder={t("Nhập mật khẩu")} value={password} onChange={(event) => setPassword(event.target.value)} required disabled={busy} /></label>}
          {(flow === "signUp" || flow === "newPassword" || flow === "confirmReset") && <><p className="muted">{t(PASSWORD_POLICY_MESSAGE)}</p><label className="field">{t("Xác nhận mật khẩu")}<input type="password" autoComplete="new-password" placeholder={t("Nhập lại mật khẩu")} value={passwordAgain} onChange={(event) => setPasswordAgain(event.target.value)} required disabled={busy} /></label></>}
          {needsCode && <label className="field">{t(flow === "mfa" ? "Mã xác thực MFA" : "Mã xác minh")}<input inputMode="numeric" autoComplete="one-time-code" placeholder={t("Nhập mã được gửi cho bạn")} value={code} onChange={(event) => setCode(event.target.value)} required disabled={busy} /></label>}
          {flow === "mfa" && challenge.includes("SELECTION") && <label className="field">{t("Chọn phương thức xác minh")}<select value={code} onChange={(event) => setCode(event.target.value)} required><option value="">{t("Chọn phương thức")}</option><option value="SMS">SMS</option><option value="EMAIL">Email</option><option value="TOTP">TOTP</option></select></label>}
          {flow === "totpSetup" && <p className="notice">{t("Thêm khóa này vào ứng dụng xác thực của bạn:")} <code>{totpSecret}</code></p>}
          <button type="submit" disabled={busy || !hasReactAuthConfig()}>{busy ? t("Đang xử lý…") : t(flow === "signIn" ? "Đăng nhập" : flow === "signUp" ? "Tạo tài khoản" : flow === "confirmSignUp" || flow === "mfa" || flow === "totpSetup" ? "Xác nhận" : flow === "forgot" ? "Gửi mã" : flow === "newPassword" ? "Đổi mật khẩu" : "Đặt lại mật khẩu")}</button>
        </form>
        <div className="auth-links">
          {flow === "signIn" && <>{config.selfSignupEnabled && <button type="button" className="link-button" onClick={() => { setFlow("signUp"); setError(""); setMessage(""); }}>{t("Tạo tài khoản")}</button>}<button type="button" className="link-button" onClick={() => { setFlow("forgot"); setError(""); setMessage(""); }}>{t("Quên mật khẩu?")}</button></>}
          {flow === "signUp" && <button type="button" className="link-button" onClick={() => setFlow("signIn")}>{t("Quay lại đăng nhập")}</button>}
          {flow === "confirmSignUp" && <button type="button" className="link-button" disabled={busy} onClick={() => run(async () => { await reactResendSignUpCode(email.trim()); setMessage(t("Mã đã được gửi lại.")); })}>{t("Gửi lại mã")}</button>}
          {(flow === "forgot" || flow === "confirmReset") && <button type="button" className="link-button" onClick={() => setFlow("signIn")}>{t("Quay lại đăng nhập")}</button>}
          {flow === "mfa" && <button type="button" className="link-button" onClick={() => setFlow("signIn")}>{t("Hủy xác minh")}</button>}
        </div>
        <div className="auth-footer"><button type="button" className="link-button" onClick={login}>{t("Dùng trang đăng nhập dự phòng")}</button><Link to="/">{t("Quay về trang chủ")}</Link></div>
        <small className="auth-security-note">{t("Thông tin đăng nhập được xác thực trực tiếp bởi Amazon Cognito.")}</small>
      </div>
    </div>
  </section>;
}
