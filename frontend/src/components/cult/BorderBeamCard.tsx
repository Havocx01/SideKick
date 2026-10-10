import { useMotionPreference } from "../../hooks/useMotionPreference";
// Adapted from Cult UI's Border Beam Card. MIT attribution: ./LICENSE.
// https://www.cult-ui.com/docs/components/border-beam-card
import { BorderBeam } from "border-beam";
import { useEffect, useState, type ReactNode } from "react";
import type { Theme } from "../../hooks/useTheme";
import styles from "./border-beam-card.module.css";

export function BorderBeamCard({ children, cardClassName }: { children: ReactNode; cardClassName?: string }) {
  const [theme, setTheme] = useState<Theme>("light");
  const reduced = useMotionPreference();
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    const readTheme = () => setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
    const readVisibility = () => setHidden(document.hidden);
    readTheme();
    readVisibility();
    const observer = new MutationObserver(readTheme);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    document.addEventListener("visibilitychange", readVisibility);
    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", readVisibility);
    };
  }, []);

  return (
    <div className={styles.shell} data-hidden={hidden || undefined}>
      <BorderBeam
        className={styles.beam}
        active={!reduced}
        css={`html[data-motion="full"] [data-beam="{id}"][data-active] {
          animation: beam-spin-{id} 8s linear infinite, beam-fade-in-{id} .6s ease forwards !important;
        }`}
        size="md"
        colorVariant="ocean"
        staticColors
        theme={theme}
        borderRadius={18}
        duration={8}
        strength={0.75}
        glowSize={0.6}
        brightness={1.15}
      >
        <div className={cardClassName}>{children}</div>
      </BorderBeam>
    </div>
  );
}
