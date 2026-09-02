import { defineConfig, devices } from '@playwright/test';

const port = 8528;
const baseURL = `http://127.0.0.1:${port}`;

delete process.env.FM_AI_TEST_MODE;
delete process.env.FM_AI_TEST_RESET_ON_START;
delete process.env.FM_AI_TEST_TMPDIR;
process.env.FM_AI_E2E_PORT = String(port);

const executable = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
const launchOptions = executable ? { executablePath: executable } : undefined;

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: /f7f-commercial-.*\.spec\.ts/,
  timeout: 120_000,
  expect: { timeout: 25_000 },
  workers: 1,
  fullyParallel: false,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report-f7f' }]],
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
      name: 'f7f-desktop',
      use: { ...devices['Desktop Chrome'], launchOptions },
    },
    {
      name: 'f7f-mobile',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 390, height: 844 },
        launchOptions,
      },
    },
    {
      name: 'f7f-tablet',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 820, height: 1180 },
        launchOptions,
      },
    },
  ],
});
