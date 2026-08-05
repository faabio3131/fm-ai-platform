import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, statSync, unlinkSync } from 'node:fs';
import { resolve, join } from 'node:path';

async function globalSetup() {
  const root = resolve(__dirname, '..', '..');
  const tmpDir = resolve(root, '.tmp', 'fm-ai-playwright');
  const dbPath = join(tmpDir, 'fm_ai_test.sqlite3');
  const realDbPath = resolve(root, 'banco_erp_local.db');

  if (resolve(dbPath) === realDbPath) {
    throw new Error(`Caminho do banco de teste resolveu para o banco real: ${dbPath}`);
  }

  mkdirSync(tmpDir, { recursive: true });
  if (existsSync(dbPath)) unlinkSync(dbPath);

  process.env.FM_AI_TEST_MODE = '1';
  process.env.FM_AI_TEST_RESET_ON_START = '1';
  process.env.FM_AI_TEST_TMPDIR = tmpDir;
  process.env.FM_AI_TEST_KEEP_TMP = '1';

  execFileSync('python', ['tests/e2e/init_test_db.py'], {
    cwd: root,
    env: process.env,
    stdio: 'inherit',
  });

  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    if (existsSync(dbPath) && statSync(dbPath).size > 0) return;
    await new Promise(resolveTimeout => setTimeout(resolveTimeout, 250));
  }
  throw new Error(`Banco temporário não ficou pronto após globalSetup: ${dbPath}`);
}

export default globalSetup;
