import { Moon, Sun } from "lucide-react";
import { useTheme } from "../hooks/useTheme";
import { Button } from "./Chrome";

export function ThemeToggle() {
  const { isDark, toggleTheme } = useTheme();
  return (
    <Button variant="ghost" className="theme-toggle icon-button" onClick={toggleTheme} role="switch" aria-checked={isDark} aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"} title={isDark ? "Light appearance" : "Dark appearance"}>
      {isDark ? <Moon size={17} strokeWidth={1.9} aria-hidden="true" /> : <Sun size={17} strokeWidth={1.9} aria-hidden="true" />}
    </Button>
  );
}
