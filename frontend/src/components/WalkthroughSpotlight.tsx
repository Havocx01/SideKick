import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useReducedMotion } from "motion/react";
import { ScanLine } from "lucide-react";
import { driver, type DriveStep } from "driver.js";
import "driver.js/dist/driver.css";
import "./WalkthroughSpotlight.css";
import type { AcceptanceCriteria } from "../api/types";
import { walkthroughPath, walkthroughSteps } from "../walkthrough";

const dismissedKey = "sidekick.walkthrough.guide.dismissed";

function wasDismissed() {
  try { return sessionStorage.getItem(dismissedKey) === "true"; } catch { return false; }
}

function rememberDismissal(dismissed: boolean) {
  try { sessionStorage.setItem(dismissedKey, String(dismissed)); } catch { /* The guide also works without browser storage. */ }
}

function moments(step: string, criteria: AcceptanceCriteria): DriveStep[] {
  const moment = (element: string, title: string, description: string): DriveStep => ({
    element, popover: { title, description, side: "bottom", align: "start" }
  });
  switch (step) {
    case "clean": return [
      moment(".guided-healthy-layout .warning-counts", "Start with the warnings", "This count shows equipment histories warned in time. Green means in time, amber means late, and red means missed."),
      moment(".walkthrough-window", "Timing matters", `A useful warning is active ${criteria.horizon_cycles} to ${criteria.min_useful_lead} cycles before failure. A cycle is a reading interval, not a fixed number of minutes.`)
    ];
    case "fault": return [
      moment(".guided-step-toolbar", "Try changing the readings", "Switch between Healthy and the faulted readings. The equipment histories and model stay the same."),
      moment(".guided-warning-result", "See which warnings survive", "Watch the count and colored bar change. The takeaway below shows how many timely warnings the fault costs.")
    ];
    case "replay": return [
      moment(".playback-controls", "Try the replay", "Press Play, drag the slider, or jump to Fault begins and Warning window. Jumping or scrubbing pauses playback."),
      moment(".guided-replay-chart", "Follow the warning", "Compare the original and faulted scores. The shaded area is useful warning time; the line follows your selected cycle. This is one stored example.")
    ];
    case "compare": return [
      moment(".guided-step-toolbar", "Choose what to compare", "Switch between Timely warnings and Fault tests. The emphasis changes; the recorded results stay the same."),
      moment(".guided-model-rows", "Look beyond healthy readings", "Compare each model's weakest fault and required tests. Passing these tests supports further evaluation, not deployment approval.")
    ];
    default: return [
      moment(".walkthrough-report-preview", "A decision you can review", "The report brings together the decision, weakest scenario, and next checks. Field performance still needs validation."),
      moment(".walkthrough-report-actions", "Take the evidence with you", "Open the readable report or download the evidence ZIP. Both use the recorded benchmark; nothing is trained during this guide.")
    ];
  }
}

export function WalkthroughSpotlight({ step, ready, criteria }: {
  step: string; ready: boolean; criteria?: AcceptanceCriteria;
}) {
  const [enabled, setEnabled] = useState(() => !wasDismissed());
  const navigate = useNavigate();
  const reduced = useReducedMotion();
  useEffect(() => {
    if (!enabled || !ready || !criteria) return;
    let cancelled = false;
    const returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const index = walkthroughSteps.findIndex(item => item.id === step);
    const next = walkthroughSteps[index + 1];
    const steps = moments(step, criteria).filter(item => document.querySelector(String(item.element)));
    if (!steps.length) return;
    function close() {
      rememberDismissal(true);
      setEnabled(false);
      tour.destroy();
      (returnFocus?.isConnected && returnFocus !== document.body ? returnFocus : document.querySelector<HTMLButtonElement>(".walkthrough-guide-button"))?.focus({ preventScroll: true });
    }
    function forward() {
      if (tour.hasNextStep()) tour.moveNext();
      else if (next) { tour.destroy(); navigate(walkthroughPath(next.id)); }
      else close();
    }
    const tour = driver({
      steps, animate: !reduced, duration: 220, smoothScroll: false,
      overlayOpacity: .48, stagePadding: 8, stageRadius: 10,
      popoverClass: "sidekick-spotlight", popoverOffset: 16,
      disableActiveInteraction: false, overlayClickBehavior: "none",
      // Preserve arrow keys for the replay slider and other highlighted controls.
      allowKeyboardControl: false, showProgress: true,
      progressText: `${walkthroughSteps[index]?.label ?? "Guide"} · {{current}} of {{total}}`,
      nextBtnText: "Next", prevBtnText: "Back", doneBtnText: next ? "Next step" : "Finish",
      closeBtnLabel: "Close guide", onNextClick: forward, onDoneClick: forward,
      onPrevClick: () => tour.movePrevious(), onCloseClick: close,
      onPopoverRender: popover => {
        popover.wrapper.removeAttribute("aria-labelledby");
        popover.wrapper.setAttribute("aria-label", "Walkthrough guide");
        popover.wrapper.setAttribute("aria-modal", "true");
        popover.nextButton.focus({ preventScroll: true });
      },
      onHighlightStarted: element => {
        if (element?.matches(".guided-replay-chart")) {
          const chart = element.querySelector<HTMLElement>(".chart-scroll");
          // On narrow screens show the useful window instead of the flat start of the history.
          if (chart) chart.scrollLeft = chart.scrollWidth - chart.clientWidth;
        }
      },
      onHighlighted: () => document.querySelector<HTMLButtonElement>(".sidekick-spotlight .driver-popover-next-btn")?.focus({ preventScroll: true })
    });
    function keyboard(event: KeyboardEvent) {
      if (!tour.isActive()) return;
      if (event.key === "Escape") { event.preventDefault(); event.stopImmediatePropagation(); close(); }
      if (event.key !== "Tab") return;
      // Driver's default tab loop omits custom sliders; include all app controls.
      const roots = [document.querySelector(".sidekick-spotlight"), tour.getActiveElement()];
      const selector = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex="0"]';
      const controls = roots.flatMap(root => root ? Array.from(root.querySelectorAll<HTMLElement>(selector)) : [])
        .filter(element => element.getClientRects().length && getComputedStyle(element).display !== "none");
      const current = controls.indexOf(document.activeElement as HTMLElement);
      const target = controls[(current + (event.shiftKey ? -1 : 1) + controls.length) % controls.length];
      if (target) { event.preventDefault(); event.stopImmediatePropagation(); target.focus(); }
    }
    // Finish existing page fades before measuring targets. No delayed or invented progress.
    const animations = document.querySelector(".page")?.getAnimations() ?? [];
    void Promise.allSettled(animations.map(animation => animation.finished)).then(() => {
      if (!cancelled) tour.drive();
    });
    window.addEventListener("keydown", keyboard, true);
    const refresh = () => { if (tour.isActive()) tour.refresh(); };
    document.addEventListener("scroll", refresh, true);
    return () => {
      cancelled = true;
      window.removeEventListener("keydown", keyboard, true);
      document.removeEventListener("scroll", refresh, true);
      tour.destroy();
    };
  }, [step, ready, criteria, enabled, reduced, navigate]);

  return <button type="button" className="button walkthrough-guide-button" disabled={!ready} onClick={() => {
    rememberDismissal(false); setEnabled(true);
  }}><ScanLine size={15} aria-hidden="true" />Show guide</button>;
}
