import { api } from "./api";
import { USE_MOCK } from "./mode";

const MAX_BYTES = 5 * 1024 * 1024; 
const MAX_SIDE = 2000;

export async function prepareFile(file) {
  if (file.type === "application/pdf") {
    if (file.size > MAX_BYTES) throw new Error("PDF lớn hơn 5 MB");
    return file;
  }
  if (!["image/jpeg", "image/png"].includes(file.type)) {
    throw new Error("Chỉ nhận JPEG, PNG hoặc PDF");
  }

  let bmp;
  try {
    bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    throw new Error("Không đọc được ảnh. Hãy chọn tệp JPEG hoặc PNG hợp lệ.");
  }
  let scale = Math.min(1, MAX_SIDE / Math.max(bmp.width, bmp.height));

  for (let attempt = 0; attempt < 4; attempt++) {
    const w = Math.round(bmp.width * scale);
    const h = Math.round(bmp.height * scale);
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#fff"; 
    ctx.fillRect(0, 0, w, h);
    ctx.drawImage(bmp, 0, 0, w, h);

    for (const quality of [0.85, 0.75, 0.65]) {
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
      if (blob && blob.size <= MAX_BYTES) {
        bmp.close();
        return blob;
      }
    }
    scale *= 0.75;
  }
  bmp.close();
  throw new Error("Không nén được ảnh xuống dưới 5 MB");
}

export async function uploadReceipt(file, onStage, { signal } = {}) {
  signal?.throwIfAborted();
  onStage("Đang nén ảnh");
  const blob = await prepareFile(file);
  signal?.throwIfAborted();

  onStage("Đang xin phép tải lên");
  const { receipt, upload } = await api("/api/receipts", {
    method: "POST",
    body: { content_type: blob.type, size: blob.size },
    signal,
  });

  onStage("Đang tải lên");
  if (USE_MOCK) {
    const { completeMockUpload } = await import("./mocks/index.js");
    await completeMockUpload(receipt.id, blob);
    return receipt.id;
  }
  const form = new FormData();
  Object.entries(upload.fields).forEach(([k, v]) => form.append(k, v));
  form.append("file", blob); 
  const res = await fetch(upload.url, { method: "POST", body: form, signal });
  if (!res.ok) throw new Error(`Kho lưu trữ từ chối tệp (${res.status})`);
  return receipt.id;
}

const FINISHED = ["DRAFT_READY", "NEEDS_REVIEW", "FAILED", "CONFIRMED"];

export async function waitForStatus(id, onUpdate, tries = 60, { signal } = {}) {
  for (let i = 0; i < tries; i++) {
    const r = await api(`/api/receipts/${id}`, { signal });
    onUpdate(r.status);
    if (FINISHED.includes(r.status)) return r.status;
    await new Promise((resolve, reject) => {
      signal?.throwIfAborted();
      const timer = setTimeout(() => {
        signal?.removeEventListener("abort", abort);
        resolve();
      }, 2000);
      function abort() {
        clearTimeout(timer);
        reject(signal.reason);
      }
      signal?.addEventListener("abort", abort, { once: true });
    });
  }
  return "TIMEOUT";
}

export const STATUS_LABEL = {
  UPLOADING: "Đang tải lên",
  UPLOADED: "Đã tải lên, chờ xử lý",
  PROCESSING: "Đang đọc hóa đơn",
  DRAFT_READY: "Bản nháp sẵn sàng",
  NEEDS_REVIEW: "Cần kiểm tra lại",
  CONFIRMED: "Đã xác nhận",
  FAILED: "Xử lý thất bại",
  TIMEOUT: "Quá thời gian chờ",
};
