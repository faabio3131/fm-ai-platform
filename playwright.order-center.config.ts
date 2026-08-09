import { defineConfig } from '@playwright/test';
import { resolve } from 'node:path';

const root = __dirname;
const tmpDir = resolve(root, '.tmp', 'fm-ai-playwright', 'order-center');

export default defineConfig({
  testDir: './tests/e2e-orders-center',
  globalSetup: './tests/e2e-orders-center/global-setup.ts',
  timeout: 45_000,
  use: { baseURL: 'http://127.0.0.1:8521', trace: 'retain-on-failure' },
  webServer: {
    command: 'node tests/e2e/start-streamlit-test.cjs',
    url: 'http://127.0.0.1:8521',
    timeout: 120_000,
    reuseExistingServer: false,
    env: {
      ...process.env,
      FM_AI_TEST_MODE: '1',
      FM_AI_ORDER_CENTER_V1: '1',
      FM_AI_E2E_PORT: '8521',
      FM_AI_TEST_TMPDIR: tmpDir,
    },
  },
  projects: [
    {
      name: 'warmup',
      testMatch: /warmup\.setup\.ts/,
    },
    {
      name: 'central',
      testMatch: /central\.spec\.ts/,
      dependencies: ['warmup'],
    },
  ],
});
