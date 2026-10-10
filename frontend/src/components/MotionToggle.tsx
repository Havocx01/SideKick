import { CirclePause, Orbit } from "lucide-react";
import { setMotionPreference, useMotionPreference } from "../hooks/useMotionPreference";
import { Button } from "./Chrome";

export function MotionToggle() {
  const reduced = useMotionPreference();
  return <Button variant="ghost" className="theme-toggle icon-button" role="switch" aria-label="Animations" aria-checked={!reduced}
    title={reduced ? "Turn animations on" : "Turn animations off"} onClick={() => setMotionPreference(!reduced)}>
    {reduced ? <CirclePause size={17} aria-hidden="true" /> : <Orbit size={17} aria-hidden="true" />}
  </Button>;
}
