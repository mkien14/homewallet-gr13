// Older notification payloads may contain either plain text or locale maps.
// Do not stringify an object or translate text written by a user.
export function notificationText(value, locale, translate, fallback = "") {
  if (typeof value === "string") return translate(value);
  if (value && typeof value === "object" && !Array.isArray(value)) {
    for (const language of [locale, "vi", "en"]) {
      if (typeof value[language] === "string" && value[language].trim()) return translate(value[language]);
    }
  }
  return translate(fallback);
}

export function notificationDate(value, locale) {
  if (typeof value !== "string" || !value.trim()) return "";
  // API timestamps without an offset have historically been displayed as UTC.
  const timestamp = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`;
  const date = new Date(timestamp);
  if (!Number.isFinite(date.getTime())) return "";
  return new Intl.DateTimeFormat(locale === "en" ? "en-US" : "vi-VN", { dateStyle: "medium", timeStyle: "short" }).format(date);
}
