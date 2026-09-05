import { resolve } from 'node:path';

import { defineConfig, devices } from '@playwright/test';

const root = resolve(__dirname);
const tmpDir = resolve(root, '.tmp', 'fm-ai-playwright', 'delivery-f11e');
const testMasterKey = 'ookbIbOksrj9AVVux_O3oSJL7g2qklErzJOWD8bswaY=';

export default defineConfig({
  testDir: './tests/e2e-delivery',
  globalSetup: './tests/e2e-delivery/global-setup.ts',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:8525',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command:
      'python -m streamlit run tests/e2e-delivery/app_delivery.py --server.headless true --server.port 8525 --server.address 127.0.0.1',
    url: 'http://127.0.0.1:8525',
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      ...process.env,
      FM_AI_TEST_MODE: '1',
      FM_AI_DELIVERY_V1: '1',
      FM_AI_TEST_TMPDIR: tmpDir,
      FM_AI_SECRET_MASTER_KEY: testMasterKey,
    },
  },
});
