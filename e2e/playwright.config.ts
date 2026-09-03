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
  // Start the Streamlit app for the run (reused locally if already up). The app
  // and its Python env must be installed first (see .github/workflows/e2e.yml).
  webServer: {
    command:
      "python -m streamlit run ../app.py --server.headless true " +
      "--server.port 8501 --browser.gatherUsageStats false",
    url: process.env.BASE_URL || "http://localhost:8501",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
