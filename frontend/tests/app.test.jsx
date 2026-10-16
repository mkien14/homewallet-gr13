import React, { StrictMode } from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/App.jsx";
import { compressReceiptImage } from "../src/image.js";

vi.mock("../src/image.js", () => ({
  validateReceiptFile: vi.fn((file) => {
    if (file.type !== "image/jpeg")
      throw new Error("Định dạng ảnh chưa được hỗ trợ.");
  }),
  compressReceiptImage: vi.fn(
    async () => new File(["compressed"], "receipt.jpg", { type: "image/jpeg" }),
  ),
  formatBytes: (size) => `${size} B`,
}));

const household = {
  id: "12",
  name: "Nhà mình",
  role: "OWNER",
  currency: "VND",
  invite_code: "INVITE12",
};
const loggedIn = { profile: { sub: "user-1", email: "test@example.com" } };
function makeAuth(user = loggedIn) {
  return {
    getUser: vi.fn().mockResolvedValue(user),
    subscribe: vi.fn(() => () => {}),
    login: vi.fn().mockResolvedValue(),
    logout: vi.fn().mockResolvedValue(),
    completeLogin: vi.fn().mockResolvedValue({ user, returnTo: "/upload" }),
  };
}
function makeClient() {
  return {
    listHouseholds: vi.fn().mockResolvedValue([household]),
    createHousehold: vi.fn().mockResolvedValue(household),
    joinHousehold: vi.fn().mockResolvedValue(household),
    uploadReceipt: vi.fn().mockResolvedValue({ receipt_id: "99" }),
    resumeReceiptUpload: vi.fn().mockResolvedValue({ receipt_id: "99" }),
  };
}
function show({
  auth = makeAuth(),
  client = makeClient(),
  path = "/households",
  settings = { isAuthConfigured: true },
  navigate = vi.fn(),
  strict = false,
} = {}) {
  const element = (
    <App
      auth={auth}
      client={client}
      settings={settings}
      initialPath={path}
      navigate={navigate}
    />
  );
  render(strict ? <StrictMode>{element}</StrictMode> : element);
  return { auth, client, navigate };
}
async function prepareUpload() {
  const input = await screen.findByLabelText("Chọn ảnh hóa đơn");
  await userEvent.upload(
    input,
    new File(["original"], "photo.jpg", { type: "image/jpeg" }),
  );
  await screen.findByAltText("Ảnh hóa đơn đã tối ưu để tải lên");
}

beforeEach(() => {
  window.history.replaceState(null, "", "/");
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL = vi.fn(() => "blob:receipt-preview");
      static revokeObjectURL = vi.fn();
    },
  );
  compressReceiptImage.mockImplementation(
    async () => new File(["compressed"], "receipt.jpg", { type: "image/jpeg" }),
  );
});

describe("HomeWallet frontend integration", () => {
  it("keeps authenticated API calls behind login and preserves the requested return route", async () => {
    const { auth, client } = show({ auth: makeAuth(null), path: "/upload" });
    await userEvent.click(
      await screen.findByRole("button", { name: /Đăng nhập qua Cognito/ }),
    );
    expect(auth.login).toHaveBeenCalledWith("/upload");
    expect(client.listHouseholds).not.toHaveBeenCalled();
    expect(client.uploadReceipt).not.toHaveBeenCalled();
  });

  it("shows unavailable Cognito configuration without pretending to log in", async () => {
    const { auth } = show({
      auth: makeAuth(null),
      path: "/",
      settings: { isAuthConfigured: false },
    });
    expect(
      await screen.findByRole("button", { name: /Đăng nhập để bắt đầu/ }),
    ).toBeDisabled();
    expect(auth.login).not.toHaveBeenCalled();
  });

  it("shows owner role and invite code and persists only the chosen household id", async () => {
    show();
    await userEvent.click(
      await screen.findByRole("button", { name: /Nhà mình.*Chủ hộ/ }),
    );
    expect(screen.getByText("INVITE12")).toBeInTheDocument();
    expect(sessionStorage.getItem("homewallet.householdId")).toBe("12");
  });

  it("creates a household with trimmed input and selects the backend result", async () => {
    const { client } = show({
      client: {
        ...makeClient(),
        listHouseholds: vi.fn().mockResolvedValue([]),
      },
    });
    await screen.findByText(/Bạn chưa có hộ gia đình/);
    await userEvent.type(
      screen.getByLabelText("Tên hộ gia đình"),
      "  Nhà mới  ",
    );
    await userEvent.click(
      screen.getByRole("button", { name: /Tạo hộ gia đình/ }),
    );
    await screen.findByText("Đã tạo hộ gia đình.");
    expect(client.createHousehold).toHaveBeenCalledWith("Nhà mới");
    expect(sessionStorage.getItem("homewallet.householdId")).toBe("12");
  });

  it("shows join failure without adding a fabricated household", async () => {
    const client = {
      ...makeClient(),
      listHouseholds: vi.fn().mockResolvedValue([]),
      joinHousehold: vi
        .fn()
        .mockRejectedValue(new Error("Mã mời không hợp lệ.")),
    };
    show({ client });
    await screen.findByText(/Bạn chưa có hộ gia đình/);
    await userEvent.type(screen.getByLabelText("Mã mời"), "wrong");
    await userEvent.click(
      screen.getByRole("button", { name: /Tham gia hộ gia đình/ }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Mã mời không hợp lệ.",
    );
    expect(
      screen.queryByRole("button", { name: /Nhà mình.*Chủ hộ/ }),
    ).not.toBeInTheDocument();
  });

  it("reports missing backend endpoints and allows reloading the list", async () => {
    const client = makeClient();
    client.listHouseholds.mockRejectedValueOnce(
      new Error("API này chưa có trên backend."),
    );
    show({ client });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "API này chưa có",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Thử tải lại danh sách" }),
    );
    expect(
      await screen.findByRole("button", { name: /Nhà mình.*Chủ hộ/ }),
    ).toBeInTheDocument();
  });

  it("does not accept a saved household outside the returned membership list", async () => {
    sessionStorage.setItem("homewallet.householdId", "unrelated-household");
    const { client } = show({ path: "/upload" });
    expect(
      await screen.findByRole("heading", {
        name: "Chọn hộ gia đình trước khi tải ảnh",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Chọn ảnh hóa đơn")).not.toBeInTheDocument();
    expect(client.uploadReceipt).not.toHaveBeenCalled();
  });

  it("uploads the compressed file and only reports image upload, never a confirmed transaction", async () => {
    sessionStorage.setItem("homewallet.householdId", "12");
    const { client } = show({ path: "/upload" });
    await prepareUpload();
    await userEvent.click(
      screen.getByRole("button", { name: /Tải hóa đơn lên/ }),
    );
    const status = await screen.findByText(/Đã tải ảnh thành công/);
    expect(status).toHaveTextContent("giao dịch chưa được xác nhận");
    expect(client.uploadReceipt).toHaveBeenCalledTimes(1);
    expect(client.uploadReceipt.mock.calls[0][0]).toMatchObject({
      householdId: "12",
      file: expect.objectContaining({
        name: "receipt.jpg",
        type: "image/jpeg",
        size: 10,
      }),
    });
    expect(
      screen.getByRole("button", { name: /Tải hóa đơn khác/ }),
    ).toBeEnabled();
  });

  it("retries S3 with the existing upload plan without creating a second receipt", async () => {
    sessionStorage.setItem("homewallet.householdId", "12");
    const client = makeClient();
    const plan = {
      receipt_id: "99",
      upload: {
        url: "https://receipts.s3.ap-southeast-1.amazonaws.com/",
        fields: { key: "key" },
      },
    };
    client.uploadReceipt.mockRejectedValueOnce(
      Object.assign(new Error("S3 chưa nhận ảnh."), {
        receiptId: "99",
        uploadPlan: plan,
      }),
    );
    show({ path: "/upload", client });
    await prepareUpload();
    await userEvent.click(
      screen.getByRole("button", { name: /Tải hóa đơn lên/ }),
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Thử tải lại ảnh" }),
    );
    await screen.findByText(/Đã tải ảnh thành công/);
    expect(client.uploadReceipt).toHaveBeenCalledTimes(1);
    expect(client.resumeReceiptUpload).toHaveBeenCalledWith(
      expect.objectContaining({ plan, file: expect.any(File) }),
    );
  });

  it.each([{ receiptId: "99" }, { creationUncertain: true }])(
    "blocks a second create when receipt creation needs reconciliation: %j",
    async (details) => {
      sessionStorage.setItem("homewallet.householdId", "12");
      const client = makeClient();
      client.uploadReceipt.mockRejectedValueOnce(
        Object.assign(new Error("Cần kiểm tra trạng thái hóa đơn."), details),
      );
      show({ path: "/upload", client });
      await prepareUpload();
      await userEvent.click(
        screen.getByRole("button", { name: /Tải hóa đơn lên/ }),
      );
      await screen.findByText("Cần kiểm tra trạng thái hóa đơn.");
      expect(
        screen.getByRole("button", { name: /Tải hóa đơn lên/ }),
      ).toBeDisabled();
      expect(client.uploadReceipt).toHaveBeenCalledTimes(1);
    },
  );

  it("shows corrupt image errors without issuing an upload", async () => {
    sessionStorage.setItem("homewallet.householdId", "12");
    compressReceiptImage.mockRejectedValueOnce(
      new Error("Không thể đọc ảnh này."),
    );
    const { client } = show({ path: "/upload" });
    await userEvent.upload(
      await screen.findByLabelText("Chọn ảnh hóa đơn"),
      new File(["broken"], "photo.jpg", { type: "image/jpeg" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Không thể đọc ảnh này.",
    );
    expect(client.uploadReceipt).not.toHaveBeenCalled();
  });

  it("clears household data when the API reports an expired session", async () => {
    sessionStorage.setItem("homewallet.householdId", "12");
    const client = makeClient();
    client.listHouseholds.mockRejectedValueOnce(
      Object.assign(new Error("expired"), { status: 401 }),
    );
    show({ client });
    expect(
      await screen.findByRole("button", { name: /Đăng nhập qua Cognito/ }),
    ).toBeInTheDocument();
    expect(sessionStorage.getItem("homewallet.householdId")).toBeNull();
    expect(
      screen.queryByRole("button", { name: /Nhà mình.*Chủ hộ/ }),
    ).not.toBeInTheDocument();
  });

  it("removes previous household data on account change while new memberships are loading", async () => {
    const { auth, client } = show();
    await screen.findByRole("button", { name: /Nhà mình.*Chủ hộ/ });
    client.listHouseholds.mockReturnValueOnce(new Promise(() => {}));
    await act(async () => {
      auth.subscribe.mock.calls[0][0]({
        profile: { sub: "other-user", email: "other@example.com" },
      });
    });
    expect(
      screen.queryByRole("button", { name: /Nhà mình.*Chủ hộ/ }),
    ).not.toBeInTheDocument();
  });

  it.each([null, { profile: { sub: "new-user", email: "new@example.com" } }])(
    "discards late household mutations after logout or account change: %j",
    async (nextUser) => {
      let resolveCreate;
      const client = makeClient();
      client.createHousehold.mockReturnValueOnce(
        new Promise((resolve) => {
          resolveCreate = resolve;
        }),
      );
      const { auth } = show({ client });
      await screen.findByRole("button", { name: /Nhà mình.*Chủ hộ/ });
      await userEvent.type(
        screen.getByLabelText("Tên hộ gia đình"),
        "Nhà riêng cũ",
      );
      await userEvent.click(
        screen.getByRole("button", { name: /Tạo hộ gia đình/ }),
      );
      client.listHouseholds.mockResolvedValue([]);
      await act(async () => {
        auth.subscribe.mock.calls[0][0](nextUser);
      });
      await act(async () => {
        resolveCreate({
          ...household,
          id: "old-account-household",
          name: "Nhà riêng cũ",
        });
      });
      expect(screen.queryByText("Đã tạo hộ gia đình.")).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /Nhà riêng cũ/ }),
      ).not.toBeInTheDocument();
      expect(sessionStorage.getItem("homewallet.householdId")).toBeNull();
    },
  );

  it("still renders when optional selection storage is blocked", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    show();
    await userEvent.click(
      await screen.findByRole("button", { name: /Nhà mình.*Chủ hộ/ }),
    );
    expect(screen.getByText("INVITE12")).toBeInTheDocument();
  });

  it("cleans OAuth query parameters while passing the original callback to auth under StrictMode", async () => {
    window.history.replaceState(
      null,
      "",
      "/auth/callback?code=secret-code&state=state",
    );
    const { auth, navigate } = show({ path: "/auth/callback", strict: true });
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/upload"));
    expect(auth.completeLogin).toHaveBeenCalledWith(
      expect.stringContaining("code=secret-code"),
    );
    expect(window.location.search).toBe("");
    expect(auth.getUser).not.toHaveBeenCalled();
  });

  it("offers a clean restart when auth rejects the callback", async () => {
    const auth = makeAuth();
    auth.completeLogin.mockRejectedValue(
      new Error("Phiên xác thực không hợp lệ."),
    );
    const { navigate } = show({ auth, path: "/auth/callback" });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Phiên xác thực không hợp lệ.",
    );
    expect(
      screen.getByRole("link", { name: "Quay về và thử lại" }),
    ).toHaveAttribute("href", "/");
    expect(navigate).not.toHaveBeenCalled();
  });
});
