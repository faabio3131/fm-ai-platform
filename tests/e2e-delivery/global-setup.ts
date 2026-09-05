import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const { executePython } = require('../e2e/python-runtime.cjs');

const TEST_MASTER_KEY = 'ookbIbOksrj9AVVux_O3oSJL7g2qklErzJOWD8bswaY=';

export default async function globalSetup() {
  const root = resolve(__dirname, '..', '..');
  const tmpDir = resolve(root, '.tmp', 'fm-ai-playwright', 'delivery-f11e');
  const env = {
    ...process.env,
    FM_AI_TEST_MODE: '1',
    FM_AI_DELIVERY_V1: '1',
    FM_AI_TEST_TMPDIR: tmpDir,
    FM_AI_SECRET_MASTER_KEY: TEST_MASTER_KEY,
  };
  mkdirSync(tmpDir, { recursive: true });
  executePython(['tests/e2e-delivery/seed_delivery.py'], {
    cwd: root,
    env,
    label: 'Seed E2E Delivery F11-E',
  });
}
