export const walkthroughSteps = [
  { id: "clean", title: "Start with healthy sensors", candidate: "logistic_regression/lr2" },
  { id: "fault", title: "Now make one sensor fail", candidate: "logistic_regression/lr2" },
  { id: "replay", title: "Watch one warning change", candidate: "logistic_regression/lr2" },
  { id: "compare", title: "Look for a model that holds up", candidate: "xgboost_augmented/aug3" },
  { id: "report", title: "Take the evidence with you", candidate: "xgboost_augmented/aug3" }
] as const;

export type WalkthroughStep = typeof walkthroughSteps[number]["id"];

export function walkthroughStep(params: URLSearchParams) {
  return walkthroughSteps.find(step => step.id === params.get("step")) ?? walkthroughSteps[0];
}

export function walkthroughPath(id: WalkthroughStep) {
  const step = walkthroughSteps.find(step => step.id === id)!;
  return `/walkthrough?${new URLSearchParams({ step: id, candidate: step.candidate, partition: "out_of_fold" })}`;
}
