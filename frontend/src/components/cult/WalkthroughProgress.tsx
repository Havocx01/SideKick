// Adapted from Cult UI's onboarding StepIndicator primitive.
// https://www.cult-ui.com/r/onboarding.json. MIT license: see LICENSE.
import { motion, useReducedMotion } from "motion/react";
import { motionTokens } from "@/registry/motion-tokens";

export function WalkthroughProgress({ currentStep, totalSteps }: { currentStep: number; totalSteps: number }) {
  const reduced = useReducedMotion();
  return <div className="walkthrough-progress" role="progressbar" aria-label={`Step ${currentStep} of ${totalSteps}`}
    aria-valuemin={1} aria-valuemax={totalSteps} aria-valuenow={currentStep} data-slot="onboarding-step-indicator">
    {Array.from({ length: totalSteps }, (_, index) => {
      const step = index + 1;
      const state = step === currentStep ? "active" : step < currentStep ? "completed" : "inactive";
      return <span key={step} data-slot="onboarding-step-dot" data-state={state} aria-current={state === "active" ? "step" : undefined}>
        <motion.span initial={false} animate={{ scaleX: step <= currentStep ? 1 : 0 }}
          transition={reduced ? { duration: 0 } : { duration: motionTokens.duration.fast, ease: motionTokens.ease.enter }} />
      </span>;
    })}
  </div>;
}
