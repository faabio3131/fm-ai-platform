import { defineConfig, devices } from '@playwright/test';
import { resolve } from 'node:path';

const testTmpDir = resolve(__dirname, '.tmp', 'fm-ai-playwright');
process.env.FM_AI_TEST_MODE = '1';
process.env.FM_AI_TEST_RESET_ON_START = '1';
process.env.FM_AI_TEST_TMPDIR = testTmpDir;
process.env.FM_AI_TEST_KEEP_TMP = '1';

export default defineConfig({
  testDir: './tests/e2e',
  globalSetup: './tests/e2e/global-setup.ts',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  workers: 1,
  fullyParallel: false,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  use: {
    baseURL: 'http://localhost:8501',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'node tests/e2e/start-streamlit-test.cjs',
    url: 'http://localhost:8501/_stcore/health',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
