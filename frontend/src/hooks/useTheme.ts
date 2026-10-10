import { useEffect, useState } from "react";
import { readMotionPreference } from "./useMotionPreference";

export type Theme = "light" | "dark";

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>("light");
  useEffect(() => {
    setThemeState(document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light");
    const sync = (event: StorageEvent) => {
      if (event.key !== "sidekick-theme") return;
      const next = event.newValue === "dark" ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", next);
      setThemeState(next);
    };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);

  const setTheme = (next: Theme) => {
    const apply = () => {
      document.documentElement.setAttribute("data-theme", next);
      document.documentElement.style.colorScheme = next;
    };
    const transition = (document as Document & { startViewTransition?: (update: () => void) => unknown }).startViewTransition;
    if (transition && !readMotionPreference()) transition.call(document, apply);
    else apply();
    setThemeState(next);
    try {
      localStorage.setItem("sidekick-theme", next);
    } catch (error) {
      console.warn("Could not save the theme preference.", error);
    }
  };
  return { theme, isDark: theme === "dark", setTheme, toggleTheme: () => setTheme(theme === "dark" ? "light" : "dark") };
}
