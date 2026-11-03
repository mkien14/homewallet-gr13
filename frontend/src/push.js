import { config } from "./config";

const SW_PATH = "/sw.js";

function decodeKey(value) {
  const padded = `${value}${"=".repeat((4 - (value.length % 4)) % 4)}`;
  const binary = atob(padded.replace(/-/gu, "+").replace(/_/gu, "/"));
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

export function pushSupport() {
  return typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

export function pushPermission() {
  return pushSupport() ? Notification.permission : "unsupported";
}

export async function serviceWorkerRegistration() {
  if (!pushSupport()) return null;
  return navigator.serviceWorker.register(SW_PATH);
}

export async function getBrowserPushSubscription() {
  const registration = await serviceWorkerRegistration();
  return registration?.pushManager.getSubscription() || null;
}

export async function subscribeBrowserPush() {
  if (!pushSupport()) throw new Error("Trình duyệt này chưa hỗ trợ Web Push.");
  if (!config.vapidPublicKey) throw new Error("Web Push chưa được cấu hình khóa công khai VAPID.");
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return { permission, subscription: null };
  const registration = await serviceWorkerRegistration();
  const existing = await registration.pushManager.getSubscription();
  const subscription = existing || await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: decodeKey(config.vapidPublicKey),
  });
  return { permission, subscription };
}

export async function unsubscribeBrowserPush() {
  const subscription = await getBrowserPushSubscription();
  if (subscription) await subscription.unsubscribe();
}

export async function setWorkerLocale(locale) {
  if (!pushSupport()) return;
  try {
    const registration = await navigator.serviceWorker.ready;
    registration.active?.postMessage({ type: "SET_LOCALE", locale: locale === "en" ? "en" : "vi" });
  } catch { /* Push is optional; the in-app center remains available. */ }
}
