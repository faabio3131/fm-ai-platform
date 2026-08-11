import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const { executePython } = require('../e2e/python-runtime.cjs');

export default async function globalSetup() {
  const root = resolve(__dirname, '..', '..');
  const tmpDir = resolve(root, '.tmp', 'fm-ai-playwright', 'entrega');
  const env = {
    ...process.env,
    FM_AI_TEST_MODE: '1',
    FM_AI_ENTREGA_V1: '1',
    FM_AI_TEST_TMPDIR: tmpDir,
  };
  mkdirSync(tmpDir, { recursive: true });
  executePython(['tests/e2e-entrega/seed_entrega.py'], {
    cwd: root,
    env,
    label: 'Seed E2E Entrega',
  });
}
