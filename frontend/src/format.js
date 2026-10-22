const vndFormatter = new Intl.NumberFormat("vi-VN", {
  style: "currency",
  currency: "VND",
  maximumFractionDigits: 0,
});

export function formatVnd(value) {
  return vndFormatter.format(Number.isFinite(Number(value)) ? Number(value) : 0);
}

export function formatDate(iso) {
  if (!iso) return "";
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:$|T)/.exec(String(iso));
  return match ? `${match[3]}/${match[2]}/${match[1]}` : "";
}

export function parseVnd(text) {
  const value = String(text ?? "").trim();
  const digits = value.replace(/(?:₫|đ|VND|\s)/gi, "");
  if (!/^\d+(?:[.,]\d{3})*$/.test(digits)) return null;
  const number = Number(digits.replace(/[.,]/g, ""));
  return Number.isSafeInteger(number) ? number : null;
}

export function todayIso(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
