import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const { executePython } = require('../e2e/python-runtime.cjs');

export default async function globalSetup() {
  const root = resolve(__dirname, '..', '..');
  const tmpDir = resolve(root, '.tmp', 'fm-ai-playwright', 'kds');
  const env = {
    ...process.env,
    FM_AI_TEST_MODE: '1',
    FM_AI_KDS_V1: '1',
    FM_AI_TEST_TMPDIR: tmpDir,
  };
  mkdirSync(tmpDir, { recursive: true });
  executePython(['tests/e2e/init_test_db.py'], { cwd: root, env, label: 'Banco E2E KDS' });
  executePython(['tests/e2e-kds/seed_kds.py'], { cwd: root, env, label: 'Seed E2E KDS' });
}
