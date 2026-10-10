import { useMotionPreference } from "../../hooks/useMotionPreference";
// Adapted from Cult UI Intro Disclosure (MIT). See ./LICENSE.
// Sidekick uses live, recorded-evidence controls in place of the media preview.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { AnimatePresence, motion, useIsPresent } from "motion/react";
import { ArrowLeft, ArrowRight, Check, X } from "lucide-react";
import styles from "./intro-disclosure.module.css";

import { walkthroughFeatureKey as featureKey, walkthroughSessionKey as sessionKey } from "../../lib/walkthrough-preference";

export function IntroDisclosure({ steps, currentStep, onStepSelect, onClose, children }: {
  steps: readonly { id: string; label: string; title: string; instruction: string; help: string; short_description: string }[];
  currentStep: number;
  onStepSelect: (index: number) => void;
  onClose: () => void;
  children: ReactNode;
}) {
  const [dontShowAgain, setDontShowAgain] = useState(false);
  const [visited, setVisited] = useState(() => new Set([currentStep]));
  const title = useRef<HTMLHeadingElement | null>(null);
  const content = useRef<HTMLDivElement>(null);
  const previousStep = useRef(currentStep);
  const direction = useRef<1 | -1>(1);
  if (currentStep !== previousStep.current) direction.current = currentStep > previousStep.current ? 1 : -1;
  const touch = useRef<{ x: number; y: number } | null>(null);
  const reduced = useMotionPreference();
  const step = steps[currentStep];
  useEffect(() => {
    setVisited(previous => new Set([...previous, currentStep]));
    if (previousStep.current !== currentStep) {
      content.current?.scrollTo({ top: 0 });
      title.current?.focus({ preventScroll: true });
      previousStep.current = currentStep;
    }
  }, [currentStep]);
  function close(complete = false) {
    try {
      sessionStorage.setItem(sessionKey, "true");
      if (dontShowAgain || complete) localStorage.setItem(featureKey, "false");
    } catch { /* Explicit opening and dismissal work without browser storage. */ }
    onClose();
  }
  if (!step) return null;
  const move = (index: number) => { if (index >= 0 && index < steps.length) onStepSelect(index); };
  return <Dialog.Root open onOpenChange={open => { if (!open) close(); }}>
    <Dialog.Portal>
      <Dialog.Backdrop className={styles.backdrop} />
      <Dialog.Popup className={styles.popup} data-step={step.id} initialFocus={title}
        finalFocus={() => document.getElementById("open-walkthrough")}>
        <header className={styles.header}>
          <div className={styles.headerLine}>
            <Dialog.Title>Sidekick walkthrough</Dialog.Title>
            <span className={styles.source}>Recorded NASA benchmark</span>
            <button type="button" className={styles.close} aria-label="Close walkthrough" onClick={() => close()}><X size={18} aria-hidden="true" /></button>
          </div>
          <Dialog.Description className={styles.srOnly}>Explore five steps using recorded development results. No training is started.</Dialog.Description>
          <div className={styles.progress} role="progressbar" aria-label="Walkthrough progress" aria-valuemin={0} aria-valuemax={steps.length} aria-valuenow={currentStep + 1}>
            <motion.span animate={{ scaleX: (currentStep + 1) / steps.length }} initial={false} transition={{ duration: reduced ? 0 : .3 }} />
          </div>
        </header>
        <div className={styles.layout}>
          <div className={styles.controls}>
            <motion.nav aria-label="Walkthrough steps" className={styles.steps}
              initial={reduced ? false : { opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .35, ease: [.25, .1, .25, 1] }}>
              {steps.map((item, index) => <motion.button type="button" key={item.id} onClick={() => move(index)} aria-label={`${item.title} ${item.short_description}`} aria-current={index === currentStep ? "step" : undefined}
                whileHover={reduced ? undefined : { scale: 1.01 }} whileTap={reduced ? undefined : { scale: .97 }} transition={{ duration: .2 }}>
                <span className={styles.stepCopy}><strong>{item.title}</strong><small>{item.short_description}</small></span>
                <span className={styles.compactStepLabel} aria-hidden="true">{item.label}</span>
                <AnimatePresence>{visited.has(index) && <motion.span key="visited" className={styles.completed} aria-label="Visited"
                  initial={reduced ? false : { opacity: 0, scale: .7 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} transition={{ duration: .2 }}><Check size={10} aria-hidden="true" /></motion.span>}</AnimatePresence>
              </motion.button>)}
            </motion.nav>
            <footer className={styles.footer}>
              <div className={styles.navigation}>
                <button type="button" className={styles.skip} onClick={() => close()}>Skip walkthrough</button>
                <div className={styles.buttons}>
                  <button type="button" className="button" onClick={() => move(currentStep - 1)} disabled={currentStep === 0}><ArrowLeft size={14} aria-hidden="true" />Back</button>
                  <button type="button" className="button primary" onClick={() => currentStep < steps.length - 1 ? move(currentStep + 1) : close(true)}>
                    {currentStep === steps.length - 1 ? "Done" : "Next"}{currentStep < steps.length - 1 && <ArrowRight size={14} aria-hidden="true" />}
                  </button>
                </div>
              </div>
              <label className={styles.preference}><input type="checkbox" checked={dontShowAgain} onChange={event => setDontShowAgain(event.target.checked)} /> Don’t show again</label>
            </footer>
          </div>
          <div className={styles.previewStage} onTouchStart={event => {
            if (!(event.target as HTMLElement).closest("button, input, [role=slider], a, summary, .chart-scroll")) touch.current = { x: event.touches[0]?.clientX ?? 0, y: event.touches[0]?.clientY ?? 0 };
          }} onTouchEnd={event => {
            const start = touch.current; touch.current = null;
            const end = event.changedTouches[0];
            if (start && end && Math.abs(end.clientX - start.x) > 100 && Math.abs(end.clientX - start.x) > Math.abs(end.clientY - start.y) * 1.5) move(currentStep + (end.clientX < start.x ? 1 : -1));
          }} onTouchCancel={() => { touch.current = null; }}>
            <AnimatePresence mode="popLayout" initial={false} custom={direction.current}>
              <motion.div key={step.id} className={styles.preview} custom={direction.current}
                variants={{ enter: (dir: number) => ({ opacity: 0, x: reduced ? 0 : 20 * dir }), show: { opacity: 1, x: 0 }, leave: (dir: number) => ({ opacity: 0, x: reduced ? 0 : -20 * dir, transition: { duration: reduced ? .1 : .15 } }) }}
                initial="enter" animate="show" exit="leave" transition={{ duration: reduced ? .12 : .3, ease: [.25, .1, .25, 1] }}>
                <PreviewContent contentRef={content}>
                  <div className={styles.evidence}>{children}</div>
                  <div className={styles.caption}>
                    <h2 ref={element => { if (element) title.current = element; }} tabIndex={-1}>{step.title}</h2>
                    <p><span className={styles.instruction}>{step.instruction} </span>{step.help}</p>
                  </div>
                </PreviewContent>
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </Dialog.Popup>
    </Dialog.Portal>
  </Dialog.Root>;
}

function PreviewContent({ children, contentRef }: { children: ReactNode; contentRef: React.RefObject<HTMLDivElement> }) {
  const present = useIsPresent();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { if (ref.current) ref.current.inert = !present; }, [present]);
  return <div ref={ref} aria-hidden={!present || undefined} className={styles.previewInner}>
    <div className={styles.content} ref={present ? contentRef : undefined}>{children}</div>
  </div>;
}
