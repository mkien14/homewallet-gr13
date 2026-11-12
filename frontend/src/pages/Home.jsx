import { useCallback, useEffect, useRef, useState } from "react";
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

function LeaveHouseholdDialog({ leaving, error, onCancel, onConfirm, onRefresh }) {
  const { t } = usePreferences();
  const dialogRef = useRef(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    dialog.showModal();
    return () => { if (dialog.open) dialog.close(); };
  }, []);

  return (
    <dialog ref={dialogRef} className="confirm-dialog" aria-labelledby="leave-household-title" aria-describedby="leave-household-description" onCancel={(event) => { event.preventDefault(); if (!leaving) onCancel(); }}>
      <div className="confirm-dialog-icon" aria-hidden="true">!</div>
      <h2 id="leave-household-title">{t("Rời hộ gia đình?")}</h2>
      <p id="leave-household-description">{t("Bạn có chắc muốn rời hộ này? Các giao dịch và hóa đơn đã tạo vẫn thuộc hộ.")}</p>
      {error && <div role="alert"><p className="error">{t(error)}</p><p>{t("Nếu không rõ thao tác đã hoàn tất, hãy tải lại trạng thái trước khi thử lại.")}</p><button type="button" className="button-secondary" onClick={onRefresh} disabled={leaving}>{t("Tải lại trạng thái")}</button></div>}
      <div className="confirm-dialog-actions">
        <button type="button" className="button-secondary" onClick={onCancel} disabled={leaving} autoFocus>{t("Hủy")}</button>
        <button type="button" className="confirm-delete" onClick={onConfirm} disabled={leaving}>{t(leaving ? "Đang rời hộ…" : "Rời hộ")}</button>
      </div>
    </dialog>
  );
}

function HouseholdView({ household, onChange, onLeave }) {
  const { t } = usePreferences();
  const [members, setMembers] = useState([]);
  const [error, setError] = useState(null);
  const [copying, setCopying] = useState(false);
  const [copyFeedback, setCopyFeedback] = useState(null);
  const [leaving, setLeaving] = useState(false);
  const leavingRef = useRef(false);
  const [leaveError, setLeaveError] = useState(null);
  const [leaveDialogOpen, setLeaveDialogOpen] = useState(false);
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

  async function leaveHousehold() {
    if (household.role !== "member" || leavingRef.current) return;
    leavingRef.current = true;
    setLeaving(true);
    setLeaveError(null);
    try {
      await api(`/api/households/${household.id}/members/me`, { method: "DELETE" });
      onLeave();
    } catch (e) {
      setLeaveError(e.status === 404
        ? "Không tìm thấy thao tác rời hộ hoặc trạng thái thành viên đã thay đổi. Hãy tải lại trạng thái; nếu vẫn là thành viên, kiểm tra backend đã được cập nhật."
        : e.message);
    } finally {
      leavingRef.current = false;
      setLeaving(false);
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
          {household.role === "member" && <button type="button" className="button-danger" onClick={() => { setLeaveError(null); setLeaveDialogOpen(true); }}>{t("Rời hộ")}</button>}
        </section>
        <section className="card">
          <h2>{t("Quyền trong hộ")}</h2>
          <p><span className="household-check" aria-hidden="true">✓</span> &nbsp;{t("Theo dõi chi tiêu chung")}</p>
          <p><span className="household-check" aria-hidden="true">✓</span> &nbsp;{t("Kiểm tra hóa đơn")}</p>
          <p><span className="household-check" aria-hidden="true">✓</span> &nbsp;{t("Xem ngân sách gia đình")}</p>
        </section>
      </aside>
      {leaveDialogOpen && <LeaveHouseholdDialog leaving={leaving} error={leaveError} onCancel={() => setLeaveDialogOpen(false)} onConfirm={leaveHousehold} onRefresh={onChange} />}
    </div>
  );

}

export default function Home() {
  const { t } = usePreferences();
  const { me, error, reload, clearHousehold } = useMe();
  const [leftHousehold, setLeftHousehold] = useState(false);
  if (error) return <p className="error">{t(error)}</p>;
  if (!me) return <p>{t("Đang tải…")}</p>;
  return (
    <>
      <div className="page-heading"><div><p className="eyebrow">{t("Xin chào")}, {userDisplayName(me.user, t("bạn"))}</p><h1>{me.household?.name || t("Hộ gia đình")}</h1></div></div>
      {leftHousehold && !me.household && <p className="notice success" role="status">{t("Bạn đã rời hộ. Bạn có thể tạo hộ mới hoặc tham gia hộ khác.")}</p>}
      {me.household ? (
        <HouseholdView household={me.household} onChange={reload} onLeave={() => { clearHousehold(); setLeftHousehold(true); }} />
      ) : (
        <Setup onDone={() => { setLeftHousehold(false); reload(); }} />
      )}
    </>
  );
}
