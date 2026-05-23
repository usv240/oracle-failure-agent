import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,        // Serialize — server has Gemini/Voyage AI rate limits
  retries: 1,        // One retry for flaky network/rate-limit blips
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:8080',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    actionTimeout: 15_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // Server must be running before tests — start it manually with:
  // uvicorn backend.main:app --port 8080
});
