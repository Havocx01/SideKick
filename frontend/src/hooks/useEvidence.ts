import { useMemo } from "react";
import { useLocation, useMatch, useSearchParams } from "react-router-dom";
import { walkthroughStep } from "../walkthrough";
import { evidenceApi } from "../api/client";

export function useExperimentId() {
  return useMatch("/experiments/:experimentId/*")?.params.experimentId;
}

export function useEvidence() {
  const id = useExperimentId();
  const [params] = useSearchParams();
  const guided = useLocation().pathname === "/walkthrough";
  const candidate = guided ? walkthroughStep(params).candidate : params.get("candidate") ?? undefined;
  const partition = !guided && params.get("partition") === "holdout" ? "holdout" : "out_of_fold";
  return useMemo(() => evidenceApi(id, candidate, partition), [id, candidate, partition]);
}
