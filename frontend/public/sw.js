const DB_NAME = "homewallet-push";
const STORE = "settings";

function getLocale() {
  return new Promise((resolve) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onerror = () => resolve("vi");
    request.onsuccess = () => {
      const db = request.result;
      const read = db.transaction(STORE, "readonly").objectStore(STORE).get("locale");
      read.onsuccess = () => { db.close(); resolve(read.result === "en" ? "en" : "vi"); };
      read.onerror = () => { db.close(); resolve("vi"); };
    };
  });
}

function saveLocale(locale) {
  return new Promise((resolve) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onerror = () => resolve();
    request.onsuccess = () => {
      const db = request.result;
      const transaction = db.transaction(STORE, "readwrite");
      transaction.objectStore(STORE).put(locale === "en" ? "en" : "vi", "locale");
      transaction.oncomplete = () => { db.close(); resolve(); };
      transaction.onerror = () => { db.close(); resolve(); };
    };
  });
}

self.addEventListener("message", (event) => {
  if (event.data?.type === "SET_LOCALE") event.waitUntil(saveLocale(event.data.locale));
});

self.addEventListener("push", (event) => {
  let payload = {};
  try { payload = event.data?.json() || {}; } catch { payload = {}; }
  const allowedPath = typeof payload.deep_link === "string" && payload.deep_link.startsWith("/") && !payload.deep_link.startsWith("//") ? payload.deep_link : "/notifications";
  event.waitUntil(getLocale().then((locale) => {
    const isBudget = payload.event_type === "budget_alert";
    const title = locale === "en" ? (isBudget ? "Budget alert" : "Bill reminder") : (isBudget ? "Cảnh báo ngân sách" : "Nhắc hóa đơn");
    const body = locale === "en" ? "Open HomeWallet to review the details." : "Mở HomeWallet để xem chi tiết.";
    return self.registration.showNotification(title, { body, data: { deep_link: allowedPath }, tag: `homewallet-${payload.event_type || "notification"}` });
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.deep_link || "/notifications", self.location.origin);
  if (target.origin !== self.location.origin) return;
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
    const current = clients.find((client) => new URL(client.url).origin === self.location.origin);
    if (current) {
      current.postMessage({ type: "OPEN_NOTIFICATION_LINK", href: `${target.pathname}${target.search}${target.hash}` });
      return current.focus();
    }
    return self.clients.openWindow(`${target.pathname}${target.search}${target.hash}`);
  }));
});
