import { execFileSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { resolve, join } from 'node:path';

export default async function globalSetup() {
  const root = resolve(__dirname, '..', '..', '..');
  const tmpDir = resolve(root, '.tmp', 'fm-ai-playwright-f5');
  const dbPath = join(tmpDir, 'admin-f5.sqlite3');
  mkdirSync(tmpDir, { recursive: true });

  const python = process.env.PYTHON || process.env.PYTHON_EXECUTABLE || 'python';
  execFileSync(
    python,
    [resolve(root, 'tests/e2e/fase5/init_admin_browser_db.py')],
    {
      cwd: root,
      env: {
        ...process.env,
        FM_AI_F5_E2E_DB_PATH: dbPath,
        PYTHONPATH: root,
      },
      stdio: 'inherit',
    },
  );
}
