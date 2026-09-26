import { useMemo } from "react";
import { useMatch } from "react-router-dom";
import { evidenceApi } from "../api/client";

export function useExperimentId() {
  return useMatch("/experiments/:experimentId/*")?.params.experimentId;
}

export function useEvidence() {
  const id = useExperimentId();
  return useMemo(() => evidenceApi(id), [id]);
}
