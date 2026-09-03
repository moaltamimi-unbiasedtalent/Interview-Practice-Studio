import { expect, test } from "@playwright/test";

// Critical candidate journeys against a locally running app. These avoid paid
// calls: the unified Home, navigation into Interview Practice, the mode cards and
// the setup form. A full Text interview that calls OpenRouter is run only with a
// key present and is intentionally not asserted here. Live is experimental and
// hidden by default (INTERVIEW_LIVE_ENABLED), so it is not part of the smoke.

test("home shows the unified product and can start practising", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Interview OS Coach").first()).toBeVisible();
  // The two product entry points are present.
  await expect(page.getByText("Career Intelligence", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("Interview Practice", { exact: false }).first()).toBeVisible();

  // Home → Interview Practice via the "Start practising" card button.
  await page.getByRole("button", { name: /Start practising/i }).click();
  await expect(page.getByText("Interview Practice Studio").first()).toBeVisible({
    timeout: 20_000,
  });
});

test("interview setup shows Text/Voice modes (Live hidden) and the setup form", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Start practising/i }).click();

  await expect(page.getByText("How would you like to practise?")).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText("Text", { exact: false })).toBeVisible();
  await expect(page.getByText("Voice", { exact: false })).toBeVisible();
  // Live is experimental and hidden by default.
  await expect(page.getByText("Live", { exact: false })).toHaveCount(0);

  await expect(page.getByText("Set up your interview")).toBeVisible();
  await expect(page.getByText("Target role", { exact: false }).first()).toBeVisible();
});

test("interview sidebar menu is available after navigating", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Start practising/i }).click();
  const menu = page.getByText("New Practice", { exact: false });
  await expect(menu.first()).toBeVisible({ timeout: 20_000 });
});
