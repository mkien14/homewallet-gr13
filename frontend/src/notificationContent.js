// Older notification payloads may contain either plain text or locale maps.
// Do not stringify an object or translate text written by a user.
const notificationTranslations = {
  "Budget alert": {
    vi: "Cảnh báo ngân sách",
    en: "Budget alert",
  },
  "A spending category reached its alert threshold. Open HomeWallet to review the details.": {
    vi: "Một danh mục chi tiêu đã chạm ngưỡng thiết lập. Mở HomeWallet để xem chi tiết.",
    en: "A spending category reached its alert threshold. Open HomeWallet to review the details.",
  },
  "A spending category has reached its configured threshold. Open HomeWallet to review it.": {
    vi: "Một danh mục chi tiêu đã chạm ngưỡng thiết lập. Mở HomeWallet để xem chi tiết.",
    en: "A spending category has reached its configured threshold. Open HomeWallet to review it.",
  },
  "Bill reminder": {
    vi: "Nhắc hóa đơn",
    en: "Bill reminder",
  },
  "Upcoming bill reminder": {
    vi: "Nhắc hóa đơn sắp đến hạn",
    en: "Upcoming bill reminder",
  },
  "A recurring bill is due soon. Open HomeWallet to review the schedule.": {
    vi: "Có hóa đơn định kỳ sắp đến hạn. Mở HomeWallet để xem lịch thanh toán.",
    en: "A recurring bill is due soon. Open HomeWallet to review the schedule.",
  },
};

function translateNotificationString(value, locale, translate) {
  const known = notificationTranslations[value];
  if (known) return known[locale] || known.vi;
  return translate(value);
}

export function notificationText(value, locale, translate, fallback = "") {
  if (typeof value === "string") return translateNotificationString(value, locale, translate);
  if (value && typeof value === "object" && !Array.isArray(value)) {
    for (const language of [locale, "vi", "en"]) {
      if (typeof value[language] === "string" && value[language].trim()) {
        return translateNotificationString(value[language], locale, translate);
      }
    }
  }
  return translateNotificationString(fallback, locale, translate);
}

export function notificationDate(value, locale) {
  if (typeof value !== "string" || !value.trim()) return "";
  // API timestamps without an offset have historically been displayed as UTC.
  const timestamp = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`;
  const date = new Date(timestamp);
  if (!Number.isFinite(date.getTime())) return "";
  return new Intl.DateTimeFormat(locale === "en" ? "en-US" : "vi-VN", { dateStyle: "medium", timeStyle: "short" }).format(date);
}
