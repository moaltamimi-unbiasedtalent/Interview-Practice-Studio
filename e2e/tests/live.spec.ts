import { expect, test } from "@playwright/test";

// Live feature-flag browser test. Runs against the INTERVIEW_LIVE_ENABLED=true
// instance on :8502. No provider socket is opened (no paid calls): we only assert
// the flag surfaces the Live mode card. The realtime Live lifecycle (barge-in,
// interruption, session/token/reconnect) is covered by the frontend unit suite
// (components/live_interviewer/frontend/src/__tests__/lifecycle.test.ts).
test.use({ baseURL: "http://localhost:8502" });

test("Live mode card appears when the feature flag is on", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Start practising/i }).click();
  await expect(page.getByText("How would you like to practise?")).toBeVisible({
    timeout: 20_000,
  });
  // With the flag ON, all three cards are offered.
  await expect(page.getByText("💬 Text", { exact: true })).toBeVisible();
  await expect(page.getByText("🎙️ Voice", { exact: true })).toBeVisible();
  await expect(page.getByText("🎥 Live", { exact: true })).toBeVisible();
});
