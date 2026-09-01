import { defineConfig, devices } from '@playwright/test';
import { resolve } from 'node:path';

const testTmpDir = resolve(__dirname, '.tmp', 'fm-ai-playwright-mica');
const e2ePort = 8522;
const e2eBaseURL = `http://127.0.0.1:${e2ePort}`;
process.env.FM_AI_TEST_MODE = '1';
process.env.FM_AI_TEST_RESET_ON_START = '1';
process.env.FM_AI_TEST_TMPDIR = testTmpDir;
process.env.FM_AI_TEST_KEEP_TMP = '1';
process.env.FM_AI_E2E_PORT = String(e2ePort);
process.env.FM_AI_ASSISTENTE_ATENDIMENTO_V1 = '1';

export default defineConfig({
  testDir: './tests/e2e-mica',
  timeout: 120_000,
  expect: { timeout: 15_000 },
  workers: 1,
  fullyParallel: false,
  reporter: [['list']],
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
