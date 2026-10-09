import { useEffect, useId, useRef } from "react";
import { motion, useAnimation } from "motion/react";
import styles from "./canvas-fractal-grid.module.css";

// Cult UI CanvasFractalGrid, adapted for local canvas sizing and Sidekick tokens.
// Original wave, per-dot glow, gradient keyframes, and two-layer mouse glow.
// MIT attribution: ./LICENSE; source: https://www.cult-ui.com/r/canvas-fractal-grid.json
interface CanvasFractalGridProps {
  dotSize?: number;
  dotSpacing?: number;
  dotOpacity?: number;
  gradientAnimationDuration?: number;
  waveIntensity?: number;
  waveRadius?: number;
  enableGradient?: boolean;
  enableMouseGlow?: boolean;
  enableNoise?: boolean;
  respectReducedMotion?: boolean;
}

// Cult's radial-gradient keyframe sequence, tinted quietly in Sidekick blue.
const gradients = [
  "radial-gradient(circle at 30% 70%, rgba(0,113,227,0.035) 0%, rgba(10,132,255,0.02) 25%, transparent 75%)",
  "radial-gradient(circle at 70% 30%, rgba(10,132,255,0.035) 0%, rgba(0,113,227,0.02) 25%, transparent 75%)",
  "radial-gradient(circle at 40% 60%, rgba(0,113,227,0.035) 0%, rgba(10,132,255,0.02) 25%, transparent 75%)",
];

export function CanvasFractalGrid({
  dotSize = 3, dotSpacing = 20, dotOpacity = 0.14,
  gradientAnimationDuration = 6, waveIntensity = 60, waveRadius = 250,
  enableGradient = true, enableMouseGlow = true, enableNoise = true,
  respectReducedMotion = true,
}: CanvasFractalGridProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const glowRef = useRef<HTMLDivElement>(null);
  const gradientControls = useAnimation();
  const noiseId = `fractal-noise-${useId().replace(/:/g, "")}`;

  useEffect(() => {
    const root = rootRef.current;
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    const mouseGlow = glowRef.current;
    if (!root || !canvas || !context) return;

    let width = 0;
    let height = 0;
    let frame = 0;
    let lastFrame = 0;
    let visible = true;
    let dotColor = "";
    let glowColor = "";
    const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
    let reducedMotion = respectReducedMotion && motionPreference.matches;
    const pointer = { x: 0, y: 0, active: false };
    const canInteract = () => visible && !document.hidden;
    const canAnimate = () => !reducedMotion && canInteract();

    function draw(time: number) {
      if (!context) return;
      context.clearRect(0, 0, width, height);
      // Preserve Cult's responsive dot sizing and spacing.
      const size = Math.max(1, dotSize * (width < 768 ? 0.75 : width < 1024 ? 0.9 : 1));
      const spacing = Math.max(8, dotSpacing * (width < 768 ? 1.5 : width < 1024 ? 1.25 : 1));
      const radius = Math.max(1, waveRadius);
      for (let x = 0; x < width; x += spacing) {
        for (let y = 0; y < height; y += spacing) {
          const dx = x - pointer.x;
          const dy = y - pointer.y;
          const distance = Math.hypot(dx, dy);
          let dotX = x;
          let dotY = y;
          const strength = pointer.active && distance < radius ? Math.pow(1 - distance / radius, 2) : 0;
          if (strength > 0) {
            // Cult's original ripple equation and per-dot radial glow.
            const angle = Math.atan2(dy, dx);
            const offset = reducedMotion ? 0 : Math.sin(distance * 0.05 - time * 0.005) * waveIntensity * strength;
            dotX += Math.cos(angle) * offset;
            dotY += Math.sin(angle) * offset;
            const glowRadius = size * (1 + strength);
            const glow = context.createRadialGradient(dotX, dotY, 0, dotX, dotY, glowRadius);
            glow.addColorStop(0, glowColor);
            glow.addColorStop(1, "transparent");
            context.fillStyle = glow;
          } else {
            context.fillStyle = dotColor;
          }
          context.globalAlpha = Math.min(1, Math.max(0, dotOpacity) * (1 + strength));
          context.beginPath();
          context.arc(dotX, dotY, size / 2, 0, Math.PI * 2);
          context.fill();
        }
      }
      context.globalAlpha = 1;
    }

    function animate(time: number) {
      frame = 0;
      if (!canAnimate() || !pointer.active) return;
      if (time - lastFrame > 16) { draw(time); lastFrame = time; }
      frame = requestAnimationFrame(animate);
    }

    function syncAnimation() {
      cancelAnimationFrame(frame);
      frame = 0;
      root!.dataset.active = String(canAnimate());
      gradientControls.stop();
      if (!canInteract()) leave();
      if (enableGradient && canAnimate()) {
        void gradientControls.start({
          background: gradients,
          transition: { duration: Math.max(1, gradientAnimationDuration), repeat: Infinity, repeatType: "reverse", ease: "linear" },
        });
      }
      draw(0);
      if (canAnimate() && pointer.active) frame = requestAnimationFrame(animate);
    }

    function readTheme() {
      const tokens = getComputedStyle(root!);
      dotColor = tokens.getPropertyValue("--text-muted").trim();
      glowColor = tokens.getPropertyValue("--accent").trim();
      draw(0);
    }

    function resize() {
      const bounds = root!.getBoundingClientRect();
      width = bounds.width;
      height = bounds.height;
      const scale = Math.min(window.devicePixelRatio || 1, 2);
      canvas!.width = Math.round(width * scale);
      canvas!.height = Math.round(height * scale);
      context!.setTransform(scale, 0, 0, scale, 0, 0);
      draw(0);
    }

    function move(event: PointerEvent) {
      if (event.pointerType === "touch" || !canInteract()) return;
      const bounds = root!.getBoundingClientRect();
      pointer.x = event.clientX - bounds.left;
      pointer.y = event.clientY - bounds.top;
      // Cult tracks the window pointer, including positions outside the grid.
      // Clipping hides the glow outside; the ripple keeps its original phase.
      pointer.active = true;
      if (mouseGlow) {
        mouseGlow.style.left = `${pointer.x}px`;
        mouseGlow.style.top = `${pointer.y}px`;
        mouseGlow.style.opacity = "1";
      }
      if (reducedMotion) draw(0);
      else if (!frame) { lastFrame = 0; frame = requestAnimationFrame(animate); }
    }

    function leave() {
      pointer.active = false;
      cancelAnimationFrame(frame);
      frame = 0;
      if (mouseGlow) mouseGlow.style.opacity = "0";
      draw(0);
    }
    function motionChanged() {
      reducedMotion = respectReducedMotion && motionPreference.matches;
      syncAnimation();
    }

    const resizeObserver = new ResizeObserver(resize);
    const themeObserver = new MutationObserver(readTheme);
    const intersectionObserver = new IntersectionObserver(([entry]) => {
      visible = entry?.isIntersecting ?? false;
      syncAnimation();
    });
    readTheme();
    resizeObserver.observe(root);
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "data-accent"] });
    intersectionObserver.observe(root);
    window.addEventListener("pointermove", move, { passive: true, capture: true });
    document.addEventListener("visibilitychange", syncAnimation);
    motionPreference.addEventListener("change", motionChanged);
    syncAnimation();
    return () => {
      cancelAnimationFrame(frame);
      gradientControls.stop();
      resizeObserver.disconnect();
      themeObserver.disconnect();
      intersectionObserver.disconnect();
      window.removeEventListener("pointermove", move, true);
      document.removeEventListener("visibilitychange", syncAnimation);
      motionPreference.removeEventListener("change", motionChanged);
    };
  }, [dotSize, dotSpacing, dotOpacity, waveIntensity, waveRadius, enableMouseGlow, enableGradient, gradientAnimationDuration, respectReducedMotion, gradientControls]);

  return (
    <div ref={rootRef} className={styles.grid} aria-hidden="true">
      {enableGradient && <motion.div className={styles.gradient} style={{ background: gradients[0] }} animate={gradientControls} />}
      <canvas ref={canvasRef} className={styles.dots} />
      {enableNoise && <svg className={styles.noise} xmlns="http://www.w3.org/2000/svg" width="100%" height="100%">
        <filter id={noiseId}><feTurbulence type="fractalNoise" baseFrequency="0.65" numOctaves="3" stitchTiles="stitch" /></filter>
        <rect width="100%" height="100%" filter={`url(#${noiseId})`} />
      </svg>}
      {enableMouseGlow && <div ref={glowRef} className={styles.mouseGlow}><div className={styles.glowOuter} /><div className={styles.glowInner} /></div>}
    </div>
  );
}
