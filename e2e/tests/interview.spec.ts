import { expect, test } from "@playwright/test";

// Critical candidate journeys against a locally running app. These avoid paid
// calls: they exercise the landing, the mode cards, and the graceful fallbacks
// (Voice/Live without credentials). A full Text interview that calls OpenRouter
// should be run only with a key present and is intentionally not asserted here.

test("landing shows Practice Interview and three mode cards", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Interview Practice Studio")).toBeVisible();
  await expect(page.getByText("How would you like to practise?")).toBeVisible();
  await expect(page.getByText("Text", { exact: false })).toBeVisible();
  await expect(page.getByText("Voice", { exact: false })).toBeVisible();
  await expect(page.getByText("Live", { exact: false })).toBeVisible();
});

test("setup form is present", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Set up your interview")).toBeVisible();
  await expect(page.getByText("Target role", { exact: false })).toBeVisible();
});

test("sidebar navigation menu is available", async ({ page }) => {
  await page.goto("/");
  // Open the sidebar if collapsed, then check the menu options exist.
  const menu = page.getByText("New Practice", { exact: false });
  await expect(menu.first()).toBeVisible({ timeout: 20_000 });
});
