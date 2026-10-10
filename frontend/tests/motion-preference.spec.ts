import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem("sidekick.walkthrough.intro.dismissed", "true"));
});

test("app motion override restores canvas and beam under system reduced motion and survives refresh", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.addInitScript(() => localStorage.setItem("sidekick-theme", "dark"));
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  const toggle = page.getByRole("switch", { name: "Animations", exact: true });
  const canvas = page.locator("canvas");
  await expect(toggle).toHaveAttribute("aria-checked", "false");
  await expect(canvas.locator("..")).toHaveAttribute("data-active", "false");
  await toggle.focus();
  await page.keyboard.press("Space");
  await expect(toggle).toHaveAttribute("aria-checked", "true");
  await expect(canvas.locator("..")).toHaveAttribute("data-active", "true");
  expect(await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches)).toBe(true);
  await expect.poll(() => page.locator("[data-beam]").evaluate(beam => getComputedStyle(beam).animationName)).toContain("beam-spin");
  expect(await page.locator("[data-beam]").evaluate(beam => getComputedStyle(beam, "::before").display)).not.toBe("none");
  const beamAngle = () => page.locator("[data-beam]").evaluate(beam => getComputedStyle(beam).getPropertyValue(`--beam-angle-${beam.getAttribute("data-beam")}`));
  const angle = await beamAngle();
  expect(angle).not.toBe("");
  await expect.poll(beamAngle).not.toBe(angle);
  await page.mouse.move(850, 340);
  const pixels = await canvas.evaluate(canvas => (canvas as HTMLCanvasElement).toDataURL());
  await expect.poll(() => canvas.evaluate(canvas => (canvas as HTMLCanvasElement).toDataURL())).not.toBe(pixels);
  await page.reload();
  await expect(toggle).toHaveAttribute("aria-checked", "true");
  await expect(canvas.locator("..")).toHaveAttribute("data-active", "true");
  const count = page.locator(".benchmark-bars [data-rolling-number]").first();
  await expect(count.locator('> span[aria-hidden="true"]').nth(1)).toHaveText((await count.getAttribute("data-value"))!);
  await page.screenshot({ path: "../output/playwright/remediation/overview-animations-enabled.png" });
  await toggle.click();
  await expect(canvas.locator("..")).toHaveAttribute("data-active", "false");
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await expect(toggle).toHaveAttribute("aria-checked", "false");
  expect(await page.locator("[data-beam]").evaluate(beam => getComputedStyle(beam).animationName)).toBe("none");
  const still = await canvas.evaluate(canvas => (canvas as HTMLCanvasElement).toDataURL());
  await page.mouse.move(550, 250);
  await page.waitForTimeout(180);
  expect(await canvas.evaluate(canvas => (canvas as HTMLCanvasElement).toDataURL())).toBe(still);
  await page.reload();
  await expect(toggle).toHaveAttribute("aria-checked", "false");
  await expect(canvas.locator("..")).toHaveAttribute("data-active", "false");
});

for (const reducedMotion of ["no-preference", "reduce"] as const) {
  test(`overview numbers roll and bars grow with animations enabled under ${reducedMotion}`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion });
    if (reducedMotion === "reduce") await page.addInitScript(() => localStorage.setItem("sidekick-motion", "full"));
    // Hold the recorded selection until the page is mounted, so capture starts
    // at the entrance animation rather than after an arbitrary network delay.
    let release!: () => void;
    const admitted = new Promise<void>(resolve => { release = resolve; });
    await page.route("**/api/selection**", async route => { await admitted; await route.continue(); });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("switch", { name: "Animations", exact: true })).toHaveAttribute("aria-checked", "true");
    const movement = page.evaluate(async () => {
      const values = new Set<string>();
      const scales: number[] = [];
      const deadline = performance.now() + 2500;
      while (performance.now() < deadline) {
        const counter = document.querySelector(".benchmark-bars [data-rolling-number]");
        if (counter) values.add(counter.querySelectorAll(':scope > span[aria-hidden="true"]')[1]?.textContent ?? "");
        const fill = document.querySelector("[data-overview-fill]");
        if (fill) {
          const transform = getComputedStyle(fill).transform;
          scales.push(transform === "none" ? 1 : new DOMMatrixReadOnly(transform).a);
        }
        await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
      }
      return { values: [...values], scales };
    });
    release();
    const observed = await movement;
    expect(observed.values.length).toBeGreaterThan(2);
    expect(observed.scales.some(scale => scale > 0 && scale < .95)).toBe(true);
    expect(observed.scales.at(-1)).toBeCloseTo(1);
    const counter = page.locator(".benchmark-bars [data-rolling-number]").first();
    await expect(counter.locator('> span[aria-hidden="true"]').nth(1)).toHaveText((await counter.getAttribute("data-value"))!);
  });
}
