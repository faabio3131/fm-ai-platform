import { defineConfig } from '@playwright/test';
import { resolve } from 'node:path';

const root = __dirname;
const tmpDir = resolve(root, '.tmp', 'fm-ai-playwright', 'kds');

export default defineConfig({
  testDir: './tests/e2e-kds',
  globalSetup: './tests/e2e-kds/global-setup.ts',
  timeout: 60_000,
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:8522',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'node tests/e2e-kds/start-kds-streamlit.cjs',
    url: 'http://127.0.0.1:8522',
    timeout: 120_000,
    reuseExistingServer: false,
    env: {
      ...process.env,
      FM_AI_TEST_MODE: '1',
      FM_AI_KDS_V1: '1',
      FM_AI_E2E_PORT: '8522',
      FM_AI_TEST_TMPDIR: tmpDir,
    },
  },
  projects: [
    {
      name: 'kds',
      testMatch: /kds\.spec\.ts/,
    },
  ],
});
