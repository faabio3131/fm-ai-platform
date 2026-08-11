import { defineConfig } from '@playwright/test';
import { resolve } from 'node:path';

const root = __dirname;
const tmpDir = resolve(root, '.tmp', 'fm-ai-playwright', 'entrega');

export default defineConfig({
  testDir: './tests/e2e-entrega',
  globalSetup: './tests/e2e-entrega/global-setup.ts',
  timeout: 60_000,
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:8525',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'node tests/e2e-entrega/start-entrega-streamlit.cjs',
    url: 'http://127.0.0.1:8525',
    timeout: 120_000,
    reuseExistingServer: false,
    env: {
      ...process.env,
      FM_AI_TEST_MODE: '1',
      FM_AI_ENTREGA_V1: '1',
      FM_AI_E2E_PORT: '8525',
      FM_AI_TEST_TMPDIR: tmpDir,
    },
  },
  projects: [
    {
      name: 'expedicao-tablet',
      testMatch: /expedicao\.spec\.ts/,
      use: { viewport: { width: 1024, height: 900 } },
    },
    {
      name: 'entregador-mobile',
      testMatch: /entregador\.spec\.ts/,
      use: { viewport: { width: 390, height: 844 } },
    },
  ],
});
