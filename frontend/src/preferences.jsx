import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

/* This shared module intentionally exports translation hooks and the provider. */
/* eslint react-refresh/only-export-components: off */

const PreferenceContext = createContext(null);
const LOCALE_KEY = "hw.locale";
const LOCALE_TOUCHED_KEY = "hw.locale.selected";
const THEME_KEY = "hw.theme";

import { t } from "./translations.js";
export { t } from "./translations.js";

export function usePreferences() {
  const value = useContext(PreferenceContext);
  if (!value) throw new Error("usePreferences must be used inside PreferenceProvider");
  return value;
}

export function PreferenceProvider({ children }) {
  const [locale, setLocaleState] = useState(() => localStorage.getItem(LOCALE_KEY) || "vi");
  const [theme, setThemeState] = useState(() => localStorage.getItem(THEME_KEY) || "light");

  useEffect(() => {
    const syncPreferences = (event) => {
      if (event.key === LOCALE_KEY) {
        setLocaleState(event.newValue === "en" ? "en" : "vi");
      }
      if (event.key === THEME_KEY) {
        setThemeState(event.newValue === "dark" ? "dark" : "light");
      }
    };
    window.addEventListener("storage", syncPreferences);
    return () => window.removeEventListener("storage", syncPreferences);
  }, []);

  const setLocale = useCallback((value, { selected = true } = {}) => {
    const next = value === "en" ? "en" : "vi";
    localStorage.setItem(LOCALE_KEY, next);
    if (selected) localStorage.setItem(LOCALE_TOUCHED_KEY, "1");
    setLocaleState(next);
  }, []);

  const setTheme = useCallback((value) => {
    const next = value === "dark" ? "dark" : "light";
    localStorage.setItem(THEME_KEY, next);
    setThemeState(next);
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
  }, [locale, theme]);

  const value = useMemo(() => ({ locale, setLocale, theme, setTheme, t: (text) => t(text, locale) }), [locale, setLocale, theme, setTheme]);
  return <PreferenceContext.Provider value={value}>{children}</PreferenceContext.Provider>;
}

export const preferenceStorageKeys = { locale: LOCALE_KEY, localeTouched: LOCALE_TOUCHED_KEY, theme: THEME_KEY };
