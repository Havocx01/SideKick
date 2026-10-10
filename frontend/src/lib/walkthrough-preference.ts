export const walkthroughFeatureKey = "feature_sidekick-walkthrough";
export const walkthroughSessionKey = "sidekick.walkthrough.intro.dismissed";

export function shouldShowWalkthroughIntro() {
  try { return localStorage.getItem(walkthroughFeatureKey) !== "false" && sessionStorage.getItem(walkthroughSessionKey) !== "true"; }
  catch { return false; }
}
