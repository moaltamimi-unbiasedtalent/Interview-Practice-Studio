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
  // Start two Streamlit apps for the run (reused locally if already up): the
  // default product (Live OFF) on 8501 and a Live-flag-ON instance on 8502 for
  // the feature-flag test. Both are installed first (see .github/workflows/e2e.yml).
  webServer: [
    {
      command:
        "python -m streamlit run ../app.py --server.headless true " +
        "--server.port 8501 --browser.gatherUsageStats false",
      url: "http://localhost:8501",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command:
        "python -m streamlit run ../app.py --server.headless true " +
        "--server.port 8502 --browser.gatherUsageStats false",
      url: "http://localhost:8502",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { INTERVIEW_LIVE_ENABLED: "true" },
    },
  ],
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
