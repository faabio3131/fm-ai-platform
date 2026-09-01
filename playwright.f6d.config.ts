import { defineConfig, devices } from '@playwright/test';

const port = 8527;
const baseURL = `http://127.0.0.1:${port}`;

delete process.env.FM_AI_TEST_MODE;
delete process.env.FM_AI_TEST_RESET_ON_START;
delete process.env.FM_AI_TEST_TMPDIR;
process.env.FM_AI_E2E_PORT = String(port);

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 120_000,
  expect: { timeout: 20_000 },
  workers: 1,
  fullyParallel: false,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report-f6d' }]],
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: {
    command: 'node tests/e2e/start-streamlit-f6d-commercial.cjs',
    url: `${baseURL}/_stcore/health`,
    reuseExistingServer: false,
    timeout: 120_000,
    gracefulShutdown: { signal: 'SIGTERM', timeout: 5_000 },
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
          ? { launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } }
          : {}),
      },
    },
  ],
});
