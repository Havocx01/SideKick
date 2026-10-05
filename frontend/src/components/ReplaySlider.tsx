import * as SliderPrimitive from "@radix-ui/react-slider";

// shadcn/ui's Radix slider composition, styled with Sidekick's existing tokens.
export function ReplaySlider({ label, valueText, ...props }: SliderPrimitive.SliderProps & { label: string; valueText: string }) {
  return <SliderPrimitive.Root {...props} className="replay-slider">
    <SliderPrimitive.Track className="replay-slider-track"><SliderPrimitive.Range className="replay-slider-range" /></SliderPrimitive.Track>
    <SliderPrimitive.Thumb className="replay-slider-thumb" aria-label={label} aria-valuetext={valueText} />
  </SliderPrimitive.Root>;
}
