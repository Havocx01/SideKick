export const walkthroughSteps = [
  { id: "clean", label: "Healthy", short_description: "Warning timing", title: "Start with healthy sensors", candidate: "logistic_regression/lr2", instruction: "See how many histories received a warning in time.", help: "Each history follows one piece of equipment to its documented failure." },
  { id: "fault", label: "Fault", short_description: "Missing readings", title: "Now make one sensor fail", candidate: "logistic_regression/lr2", instruction: "Switch readings to see which warnings survive.", help: "Both results use the same model and warning rule. Only the sensor readings change." },
  { id: "replay", label: "Replay", short_description: "One stored history", title: "Watch one warning change", candidate: "logistic_regression/lr2", instruction: "Play or scrub one stored equipment history.", help: "This is a stored example, not live monitoring or fleet-wide performance." },
  { id: "compare", label: "Compare", short_description: "Required fault tests", title: "Look for a model that holds up", candidate: "xgboost_augmented/aug3", instruction: "Compare timely warnings and required fault tests.", help: "A model must meet both detection and early-alarm limits in every required case." },
  { id: "report", label: "Report", short_description: "Report and evidence", title: "Take the evidence with you", candidate: "xgboost_augmented/aug3", instruction: "Review the decision, then open or download the evidence.", help: "A passing test supports further evaluation. It does not approve deployment." }
] as const;

export type WalkthroughStep = typeof walkthroughSteps[number]["id"];

export function walkthroughStep(params: URLSearchParams) {
  return walkthroughSteps.find(step => step.id === params.get("step")) ?? walkthroughSteps[0];
}

export function walkthroughPath(id: WalkthroughStep) {
  const step = walkthroughSteps.find(step => step.id === id)!;
  return `/walkthrough?${new URLSearchParams({ step: id, candidate: step.candidate, partition: "out_of_fold" })}`;
}
