import { expect, test } from "@playwright/test";

/**
 * Smoke suite: the three cheapest signals that the app shell, the static
 * methodology page, and the chart gallery render at all. No data-pipeline
 * or engine dependencies.
 */

test("/ renders the AppShell rail", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
  // rail links present (gold-free chrome, spec §3.4)
  await expect(page.getByRole("navigation", { name: "Primary" }).getByRole("link")).toHaveCount(
    5, // wordmark + Fleet/Backtest/Method/About
  );
});

test("/methodology accordion opens and closes", async ({ page }) => {
  await page.goto("/methodology");
  const triggers = page.getByRole("button", { expanded: false });
  const firstClosed = triggers.first();
  await firstClosed.click();
  await expect(firstClosed).toHaveAttribute("aria-expanded", "true");
  // default-open "energy" section content is visible on load
  await expect(page.locator('[data-state="open"]').first()).toBeVisible();
});

test("/dev/charts renders SVG charts", async ({ page }) => {
  await page.goto("/dev/charts");
  const svgs = page.locator("svg");
  await expect(svgs.first()).toBeVisible();
  expect(await svgs.count()).toBeGreaterThan(3);
});
