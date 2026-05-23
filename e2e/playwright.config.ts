import { defineConfig, devices } from "@playwright/test";

const executablePath = process.env.PLAYWRIGHT_EXECUTABLE_PATH;

export default defineConfig({
  testDir: ".",
  timeout: 90_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: process.env.AGENTHUB_E2E_BASE_URL ?? "http://localhost:5173",
    trace: "on-first-retry",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: executablePath ? { executablePath } : undefined,
      },
    },
  ],
});
