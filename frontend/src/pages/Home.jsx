import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useMe } from "../useMe";
import { usePreferences } from "../preferences";
import Icon from "../components/Icon";
import { userDisplayName } from "../displayName";

function Setup({ onDone }) {
  const { t } = usePreferences();
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState(null);

  async function run(fn) {
    setError(null);
    try {
      await fn();
      onDone();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <>
      <p>{t("Bạn chưa thuộc hộ nào.")}</p>
      <div className="card">
        <h3>{t("Tạo hộ mới")}</h3>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("Tên hộ, ví dụ: Nhà Kiên")} />
        <button onClick={() => run(() => api("/api/households", { method: "POST", body: { name } }))}>{t("Tạo hộ")}</button>
      </div>
      <div className="card">
        <h3>{t("Tham gia bằng mã mời")}</h3>
        <input value={code} onChange={(e) => setCode(e.target.value)} placeholder={t("Mã mời 8 ký tự")} />
        <button onClick={() => run(() => api("/api/households/join", { method: "POST", body: { invite_code: code } }))}>
          {t("Tham gia")}
        </button>
      </div>
      {error && <p className="error">{t(error)}</p>}
    </>
  );
}

function HouseholdView({ household, onChange }) {
  const { t } = usePreferences();
  const [members, setMembers] = useState([]);
  const [error, setError] = useState(null);
  const [copying, setCopying] = useState(false);
  const [copyFeedback, setCopyFeedback] = useState(null);
  const isOwner = household.role === "owner";

  const load = useCallback(
    () =>
      api(`/api/households/${household.id}/members`)
        .then((r) => setMembers(r.members))
        .catch((e) => setError(e.message)),
    [household.id]
  );
  useEffect(() => {
    load();
  }, [load]);

  async function act(fn) {
    setError(null);
    setCopyFeedback(null);
    try {
      await fn();
      await load();
      onChange();
    } catch (e) {
      setError(e.message);
    }
  }

  async function copyInviteCode() {
    if (!isOwner || !household.invite_code || copying) return;
    const code = household.invite_code;
    setCopying(true);
    setCopyFeedback(null);
    try {
      await navigator.clipboard.writeText(code);
      setCopyFeedback({ code, success: true });
    } catch {
      setCopyFeedback({ code, success: false });
    } finally {
      setCopying(false);
    }
  }

  const currentCopyFeedback = copyFeedback?.code === household.invite_code ? copyFeedback : null;

  return (
    <div className="workspace-columns">
      <section className="card">
        <div className="dashboard-card-head"><h2>{t("Các thành viên")}</h2><span className="status-badge">{members.length} {t("người")}</span></div>
        <div className="table-scroll">
          <table className="household-members-table">
            <thead><tr><th>{t("Các thành viên")}</th><th className="member-role-cell">{t("Vai trò")}</th><th></th></tr></thead>
            <tbody>{members.map((m) => (
              <tr key={m.id}>
                <td><div className="household-member"><span className="member-avatar">{m.display_name?.slice(0, 1).toUpperCase()}</span><div><b>{m.display_name}</b><small>{m.email}</small></div></div></td>
                <td className="member-role-cell"><span className="status-badge">{m.role === "owner" ? t("Chủ hộ") : t("Thành viên")}</span></td>
                <td>{isOwner && m.role !== "owner" && <button type="button" className="button-danger" onClick={() => act(() => api(`/api/households/${household.id}/members/${m.id}`, { method: "DELETE" }))}>{t("Xóa")}</button>}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <div className="dashboard-note">{t("Gửi mã mời cho người thân để họ tham gia hộ gia đình.")}</div>
        {error && <p className="error">{t(error)}</p>}
      </section>
      <aside className="workspace-stack">
        <section className="card">
          <h2 className="icon-heading"><Icon name="home" />{t("Thông tin hộ")}</h2>
          <p>{household.name}</p>
          <p>{t("Vai trò")}: <b>{isOwner ? t("Chủ hộ") : t("Thành viên")}</b></p>
          {isOwner && <>
            <small>{t("Mã mời")}</small>
            <p className="invite-code">{household.invite_code}</p>
            <div className="form-actions">
              <button type="button" className="button-secondary" disabled={copying || !household.invite_code} onClick={copyInviteCode}>{copying ? t("Đang sao chép…") : t("Sao chép mã mời")}</button>
              <button type="button" className="button-secondary" disabled={copying} onClick={() => act(() => api(`/api/households/${household.id}/invite-code`, { method: "POST" }))}>{t("Đổi mã mời")}</button>
            </div>
            <p className={currentCopyFeedback?.success === false ? "error" : "muted"} role="status" aria-live="polite">
              {currentCopyFeedback && t(currentCopyFeedback.success ? "Đã sao chép mã mời." : "Không thể sao chép. Hãy chọn mã mời và sao chép thủ công.")}
            </p>
          </>}
        </section>
        <section className="card">
          <h2>{t("Quyền trong hộ")}</h2>
          <p><span className="household-check" aria-hidden="true">✓</span> &nbsp;{t("Theo dõi chi tiêu chung")}</p>
          <p><span className="household-check" aria-hidden="true">✓</span> &nbsp;{t("Kiểm tra hóa đơn")}</p>
          <p><span className="household-check" aria-hidden="true">✓</span> &nbsp;{t("Xem ngân sách gia đình")}</p>
        </section>
      </aside>
    </div>
  );

}

export default function Home() {
  const { t } = usePreferences();
  const { me, error, reload } = useMe();
  if (error) return <p className="error">{t(error)}</p>;
  if (!me) return <p>{t("Đang tải…")}</p>;
  return (
    <>
      <div className="page-heading"><div><p className="eyebrow">{t("Xin chào")}, {userDisplayName(me.user, t("bạn"))}</p><h1>{me.household?.name || t("Hộ gia đình")}</h1></div></div>
      {me.household ? (
        <HouseholdView household={me.household} onChange={reload} />
      ) : (
        <Setup onDone={reload} />
      )}
    </>
  );
}
