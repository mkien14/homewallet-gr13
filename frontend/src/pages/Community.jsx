import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { getAccessToken } from "../auth/auth";
import { USE_MOCK } from "../mode";
import { usePreferences } from "../preferences";

function isCognitoAdmin(token) {
  try {
    if (!token) return false;
    const encoded = token.split(".")[1].replace(/-/gu, "+").replace(/_/gu, "/");
    const payload = JSON.parse(atob(`${encoded}${"=".repeat((4 - encoded.length % 4) % 4)}`));
    return Array.isArray(payload["cognito:groups"]) && payload["cognito:groups"].includes("homewallet-dev-admins");
  } catch { return false; }
}

function friendlyError(err) {
  if (err?.code === "FORBIDDEN" || err?.status === 403) return "Bạn không có quyền quản trị cộng đồng.";
  if (err?.code === "NETWORK_ERROR") return "Không kết nối được máy chủ. Hãy kiểm tra mạng rồi thử lại.";
  if (err?.status === 404 && String(err?.path || "").includes("community")) return "API cộng đồng chưa được triển khai trên môi trường này.";
  if (err?.code === "VALIDATION") return "Nội dung chưa hợp lệ. Hãy kiểm tra tiêu đề và nội dung bài viết.";
  return "Không thể tải hoặc cập nhật bài viết. Hãy thử lại.";
}

function PostCard({ post, admin, onAction, busy, t, translateSample }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(post.title);
  const [body, setBody] = useState(post.body);
  const type = post.type === "budget_template" ? t("Mẫu ngân sách") : t("Mẹo tiết kiệm");
  return <article className="community-post card">
    <div className="community-post-meta"><span className="status-badge">{type}</span>{admin && <span className={`status-badge community-status-${post.status.toLowerCase()}`}>{t(post.status === "PENDING" ? "Chờ duyệt" : post.status === "HIDDEN" ? "Đã ẩn" : "Đã duyệt")}</span>}</div>
    {editing ? <div className="community-edit"><label className="field">{t("Tiêu đề")}<input value={title} maxLength={120} onChange={(event) => setTitle(event.target.value)} /></label><label className="field">{t("Nội dung")}<textarea value={body} maxLength={3000} rows={5} onChange={(event) => setBody(event.target.value)} /></label><div className="form-actions"><button type="button" disabled={busy} onClick={async () => { await onAction(post.id, { title, body }); setEditing(false); }}>{t("Lưu thay đổi")}</button><button type="button" className="button-secondary" onClick={() => setEditing(false)}>{t("Hủy")}</button></div></div> : <><h2>{translateSample && post.sample ? t(post.title) : post.title}</h2><p className="community-post-body">{translateSample && post.sample ? t(post.body) : post.body}</p></>}
    <small>{t("Đăng bởi")} {post.author || t("Thành viên")} · {post.updated_at ? new Intl.DateTimeFormat(document.documentElement.lang === "en" ? "en-US" : "vi-VN", { dateStyle: "medium" }).format(new Date(`${post.updated_at}${post.updated_at.endsWith("Z") ? "" : "Z"}`)) : ""}</small>
    {admin && <div className="community-actions">{!editing && <button type="button" className="button-secondary" onClick={() => setEditing(true)}>{t("Chỉnh sửa")}</button>}{post.status !== "APPROVED" && <button type="button" disabled={busy} onClick={() => onAction(post.id, { status: "APPROVED" })}>{t("Duyệt bài")}</button>}{post.status !== "HIDDEN" && <button type="button" className="button-secondary" disabled={busy} onClick={() => onAction(post.id, { status: "HIDDEN" })}>{t("Ẩn bài")}</button>}{post.status === "HIDDEN" && <button type="button" className="button-secondary" disabled={busy} onClick={() => onAction(post.id, { status: "PENDING" })}>{t("Đưa lại chờ duyệt")}</button>}</div>}
  </article>;
}

export default function Community() {
  const { t } = usePreferences();
  const [isAdmin, setIsAdmin] = useState(() => USE_MOCK && localStorage.getItem("hw.mock.communityAdmin") === "1");
  const [approved, setApproved] = useState([]);
  const [pending, setPending] = useState([]);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [type, setType] = useState("tip");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const mockAdmin = USE_MOCK && isAdmin;
  const load = useCallback(async () => {
    setLoading(true); setError(""); setPending([]);
    try {
      // Refresh the session before deriving visibility; the API remains authoritative.
      const admin = USE_MOCK ? mockAdmin : isCognitoAdmin(await getAccessToken());
      setIsAdmin(admin);
      const result = await api("/api/community/posts?status=APPROVED");
      setApproved(Array.isArray(result.items) ? result.items : []);
      if (admin) {
        const queue = await api("/api/admin/community/posts?status=PENDING");
        const hidden = await api("/api/admin/community/posts?status=HIDDEN");
        setPending([...(queue.items || []), ...(hidden.items || [])]);
      } else setPending([]);
    } catch (err) {
      if (!USE_MOCK && (err?.status === 401 || err?.status === 403)) setIsAdmin(false);
      setError(friendlyError(err));
    }
    finally { setLoading(false); }
  }, [mockAdmin]);
  useEffect(() => { queueMicrotask(() => { void load(); }); }, [load]);

  async function submit(event) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/community/posts", { method: "POST", body: { type, title, body } });
      setTitle(""); setBody(""); setNotice(t("Bài viết đã gửi và đang chờ admin duyệt.")); await load();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function adminAction(id, patch) {
    setBusy(true); setError(""); setNotice("");
    try { await api(`/api/admin/community/posts/${id}`, { method: "PATCH", body: patch }); setNotice(t("Đã cập nhật bài viết.")); await load(); }
    catch (err) { setError(friendlyError(err)); }
    finally { setBusy(false); }
  }

  async function toggleMockAdmin(event) {
    const next = event.target.checked;
    setBusy(true); setError("");
    try { await api("/api/mock/community/admin", { method: "POST", body: { enabled: next } }); localStorage.setItem("hw.mock.communityAdmin", next ? "1" : "0"); setIsAdmin(next); }
    catch (err) { setError(friendlyError(err)); }
    finally { setBusy(false); }
  }

  return <>
    <div className="page-heading"><div><p className="eyebrow">HomeWallet · {t("Cộng đồng")}</p><h1>{t("Mẹo tiết kiệm gia đình")}</h1><p>{t("Chia sẻ mẹo hữu ích và mẫu ngân sách đã được duyệt.")}</p></div><button className="button-secondary" type="button" onClick={load} disabled={loading}>{t("Làm mới")}</button></div>
    {USE_MOCK && <div className="notice mock-role-switch"><strong>{t("Chế độ demo")}</strong><span>{t("Chuyển vai trò chỉ thay đổi dữ liệu giả trên trình duyệt.")}</span><label><input type="checkbox" checked={isAdmin} onChange={toggleMockAdmin} disabled={busy} />{t("Xem như admin")}</label></div>}
    {isAdmin && !USE_MOCK && <p className="notice">{t("Quyền admin được đọc từ Cognito group. Máy chủ vẫn xác thực mọi thao tác.")}</p>}
    {notice && <p className="success" role="status">{notice}</p>}
    {error && <div className="notice error" role="alert"><p>{t(error)}</p><button type="button" className="button-secondary" onClick={load}>{t("Thử lại")}</button></div>}
    <div className="community-layout">
      <section className="community-feed"><div className="community-section-title"><h2>{t("Bài viết đã duyệt")}</h2><span className="status-badge">{approved.length}</span></div>
        {loading ? <p role="status">{t("Đang tải bài viết…")}</p> : approved.length ? approved.map((post) => <PostCard key={post.id} post={post} admin={isAdmin} onAction={adminAction} busy={busy} t={t} translateSample={USE_MOCK} />) : <div className="card empty-state"><h3>{t("Cộng đồng đang bắt đầu")}</h3><p>{t("Chưa có bài viết được duyệt. Bạn có thể gửi mẹo đầu tiên.")}</p></div>}
        {isAdmin && <><div className="community-section-title community-queue-title"><h2>{t("Hàng chờ quản trị")}</h2><span className="status-badge">{pending.length}</span></div>{pending.length ? pending.map((post) => <PostCard key={post.id} post={post} admin onAction={adminAction} busy={busy} t={t} translateSample={USE_MOCK} />) : <p className="empty-state">{t("Không có bài đang chờ hoặc đã ẩn.")}</p>}</>}
      </section>
      <aside className="card community-compose"><p className="eyebrow">{t("Chia sẻ với gia đình")}</p><h2>{t("Gửi bài viết")}</h2><p className="muted">{t("Bài mới sẽ ở trạng thái chờ duyệt và chỉ xuất hiện với mọi người sau khi được duyệt.")}</p>
        <form onSubmit={submit}><label className="field">{t("Loại bài viết")}<select value={type} onChange={(event) => setType(event.target.value)}><option value="tip">{t("Mẹo tiết kiệm")}</option><option value="budget_template">{t("Mẫu ngân sách")}</option></select></label><label className="field">{t("Tiêu đề")}<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={120} required /></label><label className="field">{t("Nội dung")}<textarea value={body} onChange={(event) => setBody(event.target.value)} rows={6} maxLength={3000} required /></label><small>{body.length}/3000</small><button type="submit" disabled={busy}>{busy ? t("Đang gửi…") : t("Gửi để duyệt")}</button></form>
      </aside>
    </div>
  </>;
}
