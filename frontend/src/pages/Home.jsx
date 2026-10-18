import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useMe } from "../useMe";

function Setup({ onDone }) {
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
      <p>Bạn chưa thuộc hộ nào.</p>
      <div className="card">
        <h3>Tạo hộ mới</h3>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Tên hộ, ví dụ: Nhà Kiên" />
        <button onClick={() => run(() => api("/api/households", { method: "POST", body: { name } }))}>Tạo hộ</button>
      </div>
      <div className="card">
        <h3>Tham gia bằng mã mời</h3>
        <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="Mã mời 8 ký tự" />
        <button onClick={() => run(() => api("/api/households/join", { method: "POST", body: { invite_code: code } }))}>
          Tham gia
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </>
  );
}

function HouseholdView({ household, onChange }) {
  const [members, setMembers] = useState([]);
  const [error, setError] = useState(null);
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
    try {
      await fn();
      await load();
      onChange();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div className="card">
      <h3>{household.name}</h3>
      <p>Vai trò của bạn: <b>{isOwner ? "Chủ hộ" : "Thành viên"}</b></p>
      {isOwner && (
        <p>
          Mã mời: <code>{household.invite_code}</code>{" "}
          <button onClick={() => act(() => api(`/api/households/${household.id}/invite-code`, { method: "POST" }))}>
            Đổi mã
          </button>
        </p>
      )}
      <ul>
        {members.map((m) => (
          <li key={m.id}>
            {m.display_name} ({m.email}) - {m.role === "owner" ? "Chủ hộ" : "Thành viên"}{" "}
            {isOwner && m.role !== "owner" && (
              <button onClick={() => act(() => api(`/api/households/${household.id}/members/${m.id}`, { method: "DELETE" }))}>
                Xóa
              </button>
            )}
          </li>
        ))}
      </ul>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

export default function Home() {
  const { me, error, reload } = useMe();
  if (error) return <p className="error">{error}</p>;
  if (!me) return <p>Đang tải...</p>;
  return (
    <>
      <p>Xin chào, <b>{me.user.email}</b></p>
      {me.household ? (
        <HouseholdView household={me.household} onChange={reload} />
      ) : (
        <Setup onDone={reload} />
      )}
    </>
  );
}