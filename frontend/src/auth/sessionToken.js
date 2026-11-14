export function readSessionToken(storage, now = Date.now()) {
  const raw = storage.getItem("hw.token");
  if (!raw) return null;
  try {
    const token = JSON.parse(raw);
    if (typeof token?.access === "string" && token.access && Number.isFinite(token.exp) && token.exp > now) return token.access;
  } catch { /* Discard damaged or stale browser state. */ }
  storage.removeItem("hw.token");
  return null;
}
