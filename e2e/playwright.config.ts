import { defineConfig, devices } from "@playwright/test";

// Browser E2E runs against a locally running Streamlit app (BASE_URL), not in
// CI: it needs a live server and installed browsers. Paid provider calls are
// avoided by exercising the Text flow / fallbacks only.
export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: process.env.BASE_URL || "http://localhost:8501",
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
