import { defineConfig, devices } from '@playwright/test';
import { resolve } from 'node:path';

const port = 8519;
process.env.FM_AI_TEST_MODE = '1';
process.env.FM_AI_TEST_RESET_ON_START = '1';
process.env.FM_AI_TEST_TMPDIR = resolve(__dirname, '.tmp', 'fm-ai-playwright');
process.env.FM_AI_TEST_KEEP_TMP = '1';
process.env.FM_AI_E2E_PORT = String(port);
process.env.FM_AI_PDV_MODE = 'authoritative_canary';
process.env.FM_AI_TEST_TENANT = 'tenant-e2e';
process.env.FM_AI_TEST_UNIDADE = 'unidade-e2e';
process.env.FM_AI_TEST_TERMINAL = 'caixa-e2e';

export default defineConfig({
  testDir: './tests/e2e-pdv', testMatch: 'canary.spec.ts', workers: 1,
  globalSetup: './tests/e2e/global-setup.ts', timeout: 120_000,
  use: { baseURL: `http://127.0.0.1:${port}` },
  webServer: {
    command: 'node tests/e2e/start-streamlit-test.cjs',
    url: `http://127.0.0.1:${port}/_stcore/health`, reuseExistingServer: false,
    timeout: 120_000,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
