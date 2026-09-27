import { useEffect, useState } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "sidekick-theme";

function storedTheme() {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch (error) {
    if (!(error instanceof DOMException) || error.name !== "SecurityError") throw error;
    return null;
  }
}

function getSystemTheme(): Theme {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function getInitialTheme(): Theme {
  if (typeof window === "undefined") return "light";
  const stored = storedTheme();
  if (stored === "light" || stored === "dark") return stored;

  const fromDom = document.documentElement.getAttribute("data-theme");
  if (fromDom === "light" || fromDom === "dark") return fromDom;

  return getSystemTheme();
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(getInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    document.documentElement.style.colorScheme = theme;
  }, [theme]);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const listener = (event: MediaQueryListEvent) => {
      const stored = storedTheme();
      if (!stored) {
        const next = event.matches ? "dark" : "light";
        setThemeState(next);
      }
    };
    media.addEventListener("change", listener);
    return () => media.removeEventListener("change", listener);
  }, []);

  const setTheme = (next: Theme) => {
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch (error) {
      console.warn("Could not save the theme preference.", error);
    }
    setThemeState(next);
  };

  const toggleTheme = () => {
    setTheme(theme === "dark" ? "light" : "dark");
  };

  return { theme, isDark: theme === "dark", setTheme, toggleTheme };
}
