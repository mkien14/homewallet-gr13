import { useCallback, useEffect, useRef, useState } from "react";
import { config } from "./config.js";
import { authService } from "./auth/service.js";
import { api } from "./api.js";
import {
  compressReceiptImage,
  formatBytes,
  validateReceiptFile,
} from "./image.js";

const nav = [
  { path: "/", label: "Bắt đầu", icon: "home" },
  { path: "/households", label: "Hộ gia đình", icon: "people" },
  { path: "/upload", label: "Tải hóa đơn", icon: "receipt" },
];
const goTo = (path) => window.location.replace(path);

// Household selection is optional; disabled browser storage must not crash the app.
function readHouseholdSelection() {
  try {
    return sessionStorage.getItem("homewallet.householdId") || "";
  } catch {
    return "";
  }
}
function storeHouseholdSelection(id) {
  try {
    if (id) sessionStorage.setItem("homewallet.householdId", String(id));
    else sessionStorage.removeItem("homewallet.householdId");
  } catch {
    /* Keep selection in memory when browser storage is unavailable. */
  }
}

function Icon({ name, size = 22, ...props }) {
  const paths = {
    home: (
      <>
        <path d="m3 10 9-7 9 7v10H3Z" />
        <path d="M9 20v-7h6v7" />
      </>
    ),
    people: (
      <>
        <circle cx="9" cy="8" r="3" />
        <path d="M3 21v-3a6 6 0 0 1 12 0v3M16 5a3 3 0 0 1 0 6M18 15a5 5 0 0 1 3 5" />
      </>
    ),
    receipt: (
      <>
        <path d="M5 3h14v19l-3-2-4 2-4-2-3 2Z" />
        <path d="M9 8h6M9 12h6M9 16h3" />
      </>
    ),
    upload: (
      <>
        <path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5" />
      </>
    ),
    arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
    check: <path d="m5 12 4 4L19 6" />,
    shield: (
      <>
        <path d="M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6Z" />
        <path d="m8 12 3 3 5-6" />
      </>
    ),
    logout: (
      <>
        <path d="M10 3H4v18h6M9 12h12m-4-4 4 4-4 4" />
      </>
    ),
    image: (
      <>
        <rect x="3" y="3" width="18" height="18" rx="3" />
        <circle cx="8" cy="8" r="1" />
        <path d="m3 17 6-6 4 4 3-3 5 5" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {paths[name] || paths.receipt}
    </svg>
  );
}

function Notice({ children, kind = "error" }) {
  if (!children) return null;
  return (
    <div
      className={`notice notice-${kind}`}
      role={kind === "error" ? "alert" : "status"}
    >
      {children}
    </div>
  );
}

function Callback({ auth, navigate }) {
  const callbackUrl = useRef(window.location.href);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    // Keep the code only in memory while the OIDC client validates its saved state.
    window.history.replaceState(null, "", window.location.pathname);
    auth
      .completeLogin(callbackUrl.current)
      .then(({ returnTo }) => {
        if (active) navigate(returnTo);
      })
      .catch((err) => {
        if (active)
          setError(
            err.message || "Không thể hoàn tất đăng nhập. Vui lòng thử lại.",
          );
      });
    return () => {
      active = false;
    };
  }, [auth, navigate]);
  return (
    <main className="callback-page">
      <a className="brand" href="/">
        <span className="brand-mark">
          <Icon name="home" />
        </span>
        HomeWallet<span className="brand-dot">.</span>
      </a>
      <div className="callback-card">
        <span className="round-icon">
          <Icon name="shield" size={30} />
        </span>
        <h1>{error ? "Chưa thể đăng nhập" : "Đang hoàn tất đăng nhập"}</h1>
        <Notice>{error}</Notice>
        {error ? (
          <a className="button primary" href="/">
            Quay về và thử lại
          </a>
        ) : (
          <p role="status">Đang xác nhận phiên đăng nhập của bạn…</p>
        )}
      </div>
    </main>
  );
}

function Welcome({ user, login, signingIn, settings }) {
  return (
    <section className="welcome-grid">
      <div className="welcome-copy">
        <span className="eyebrow">MỘT KHÔNG GIAN · CẢ GIA ĐÌNH</span>
        <h1>
          Chi tiêu rõ ràng.
          <br />
          <span>Cả nhà an tâm.</span>
        </h1>
        <p className="lead">
          Gom hóa đơn về một nơi, cùng ghi nhận những khoản chi và dành thời
          gian cho điều quan trọng hơn.
        </p>
        {user ? (
          <a className="button primary" href="/households">
            Đến hộ gia đình <Icon name="arrow" size={19} />
          </a>
        ) : (
          <button
            className="button primary"
            onClick={login}
            disabled={signingIn || !settings.isAuthConfigured}
          >
            {signingIn ? "Đang chuyển đến đăng nhập…" : "Đăng nhập để bắt đầu"}
            <Icon name="arrow" size={19} />
          </button>
        )}
        {!user && !settings.isAuthConfigured && (
          <p className="configuration-note">
            Đăng nhập chưa sẵn sàng. Quản trị viên cần hoàn tất cấu hình kết nối
            Cognito.
          </p>
        )}
        <div className="trust-note">
          <Icon name="shield" size={18} />
          <span>Đăng nhập an toàn qua Amazon Cognito</span>
        </div>
      </div>
      <div
        className="welcome-art"
        aria-label="Minh họa quản lý hóa đơn gia đình"
      >
        <span className="art-spark spark-one">✳</span>
        <span className="art-spark spark-two">✦</span>
        <div className="art-orbit" />
        <div className="paper-receipt">
          <div className="paper-logo">
            <Icon name="home" size={28} />
          </div>
          <strong>Những khoản chi nhỏ</strong>
          <span>Góp nên câu chuyện của cả nhà</span>
          <div className="paper-dash" />
          <div className="paper-row">
            <i />
            <b />
          </div>
          <div className="paper-row">
            <i />
            <b />
          </div>
          <div className="paper-row">
            <i />
            <b />
          </div>
          <div className="paper-dash" />
          <div className="paper-total">
            <span>Một nơi để cùng theo dõi</span>
            <Icon name="check" />
          </div>
          <div className="paper-barcode" />
        </div>
        <div className="art-chip">
          <span className="chip-check">
            <Icon name="check" size={17} />
          </span>
          Bạn luôn được kiểm tra trước khi lưu
        </div>
        <small className="art-caption">Minh họa luồng hóa đơn</small>
      </div>
    </section>
  );
}

function Journey({ current }) {
  return (
    <ol className="journey" aria-label="Các bước bắt đầu">
      {["Đăng nhập", "Chọn hộ gia đình", "Tải hóa đơn"].map((label, i) => (
        <li
          key={label}
          className={i < current ? "complete" : i === current ? "current" : ""}
          aria-current={i === current ? "step" : undefined}
        >
          <span>
            {i < current ? <Icon name="check" size={15} /> : `0${i + 1}`}
          </span>
          {label}
        </li>
      ))}
    </ol>
  );
}

function HouseholdForms({ client, onSaved, onAuthError }) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const active = useRef(true);
  const submitting = useRef(false);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  async function submit(event, kind) {
    event.preventDefault();
    if (submitting.current) return;
    const value = (kind === "create" ? name : code).trim();
    if (!value) {
      setError("Vui lòng nhập đầy đủ thông tin.");
      return;
    }
    submitting.current = true;
    setBusy(kind);
    setError("");
    setSuccess("");
    try {
      const household =
        kind === "create"
          ? await client.createHousehold(value)
          : await client.joinHousehold(value);
      if (!active.current) return;
      setName("");
      setCode("");
      setSuccess(
        kind === "create" ? "Đã tạo hộ gia đình." : "Đã tham gia hộ gia đình.",
      );
      onSaved(household);
    } catch (err) {
      if (active.current) {
        setError(err.message || "Chưa thể lưu hộ gia đình.");
        onAuthError(err);
      }
    } finally {
      submitting.current = false;
      if (active.current) setBusy("");
    }
  }
  return (
    <>
      <Notice>{error}</Notice>
      <Notice kind="success">{success}</Notice>
      <div className="household-forms">
        <form className="card" onSubmit={(event) => submit(event, "create")}>
          <span className="small-icon">
            <Icon name="plus" />
          </span>
          <h2>Tạo tổ ấm của bạn</h2>
          <p>
            Mở không gian chi tiêu chung và mời các thành viên cùng tham gia.
          </p>
          <label htmlFor="household-name">Tên hộ gia đình</label>
          <input
            id="household-name"
            placeholder="Ví dụ: Nhà mình"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={100}
            required
            disabled={!!busy}
          />
          <button className="button primary" disabled={!!busy}>
            {busy === "create" ? "Đang tạo…" : "Tạo hộ gia đình"}
            <Icon name="arrow" size={18} />
          </button>
        </form>
        <form className="card" onSubmit={(event) => submit(event, "join")}>
          <span className="small-icon peach">
            <Icon name="people" />
          </span>
          <h2>Đã có lời mời?</h2>
          <p>Nhập mã mời được chủ hộ chia sẻ để cùng theo dõi chi tiêu.</p>
          <label htmlFor="invite-code">Mã mời</label>
          <input
            id="invite-code"
            placeholder="Nhập mã mời của bạn"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            maxLength={16}
            required
            disabled={!!busy}
            autoCapitalize="none"
            autoComplete="off"
            spellCheck="false"
          />
          <button className="button secondary" disabled={!!busy}>
            {busy === "join" ? "Đang tham gia…" : "Tham gia hộ gia đình"}
            <Icon name="arrow" size={18} />
          </button>
        </form>
      </div>
    </>
  );
}

function ReceiptUpload({ household, client, onAuthError }) {
  const [file, setFile] = useState(null);
  const [originalSize, setOriginalSize] = useState(0);
  const [preview, setPreview] = useState("");
  const [phase, setPhase] = useState("empty");
  const [error, setError] = useState("");
  const [receiptId, setReceiptId] = useState(null);
  const [plan, setPlan] = useState(null);
  const [creationUncertain, setCreationUncertain] = useState(false);
  const [dragging, setDragging] = useState(false);
  const input = useRef(null);
  const version = useRef(0);
  const abort = useRef(null);
  const active = useRef(true);
  const busy = phase === "preparing" || phase === "uploading";
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
      version.current++;
      abort.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (!file) {
      setPreview("");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  async function selectFile(candidate) {
    if (!candidate || busy) return;
    const request = ++version.current;
    setError("");
    setPlan(null);
    setCreationUncertain(false);
    setReceiptId(null);
    setFile(null);
    try {
      validateReceiptFile(candidate);
      setPhase("preparing");
      setOriginalSize(candidate.size);
      const prepared = await compressReceiptImage(candidate);
      if (active.current && version.current === request) {
        setFile(prepared);
        setPhase("ready");
      }
    } catch (err) {
      if (active.current && version.current === request) {
        setError(err.message || "Không thể đọc ảnh này.");
        setPhase("empty");
      }
    }
  }
  async function submit(event) {
    event.preventDefault();
    if (
      !file ||
      busy ||
      phase === "success" ||
      creationUncertain ||
      (receiptId && !plan)
    )
      return;
    setPhase("uploading");
    setError("");
    abort.current = new AbortController();
    try {
      const result = plan
        ? await client.resumeReceiptUpload({
            plan,
            file,
            signal: abort.current.signal,
          })
        : await client.uploadReceipt({
            householdId: household.id,
            file,
            signal: abort.current.signal,
          });
      if (active.current) {
        setReceiptId(result.receipt_id);
        setPlan(null);
        setPhase("success");
      }
    } catch (err) {
      if (active.current) {
        setError(err.message || "Tải ảnh chưa thành công. Vui lòng thử lại.");
        setPlan(err.uploadPlan || plan);
        setCreationUncertain(Boolean(err.creationUncertain));
        setReceiptId(err.receiptId || null);
        setPhase("error");
        onAuthError(err);
      }
    }
  }
  function reset() {
    version.current++;
    setFile(null);
    setPlan(null);
    setCreationUncertain(false);
    setReceiptId(null);
    setError("");
    setPhase("empty");
    if (input.current) input.current.value = "";
  }
  return (
    <div className="upload-layout">
      <form className="card upload-card" onSubmit={submit}>
        <div className="card-heading">
          <div>
            <span className="eyebrow">GHI NHẬN CHI TIÊU</span>
            <h2>Một bức ảnh, bớt một lần nhập tay.</h2>
          </div>
          <span className="tag">{household.name}</span>
        </div>
        <p className="card-intro">
          Ảnh được tối ưu ngay trên thiết bị trước khi tải lên. Bạn sẽ kiểm tra
          kết quả nhận dạng trước khi xác nhận giao dịch.
        </p>
        <input
          ref={input}
          id="receipt-file"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="file-input"
          aria-label="Chọn ảnh hóa đơn"
          disabled={busy || phase === "success"}
          onChange={(e) => {
            selectFile(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
        {!file && (
          <div
            className={`dropzone ${dragging ? "dragging" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              if (!busy) setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              selectFile(e.dataTransfer.files?.[0]);
            }}
          >
            <span className="upload-symbol">
              <Icon name="upload" size={32} />
            </span>
            <h3>
              {phase === "preparing"
                ? "Đang tối ưu ảnh…"
                : "Thả ảnh hóa đơn vào đây"}
            </h3>
            <p>hoặc chọn ảnh từ thiết bị của bạn</p>
            <button
              type="button"
              className="button secondary"
              onClick={() => input.current?.click()}
              disabled={busy}
            >
              Chọn ảnh hóa đơn
            </button>
            <small>JPG, PNG, WebP · Ảnh gốc tối đa 15 MiB</small>
          </div>
        )}
        {file && (
          <div className="file-preview">
            <div className="preview-image">
              {preview && (
                <img src={preview} alt="Ảnh hóa đơn đã tối ưu để tải lên" />
              )}
            </div>
            <div className="file-details">
              <span className="small-icon">
                <Icon name="image" />
              </span>
              <strong>{file.name}</strong>
              <span>
                {formatBytes(originalSize)} → {formatBytes(file.size)}
              </span>
              <span className="prepared-label">
                <Icon name="check" size={15} />
                Đã tối ưu · JPEG · tối đa 2 MiB
              </span>
              {!busy && phase !== "success" && (
                <button className="text-button" type="button" onClick={reset}>
                  Chọn ảnh khác
                </button>
              )}
            </div>
          </div>
        )}
        <Notice>{error}</Notice>
        {creationUncertain && (
          <p className="configuration-note">
            Kết nối bị gián đoạn khi tạo hóa đơn. Hệ thống có thể đã nhận yêu
            cầu; cần kiểm tra bản ghi trên máy chủ trước khi tải lại để tránh
            tạo trùng.
          </p>
        )}
        {phase === "error" && receiptId && !plan && (
          <p className="configuration-note">
            Hóa đơn {receiptId} đã được tạo nhưng chưa có thông tin tải lên hợp
            lệ. Vui lòng liên hệ quản trị viên để tiếp tục với cùng mã hóa đơn.
          </p>
        )}
        {phase === "uploading" && (
          <div className="upload-status" role="status">
            <span className="spinner" />
            Đang tải ảnh lên, vui lòng giữ trang này mở…
            <button
              className="text-button"
              type="button"
              onClick={() => abort.current?.abort()}
            >
              Dừng tải
            </button>
          </div>
        )}
        {phase === "success" ? (
          <>
            <Notice kind="success">
              Đã tải ảnh thành công. Mã hóa đơn: {receiptId}. Ảnh đang chờ hệ
              thống xử lý; giao dịch chưa được xác nhận.
            </Notice>
            <button className="button secondary" type="button" onClick={reset}>
              Tải hóa đơn khác
              <Icon name="plus" size={18} />
            </button>
          </>
        ) : (
          <div className="upload-footer">
            <span>
              <Icon name="shield" size={16} />
              Ảnh thuộc hộ gia đình bạn đã chọn
            </span>
            <button
              className="button primary"
              disabled={
                !file || busy || creationUncertain || (!!receiptId && !plan)
              }
            >
              {phase === "uploading"
                ? "Đang tải…"
                : plan
                  ? "Thử tải lại ảnh"
                  : "Tải hóa đơn lên"}
              <Icon name="arrow" size={18} />
            </button>
          </div>
        )}
      </form>
      <aside className="upload-tips">
        <span className="eyebrow">MẸO NHỎ</span>
        <h3>
          Ảnh rõ hơn,
          <br />
          kết quả tốt hơn.
        </h3>
        <ul>
          <li>Đặt hóa đơn trên bề mặt phẳng, đủ sáng.</li>
          <li>Chụp trọn hóa đơn, giữ rõ ngày và tổng tiền.</li>
          <li>Hạn chế bóng đổ và ảnh bị nhòe.</li>
        </ul>
        <div className="tip-note">
          <Icon name="shield" />
          <p>
            Ảnh được tải vào vùng lưu trữ riêng tư. Thông tin nhận dạng luôn cần
            bạn kiểm tra lại.
          </p>
        </div>
      </aside>
    </div>
  );
}

export default function App({
  auth = authService,
  client = api,
  settings = config,
  initialPath = window.location.pathname,
  navigate = goTo,
}) {
  const path = initialPath.replace(/\/+$/, "") || "/";
  const [user, setUser] = useState(null);
  const [booting, setBooting] = useState(path !== "/auth/callback");
  const [signingIn, setSigningIn] = useState(false);
  const [error, setError] = useState("");
  const [households, setHouseholds] = useState([]);
  const [householdLoading, setHouseholdLoading] = useState(false);
  const [householdError, setHouseholdError] = useState("");
  const [loadVersion, setLoadVersion] = useState(0);
  const [selectedId, setSelectedId] = useState(readHouseholdSelection);
  useEffect(() => {
    if (path === "/auth/callback") return;
    let active = true;
    let identity;
    let sessionEventReceived = false;
    const receiveUser = (value) => {
      const nextIdentity = value?.profile?.sub;
      if (identity !== undefined && identity !== nextIdentity) {
        setHouseholds([]);
        setSelectedId("");
        storeHouseholdSelection("");
      }
      identity = nextIdentity;
      setUser(value);
      if (!value) {
        setHouseholds([]);
        setSelectedId("");
        storeHouseholdSelection("");
      }
    };
    auth
      .getUser()
      .then((value) => {
        if (active && !sessionEventReceived) receiveUser(value);
      })
      .catch((err) => {
        if (active)
          setError(err.message || "Không thể khôi phục phiên đăng nhập.");
      })
      .finally(() => {
        if (active) setBooting(false);
      });
    const unsubscribe = auth.subscribe((value) => {
      if (active) {
        sessionEventReceived = true;
        receiveUser(value);
      }
    });
    return () => {
      active = false;
      unsubscribe();
    };
  }, [auth, path]);
  const userId = user?.profile?.sub;
  const onAuthError = useCallback((err) => {
    if (err.status === 401 || err.name === "AuthError") {
      setUser(null);
      setHouseholds([]);
      setSelectedId("");
      storeHouseholdSelection("");
      setError("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
    }
  }, []);
  useEffect(() => {
    if (!userId || path === "/auth/callback") return;
    let active = true;
    setHouseholdLoading(true);
    setHouseholdError("");
    client
      .listHouseholds()
      .then((items) => {
        if (active) setHouseholds(items);
      })
      .catch((err) => {
        if (active) {
          setHouseholdError(
            err.message || "Không thể tải danh sách hộ gia đình.",
          );
          onAuthError(err);
        }
      })
      .finally(() => {
        if (active) setHouseholdLoading(false);
      });
    return () => {
      active = false;
    };
  }, [client, userId, path, loadVersion, onAuthError]);
  const selected =
    households.find((item) => String(item.id) === selectedId) || null;
  function chooseHousehold(id) {
    setSelectedId(String(id));
    storeHouseholdSelection(id);
  }
  async function login() {
    setSigningIn(true);
    setError("");
    try {
      await auth.login(nav.some((item) => item.path === path) ? path : "/");
    } catch (err) {
      setError(err.message || "Không thể mở trang đăng nhập.");
    } finally {
      setSigningIn(false);
    }
  }
  async function logout() {
    setError("");
    try {
      await auth.logout();
    } catch {
      setError(
        "Đã xóa phiên trên thiết bị. Chưa thể hoàn tất đăng xuất tại Cognito; vui lòng thử lại.",
      );
    }
  }
  function savedHousehold(household) {
    setHouseholds((items) => [
      ...items.filter((item) => String(item.id) !== String(household.id)),
      household,
    ]);
    chooseHousehold(household.id);
  }
  if (path === "/auth/callback")
    return <Callback auth={auth} navigate={navigate} />;
  const page = nav.find((item) => item.path === path);
  const userName = user?.profile?.name || user?.profile?.email || "Thành viên";
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Đến nội dung chính
      </a>
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="HomeWallet trang chủ">
          <span className="brand-mark">
            <Icon name="home" />
          </span>
          HomeWallet<span className="brand-dot">.</span>
        </a>
        <div className="sidebar-label">KHÔNG GIAN GIA ĐÌNH</div>
        <nav aria-label="Điều hướng chính">
          {nav.map((item) => (
            <a
              key={item.path}
              href={item.path}
              className={`nav-link ${path === item.path ? "active" : ""}`}
              aria-current={path === item.path ? "page" : undefined}
            >
              <Icon name={item.icon} />
              {item.label}
              {path === item.path && <span className="nav-dot" />}
            </a>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <Icon name="people" size={28} />
            <p>
              Cùng nhau ghi nhận.
              <br />
              <strong>Cùng nhau vun vén.</strong>
            </p>
          </div>
          <span className="sidebar-foot">HOMEWALLET · NHÓM T13</span>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <span className="breadcrumb">
            Không gian của bạn <span>/</span>{" "}
            <strong>{page?.label || "Trang không tồn tại"}</strong>
          </span>
          {user ? (
            <div className="user-menu">
              <span className="avatar">
                {String(userName).slice(0, 1).toLocaleUpperCase("vi-VN")}
              </span>
              <span className="user-name">{userName}</span>
              <button
                className="icon-button"
                onClick={logout}
                aria-label="Đăng xuất"
                title="Đăng xuất"
              >
                <Icon name="logout" size={19} />
              </button>
            </div>
          ) : (
            <span className="private-label">
              <Icon name="shield" size={16} />
              Dành riêng cho gia đình
            </span>
          )}
        </header>
        <main id="main" className="content">
          <Notice>{error}</Notice>
          {booting ? (
            <div className="loading-state" role="status">
              <span className="spinner" />
              Đang kiểm tra phiên đăng nhập…
            </div>
          ) : !page ? (
            <section className="card empty-state">
              <h1>Không tìm thấy trang này</h1>
              <a className="button primary" href="/">
                Về trang bắt đầu
              </a>
            </section>
          ) : (
            <>
              {path === "/" ? (
                <>
                  <Welcome
                    user={user}
                    login={login}
                    signingIn={signingIn}
                    settings={settings}
                  />
                  <section
                    className="features"
                    aria-label="Bắt đầu với HomeWallet"
                  >
                    <article>
                      <span className="feature-number">01</span>
                      <h2>Một hộ, cùng kết nối</h2>
                      <p>
                        Tạo hộ gia đình hoặc tham gia bằng mã mời để bắt đầu
                        quản lý chi tiêu chung.
                      </p>
                    </article>
                    <article>
                      <span className="feature-number">02</span>
                      <h2>Gọn nhẹ từng hóa đơn</h2>
                      <p>
                        Chọn ảnh, tối ưu dung lượng ngay trên thiết bị và tải
                        lên vùng lưu trữ riêng tư.
                      </p>
                    </article>
                    <article>
                      <span className="feature-number">03</span>
                      <h2>Bạn là người xác nhận</h2>
                      <p>
                        Dữ liệu nhận dạng là bản nháp. Hãy kiểm tra trước khi
                        ghi nhận khoản chi.
                      </p>
                    </article>
                  </section>
                </>
              ) : (
                <>
                  <div className="page-heading">
                    <span className="eyebrow">CÙNG NHÀ MÌNH</span>
                    <h1>
                      {path === "/households"
                        ? "Không gian của gia đình"
                        : "Thêm một hóa đơn mới"}
                    </h1>
                    <p>
                      {path === "/households"
                        ? "Chọn nơi bạn muốn ghi nhận chi tiêu, hoặc bắt đầu một hộ gia đình mới."
                        : "Giữ những khoản chi ngăn nắp, bắt đầu từ một bức ảnh."}
                    </p>
                  </div>
                  <Journey current={!user ? 0 : !selected ? 1 : 2} />
                  {!user ? (
                    <section className="card empty-state">
                      <span className="round-icon">
                        <Icon name="shield" size={30} />
                      </span>
                      <h2>Đăng nhập để tiếp tục</h2>
                      <p>
                        Truy cập an toàn vào hộ gia đình và hóa đơn của bạn.
                      </p>
                      <button
                        className="button primary"
                        onClick={login}
                        disabled={signingIn || !settings.isAuthConfigured}
                      >
                        Đăng nhập qua Cognito
                        <Icon name="arrow" size={18} />
                      </button>
                      {!settings.isAuthConfigured && (
                        <p className="configuration-note">
                          Đăng nhập chưa sẵn sàng. Vui lòng liên hệ quản trị
                          viên.
                        </p>
                      )}
                    </section>
                  ) : (
                    <>
                      {householdLoading && (
                        <p className="loading-inline" role="status">
                          <span className="spinner" />
                          Đang tải hộ gia đình…
                        </p>
                      )}
                      {householdError && (
                        <div className="load-error">
                          <Notice>{householdError}</Notice>
                          <button
                            className="button secondary"
                            onClick={() => setLoadVersion((value) => value + 1)}
                          >
                            Thử tải lại danh sách
                          </button>
                        </div>
                      )}
                      {path === "/households" && (
                        <>
                          <section
                            className="household-list"
                            aria-label="Hộ gia đình của bạn"
                          >
                            {households.map((household) => (
                              <button
                                key={household.id}
                                className={`household-option ${String(household.id) === selectedId ? "selected" : ""}`}
                                onClick={() => chooseHousehold(household.id)}
                                aria-pressed={
                                  String(household.id) === selectedId
                                }
                              >
                                <span className="round-icon">
                                  <Icon name="home" />
                                </span>
                                <span>
                                  <strong>{household.name}</strong>
                                  <small>
                                    {household.role === "OWNER"
                                      ? "Chủ hộ"
                                      : "Thành viên"}{" "}
                                    · {household.currency || "VND"}
                                  </small>
                                </span>
                                {String(household.id) === selectedId && (
                                  <Icon name="check" />
                                )}
                              </button>
                            ))}
                          </section>
                          {!householdLoading &&
                            !householdError &&
                            households.length === 0 && (
                              <p className="empty-household">
                                Bạn chưa có hộ gia đình. Tạo hộ mới hoặc nhập mã
                                mời bên dưới.
                              </p>
                            )}
                          {selected && (
                            <div className="selected-summary">
                              <span>
                                Đang chọn <strong>{selected.name}</strong>
                                {selected.role === "OWNER" &&
                                  selected.invite_code && (
                                    <span className="invite-display">
                                      {" "}
                                      · Mã mời:{" "}
                                      <code>{selected.invite_code}</code>
                                    </span>
                                  )}
                              </span>
                              <a className="button primary" href="/upload">
                                Tải hóa đơn
                                <Icon name="arrow" size={18} />
                              </a>
                            </div>
                          )}
                          <HouseholdForms
                            key={userId}
                            client={client}
                            onSaved={savedHousehold}
                            onAuthError={onAuthError}
                          />
                        </>
                      )}
                      {path === "/upload" &&
                        !householdError &&
                        !householdLoading && (
                          <>
                            {selected ? (
                              <>
                                <div className="household-picker">
                                  <label htmlFor="active-household">
                                    Hộ gia đình nhận hóa đơn
                                  </label>
                                  <select
                                    id="active-household"
                                    value={selectedId}
                                    onChange={(event) =>
                                      chooseHousehold(event.target.value)
                                    }
                                  >
                                    {households.map((item) => (
                                      <option
                                        key={item.id}
                                        value={String(item.id)}
                                      >
                                        {item.name}
                                      </option>
                                    ))}
                                  </select>
                                </div>
                                <ReceiptUpload
                                  key={selectedId}
                                  household={selected}
                                  client={client}
                                  onAuthError={onAuthError}
                                />
                              </>
                            ) : (
                              <section className="card empty-state">
                                <span className="round-icon">
                                  <Icon name="people" size={30} />
                                </span>
                                <h2>Chọn hộ gia đình trước khi tải ảnh</h2>
                                <p>
                                  Hóa đơn cần được gắn với hộ gia đình mà bạn là
                                  thành viên.
                                </p>
                                <a
                                  className="button primary"
                                  href="/households"
                                >
                                  Chọn hoặc tạo hộ gia đình
                                  <Icon name="arrow" size={18} />
                                </a>
                              </section>
                            )}
                          </>
                        )}
                    </>
                  )}
                </>
              )}
            </>
          )}
          <footer className="page-footer">
            <span>HomeWallet</span>
            <span>Mỗi khoản chi, một chút chăm lo.</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
