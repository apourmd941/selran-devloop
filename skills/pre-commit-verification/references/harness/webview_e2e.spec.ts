// Smoke test [5]: browser quirks — headless webview e2e.
//
// A desktop app's webview (WKWebView on macOS, WebView2 on Windows) is NOT the
// same engine as the dev browser. Code that works against Chrome in `npm run
// dev` can break in WKWebView: different CSP enforcement, missing APIs, custom
// scheme handling (tauri://), storage quirks. This drives the ACTUAL app webview
// and asserts the core path renders and is interactive.
//
// Two ways to run, in order of fidelity:
//   1. Drive the launched .app's webview directly (highest fidelity; needs a
//      WebDriver bridge such as tauri-driver / WebKitWebDriver).
//   2. Fall back to Playwright's webkit engine pointed at the built frontend
//      (catches most engine-quirk issues without bundling).
//
// CUSTOMIZE: the launch/connect strategy, the app URL/scheme, and the selectors.

import { test, expect } from "@playwright/test";

// CUSTOMIZE: how the e2e harness reaches the app.
//   For a real bundle via tauri-driver, configure playwright.config to talk to
//   the WebDriver endpoint. For the webkit-fallback, point at the built frontend.
const APP_URL = process.env.SMOKE_APP_URL ?? "http://127.0.0.1:1420"; // CUSTOMIZE

test.describe("@smoke webview core path", () => {
  test("app shell renders in the webview engine", async ({ page }) => {
    await page.goto(APP_URL, { waitUntil: "domcontentloaded" });

    // CUSTOMIZE: a selector that only exists once the app shell has mounted.
    const shell = page.locator('[data-testid="app-shell"]'); // CUSTOMIZE
    await expect(shell).toBeVisible({ timeout: 15_000 });
  });

  test("no console errors during initial render", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    page.on("pageerror", (err) => errors.push(String(err)));

    await page.goto(APP_URL, { waitUntil: "networkidle" });

    // WKWebView surfaces CSP violations and missing-API errors as console errors
    // that Chrome may not. A clean console here is a real signal.
    expect(
      errors,
      `webview produced console errors during render:\n${errors.join("\n")}`,
    ).toHaveLength(0);
  });

  test("a core interaction works (not just renders)", async ({ page }) => {
    await page.goto(APP_URL, { waitUntil: "domcontentloaded" });

    // CUSTOMIZE: click the primary action and assert the result. Rendering is
    // necessary but not sufficient — prove the webview can actually drive the app.
    // await page.locator('[data-testid="primary-action"]').click();
    // await expect(page.locator('[data-testid="result"]')).toBeVisible();
  });
});
