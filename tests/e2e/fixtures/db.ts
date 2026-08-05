import { execFileSync } from 'node:child_process';
import { existsSync, statSync } from 'node:fs';
import { join } from 'node:path';

export const testDbPath = join(process.cwd(), '.tmp', 'fm-ai-playwright', 'fm_ai_test.sqlite3');
export const realDbPath = join(process.cwd(), 'banco_erp_local.db');

export function dbValue(sql: string): string {
  const script = `import sqlite3\nconn=sqlite3.connect(${JSON.stringify(testDbPath)})\ncur=conn.cursor()\ncur.execute(${JSON.stringify(sql)})\nrow=cur.fetchone()\nprint('' if row is None or row[0] is None else row[0])\nconn.close()`;
  return execFileSync('python', ['-c', script], { encoding: 'utf-8' }).trim();
}

export function dbNumber(sql: string): number {
  const raw = dbValue(sql);
  return raw === '' ? 0 : Number(raw);
}

export function realDbSnapshot() {
  if (!existsSync(realDbPath)) return { exists: false, size: 0, mtimeMs: 0 };
  const stat = statSync(realDbPath);
  return { exists: true, size: stat.size, mtimeMs: stat.mtimeMs };
}
