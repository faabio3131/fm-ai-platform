import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { expect } from '@playwright/test';

export const testTmpDir = resolve(process.env.FM_AI_TEST_TMPDIR ?? join(process.cwd(), '.tmp', 'fm-ai-playwright'));
export const testDbPath = join(testTmpDir, 'fm_ai_test.sqlite3');
export const realDbPath = resolve(process.cwd(), 'banco_erp_local.db');

if (resolve(testDbPath) === realDbPath) {
  throw new Error(`Caminho do banco de teste resolveu para o banco real: ${testDbPath}`);
}

export async function waitForTestDb() {
  mkdirSync(testTmpDir, { recursive: true });
  await expect.poll(() => {
    if (!existsSync(testDbPath)) return 'missing';
    if (statSync(testDbPath).size <= 0) return 'empty';
    return dbValue("select count(*) from sqlite_master where type='table' and name in ('produtos','insumos','clientes','vendas')");
  }, { message: `aguardando banco temporário em ${testDbPath}`, timeout: 15_000 }).toBe('4');
}

export function dbValue(sql: string): string {
  const script = `import sqlite3\nconn=sqlite3.connect(${JSON.stringify(testDbPath)})\ncur=conn.cursor()\ncur.execute(${JSON.stringify(sql)})\nrow=cur.fetchone()\nprint('' if row is None or row[0] is None else row[0])\nconn.close()`;
  return execFileSync('python', ['-c', script], { encoding: 'utf-8' }).trim();
}

export function dbNumber(sql: string): number {
  const raw = dbValue(sql);
  return raw === '' ? 0 : Number(raw);
}

export function resetTestDb() {
  mkdirSync(testTmpDir, { recursive: true });
  execFileSync('python', ['tests/e2e/reset_test_db.py'], {
    cwd: process.cwd(),
    env: { ...process.env, FM_AI_TEST_MODE: '1', FM_AI_TEST_RESET_ON_START: '1', FM_AI_TEST_TMPDIR: testTmpDir },
    stdio: 'ignore',
  });
}

export function realDbSnapshot() {
  if (!existsSync(realDbPath)) return { exists: false, size: 0, mtimeMs: 0 };
  const stat = statSync(realDbPath);
  return { exists: true, size: stat.size, mtimeMs: stat.mtimeMs };
}
