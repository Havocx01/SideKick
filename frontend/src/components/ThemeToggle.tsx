import { Moon, Sun } from "lucide-react";
import { useTheme } from "../hooks/useTheme";
import { Button } from "./Chrome";

export function ThemeToggle() {
  const { isDark, toggleTheme } = useTheme();
  return (
    <Button variant="ghost" className="theme-toggle" onClick={toggleTheme} role="switch" aria-checked={isDark} aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}>
      {isDark ? <Moon size={18} aria-hidden="true" /> : <Sun size={18} aria-hidden="true" />}
      <span>{isDark ? "Dark" : "Light"}</span>
    </Button>
  );
}
