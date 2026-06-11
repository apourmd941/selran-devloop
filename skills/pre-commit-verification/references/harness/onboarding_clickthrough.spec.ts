// Smoke test [9]: UX — onboarding click-through.
//
// First-run/onboarding flows are where users actually land, and they're the
// least unit-tested part of an app (lots of state, multiple screens, real
// navigation). This drives the whole onboarding path end to end and asserts the
// user can complete it. Catches dead buttons, broken navigation between steps,
// validation that blocks progress, and "looks fine but the Continue button does
// nothing" bugs.
//
// Runs in the same webview-fidelity setup as webview_e2e.spec.ts.
//
// CUSTOMIZE: the step selectors, inputs, and the success assertion.

import { test, expect } from "@playwright/test";

const APP_URL = process.env.SMOKE_APP_URL ?? "http://127.0.0.1:1420"; // CUSTOMIZE

test.describe("@smoke onboarding click-through", () => {
  test("user can complete onboarding end to end", async ({ page }) => {
    await page.goto(APP_URL, { waitUntil: "domcontentloaded" });

    // CUSTOMIZE: this should reflect your real onboarding steps. Each step:
    //   - assert the step is visible
    //   - perform the required interaction (fill, choose, click)
    //   - advance and assert the next step appears

    // Step 1 — welcome
    const welcome = page.locator('[data-testid="onboarding-welcome"]'); // CUSTOMIZE
    await expect(welcome).toBeVisible({ timeout: 15_000 });
    await page.locator('[data-testid="onboarding-start"]').click(); // CUSTOMIZE

    // Step 2 — example input step
    // await page.locator('[data-testid="account-email"]').fill("test@example.com");
    // await page.locator('[data-testid="onboarding-next"]').click();

    // Step 3 — example permission/choice step
    // await page.locator('[data-testid="grant-access"]').click();
    // await page.locator('[data-testid="onboarding-next"]').click();

    // Final — assert we reached the main app, i.e. onboarding actually completed.
    const mainApp = page.locator('[data-testid="app-shell"]'); // CUSTOMIZE
    await expect(
      mainApp,
      "onboarding did not reach the main app — a step likely failed to advance",
    ).toBeVisible({ timeout: 15_000 });
  });

  test("onboarding does not let the user past a required step empty", async ({ page }) => {
    await page.goto(APP_URL, { waitUntil: "domcontentloaded" });

    // CUSTOMIZE: assert that skipping a required input keeps the user on the step
    // (validation works) rather than silently advancing with bad state.
    // await page.locator('[data-testid="onboarding-start"]').click();
    // await page.locator('[data-testid="onboarding-next"]').click(); // no input
    // await expect(page.locator('[data-testid="validation-error"]')).toBeVisible();
  });
});
