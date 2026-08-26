import { defineConfig, devices } from '@playwright/test';
import { resolve } from 'node:path';

const root = __dirname;
const testTmpDir = resolve(root, '.tmp', 'fm-ai-playwright');
const e2ePort = 8518;
const e2eBaseURL = `http://127.0.0.1:${e2ePort}`;

// O navegador deve exercer explicitamente o canary autoritativo completo.
process.env.FM_AI_TEST_MODE = '1';
process.env.FM_AI_TEST_RESET_ON_START = '1';
process.env.FM_AI_TEST_TMPDIR = testTmpDir;
process.env.FM_AI_TEST_KEEP_TMP = '1';
process.env.FM_AI_E2E_PORT = String(e2ePort);
process.env.FM_AI_PDV_MODE = 'authoritative_canary';
process.env.FM_AI_TEST_TENANT = 'tenant-local';
process.env.FM_AI_TEST_UNIDADE = 'unidade-local';
process.env.FM_AI_TEST_TERMINAL = 'pdv-e2e';

export default defineConfig({
  testDir: './tests/e2e-pdv',
  testMatch: '**/canary.spec.ts',
  globalSetup: './tests/e2e/global-setup.ts',
  timeout: 120_000,
  expect: { timeout: 20_000 },
  workers: 1,
  fullyParallel: false,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report-pdv' }]],
  use: {
    baseURL: e2eBaseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: {
    command: 'node tests/e2e/start-streamlit-test.cjs',
    url: `${e2eBaseURL}/_stcore/health`,
    reuseExistingServer: false,
    timeout: 120_000,
    gracefulShutdown: { signal: 'SIGTERM', timeout: 5_000 },
    env: {
      ...process.env,
      FM_AI_TEST_MODE: '1',
      FM_AI_TEST_RESET_ON_START: '0',
      FM_AI_TEST_TMPDIR: testTmpDir,
      FM_AI_TEST_KEEP_TMP: '1',
      FM_AI_E2E_PORT: String(e2ePort),
      FM_AI_PDV_MODE: 'authoritative_canary',
      FM_AI_TEST_TENANT: 'tenant-local',
      FM_AI_TEST_UNIDADE: 'unidade-local',
      FM_AI_TEST_TERMINAL: 'pdv-e2e',
    },
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
