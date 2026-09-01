import { existsSync, mkdirSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { expect } from '@playwright/test';

const { executePython, logPythonRuntime } = require('../python-runtime.cjs');

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
    return dbValue(`
      select case when
        (select count(*) from sqlite_master where type='table' and name in
          ('produtos','insumos','clientes','vendas','lojas','fm_unidade_loja_legacy_v1')) = 6
        and (select count(*) from fm_unidade_loja_legacy_v1) = 1
        and (select count(*) from fm_unidade_loja_legacy_v1 as m
          join lojas as l on l.id = m.loja_id
          where m.tenant_id = 'tenant-local' and m.unidade_id = 'unidade-local'
            and m.ativo = 1 and l.nome_fantasia = 'Loja Sandbox') = 1
        and (select count(*) from produtos as p
          where p.loja_id is null or p.loja_id !=
            (select loja_id from fm_unidade_loja_legacy_v1
             where tenant_id = 'tenant-local' and unidade_id = 'unidade-local' and ativo = 1)) = 0
        and (select count(*) from insumos as i
          where i.loja_id is null or i.loja_id !=
            (select loja_id from fm_unidade_loja_legacy_v1
             where tenant_id = 'tenant-local' and unidade_id = 'unidade-local' and ativo = 1)) = 0
      then 1 else 0 end
    `);
  }, { message: `aguardando escopo canônico do banco temporário em ${testDbPath}`, timeout: 15_000 }).toBe('1');
}

export function dbValue(sql: string): string {
  const script = `import sqlite3\nconn=sqlite3.connect(${JSON.stringify(testDbPath)})\ncur=conn.cursor()\ncur.execute(${JSON.stringify(sql)})\nrow=cur.fetchone()\nprint('' if row is None or row[0] is None else row[0])\nconn.close()`;
  return executePython(['-c', script], {
    cwd: process.cwd(),
    env: process.env,
    label: 'Consulta ao banco E2E',
  }).stdout.trim();
}

export function dbNumber(sql: string): number {
  const raw = dbValue(sql);
  return raw === '' ? 0 : Number(raw);
}

export function resetTestDb() {
  mkdirSync(testTmpDir, { recursive: true });
  const cwd = process.cwd();
  const env = {
    ...process.env,
    FM_AI_TEST_MODE: '1',
    FM_AI_TEST_RESET_ON_START: '1',
    FM_AI_TEST_TMPDIR: testTmpDir,
  };
  logPythonRuntime({ cwd, dbPath: testDbPath, env });
  const result = executePython(['tests/e2e/reset_test_db.py'], {
    cwd,
    env,
    label: 'Reset do banco E2E',
  });
  if (result.stdout) process.stdout.write(result.stdout);
  if (result.stderr) process.stderr.write(result.stderr);
}

export function realDbSnapshot() {
  if (!existsSync(realDbPath)) return { exists: false, size: 0, mtimeMs: 0 };
  const stat = statSync(realDbPath);
  return { exists: true, size: stat.size, mtimeMs: stat.mtimeMs };
}
