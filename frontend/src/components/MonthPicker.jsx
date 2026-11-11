import { useMemo, useState } from "react";
import { usePreferences } from "../preferences";

function validYear(value) {
  const year = Number(value);
  return /^\d{1,4}$/.test(value) && year >= 1 && year <= 9998;
}

export default function MonthPicker({ id, value, onChange, disabled = false }) {
  const { locale } = usePreferences();
  const [year, setYear] = useState(() => String(Number(value.slice(0, 4))));

  const months = useMemo(() => Array.from({ length: 12 }, (_, index) =>
    new Intl.DateTimeFormat(locale === "en" ? "en-US" : "vi-VN", { month: "long", timeZone: "UTC" })
      .format(new Date(Date.UTC(2020, index, 1)))), [locale]);

  const month = value.slice(5);
  const selectedYear = validYear(year) ? String(Number(year)).padStart(4, "0") : value.slice(0, 4);

  function commitYear() {
    if (!validYear(year) || onChange(`${selectedYear}-${month}`) === false) {
      setYear(String(Number(value.slice(0, 4))));
    }
  }

  return <div className="month-picker">
    <select id={id} value={month} disabled={disabled} onChange={(event) => {
      if (onChange(`${selectedYear}-${event.target.value}`) === false) {
        event.currentTarget.value = month;
        setYear(String(Number(value.slice(0, 4))));
      }
    }}>
      {months.map((label, index) => <option key={index} value={String(index + 1).padStart(2, "0")}>{label}</option>)}
    </select>
    <input type="text" inputMode="numeric" aria-label={locale === "en" ? "Year" : "Năm"} value={year} disabled={disabled}
      onChange={(event) => { if (/^\d{0,4}$/.test(event.target.value)) setYear(event.target.value); }}
      onBlur={commitYear} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); event.currentTarget.blur(); } }} />
  </div>;
}
