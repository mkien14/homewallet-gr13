import { useEffect, useMemo, useRef, useState } from "react";
import Icon from "./Icon";

function parseIso(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || "");
  if (!match) return null;
  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 12));
}

function parseTypedDate(value, locale) {
  const parts = String(value).trim().split(/[./-]/u).map(Number);
  if (parts.length !== 3 || parts.some((part) => !Number.isInteger(part))) return null;
  const [first, second, third] = parts;
  const year = third > 31 ? third : first > 31 ? first : null;
  const month = year === third ? (locale === "en" ? first : second) : second;
  const day = year === third ? (locale === "en" ? second : first) : first;
  if (!year || month < 1 || month > 12 || day < 1 || day > 31) return null;
  const date = new Date(Date.UTC(year, month - 1, day, 12));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day ? date : null;
}

function isoDate(date) {
  return date.toISOString().slice(0, 10);
}

function startOfMonth(date) {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1, 12));
}

function clampDate(date, min, max) {
  if (min && date < min) return min;
  if (max && date > max) return max;
  return date;
}

function calendarDays(month, min, max) {
  const first = startOfMonth(month);
  const mondayOffset = (first.getUTCDay() + 6) % 7;
  const start = new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth(), 1 - mondayOffset, 12));
  return Array.from({ length: 42 }, (_, index) => {
    const date = new Date(start);
    date.setUTCDate(start.getUTCDate() + index);
    return {
      date,
      value: isoDate(date),
      inMonth: date.getUTCMonth() === month.getUTCMonth(),
      disabled: Boolean((min && date < min) || (max && date > max)),
    };
  });
}

export default function LocalizedDatePicker({ id, value, min, max, locale, disabled, required, onChange }) {
  const containerRef = useRef(null);
  const selectedDate = parseIso(value);
  const minDate = parseIso(min);
  const maxDate = parseIso(max);
  const today = new Date();
  const [open, setOpen] = useState(false);
  const [month, setMonth] = useState(() => startOfMonth(clampDate(selectedDate || startOfMonth(today), minDate, maxDate) || today));
  const language = locale === "en" ? "en-US" : "vi-VN";
  const monthLabel = new Intl.DateTimeFormat(language, { month: "long", year: "numeric", timeZone: "UTC" }).format(month);
  const [typedValue, setTypedValue] = useState("");
  const weekdays = useMemo(() => {
    const monday = new Date(Date.UTC(2024, 0, 1, 12));
    return Array.from({ length: 7 }, (_, index) => {
      const date = new Date(monday);
      date.setUTCDate(monday.getUTCDate() + index);
      return new Intl.DateTimeFormat(language, { weekday: "short", timeZone: "UTC" }).format(date);
    });
  }, [language]);
  const days = calendarDays(month, minDate, maxDate);
  const inputFormatter = useMemo(() => new Intl.DateTimeFormat(language, { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" }), [language]);

  useEffect(() => {
    if (!open) return undefined;
    const close = (event) => {
      if (!containerRef.current?.contains(event.target)) setOpen(false);
    };
    const closeOnEscape = (event) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  function moveMonth(offset) {
    const next = new Date(Date.UTC(month.getUTCFullYear(), month.getUTCMonth() + offset, 1, 12));
    const firstAllowed = minDate && startOfMonth(minDate);
    const lastAllowed = maxDate && startOfMonth(maxDate);
    if (firstAllowed && next < firstAllowed) return;
    if (lastAllowed && next > lastAllowed) return;
    setMonth(next);
  }

  function choose(valueToSet) {
    onChange(valueToSet);
    setTypedValue(valueToSet ? inputFormatter.format(parseIso(valueToSet)) : "");
    setOpen(false);
  }

  const displayValue = typedValue || (selectedDate ? inputFormatter.format(selectedDate) : "");

  return (
    <div className="localized-date-picker" ref={containerRef}>
      <div className="localized-date-trigger">
        <input id={id} type="text" inputMode="numeric" value={displayValue} placeholder={locale === "en" ? "MM/DD/YYYY" : "DD/MM/YYYY"} required={required} disabled={disabled} onChange={(event) => {
          const next = event.target.value;
          setTypedValue(next);
          const parsed = parseTypedDate(next, locale);
          if (parsed) {
            const nextValue = isoDate(parsed);
            if ((!minDate || parsed >= minDate) && (!maxDate || parsed <= maxDate)) onChange(nextValue);
          } else if (!next) onChange("");
        }} onBlur={() => {
          if (value) setTypedValue(inputFormatter.format(parseIso(value)));
        }} />
        <button type="button" className="localized-date-icon" aria-label={locale === "en" ? "Open calendar" : "Mở lịch"} aria-haspopup="dialog" aria-expanded={open} aria-controls={`${id}-calendar`} disabled={disabled} onClick={() => setOpen((current) => !current)}><Icon name="calendar" /></button>
      </div>
      {open && <div id={`${id}-calendar`} className="localized-date-calendar" role="dialog" aria-label={locale === "en" ? "Choose date" : "Chọn ngày"}>
        <div className="localized-date-calendar-heading">
          <strong>{monthLabel}</strong>
          <div>
            <button type="button" aria-label={locale === "en" ? "Previous month" : "Tháng trước"} onClick={() => moveMonth(-1)}>‹</button>
            <button type="button" aria-label={locale === "en" ? "Next month" : "Tháng sau"} onClick={() => moveMonth(1)}>›</button>
          </div>
        </div>
        <div className="localized-date-weekdays">{weekdays.map((day) => <span key={day}>{day}</span>)}</div>
        <div className="localized-date-grid">
          {days.map((day) => <button type="button" key={day.value} disabled={day.disabled} className={`${day.inMonth ? "" : "is-outside"} ${day.value === value ? "is-selected" : ""}`} onClick={() => choose(day.value)}>{day.date.getUTCDate()}</button>)}
        </div>
        <div className="localized-date-actions">
          <button type="button" onClick={() => choose("")}>{locale === "en" ? "Clear" : "Xóa"}</button>
          <button type="button" onClick={() => choose(isoDate(clampDate(new Date(Date.UTC(today.getFullYear(), today.getMonth(), today.getDate(), 12)), minDate, maxDate)))}>{locale === "en" ? "Today" : "Hôm nay"}</button>
        </div>
      </div>}
    </div>
  );
}
