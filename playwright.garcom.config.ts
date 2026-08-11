import { defineConfig } from '@playwright/test';
import { resolve } from 'node:path';

const root = __dirname;
const tmpDir = resolve(root, '.tmp', 'fm-ai-playwright', 'garcom');

export default defineConfig({
  testDir: './tests/e2e-garcom',
  globalSetup: './tests/e2e-garcom/global-setup.ts',
  timeout: 60_000,
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:8524',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'node tests/e2e-garcom/start-garcom-streamlit.cjs',
    url: 'http://127.0.0.1:8524',
    timeout: 120_000,
    reuseExistingServer: false,
    env: {
      ...process.env,
      FM_AI_TEST_MODE: '1',
      FM_AI_GARCOM_V1: '1',
      FM_AI_SALAO_V1: '1',
      FM_AI_KDS_V1: '1',
      FM_AI_E2E_PORT: '8524',
      FM_AI_TEST_TMPDIR: tmpDir,
    },
  },
  projects: [
    {
      name: 'garcom-mobile',
      testMatch: /garcom\.spec\.ts/,
      use: { viewport: { width: 390, height: 844 } },
    },
    {
      name: 'garcom-tablet',
      testMatch: /gerente\.spec\.ts/,
      use: { viewport: { width: 820, height: 1180 } },
    },
  ],
});
