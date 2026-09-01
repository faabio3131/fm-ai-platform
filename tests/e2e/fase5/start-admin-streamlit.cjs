const { spawn } = require('node:child_process');
const { mkdirSync } = require('node:fs');
const { resolve, join } = require('node:path');

const root = resolve(__dirname, '..', '..', '..');
const tmpDir = resolve(root, '.tmp', 'fm-ai-playwright-f5');
const dbPath = join(tmpDir, 'admin-f5.sqlite3');
const port = process.env.FM_AI_F5_E2E_PORT || '8525';
mkdirSync(tmpDir, { recursive: true });

const normalizedDb = dbPath.replace(/\\/g, '/');
const env = {
  ...process.env,
  FM_AI_ENV: 'staging',
  DATABASE_URL: 'sqlite:///' + normalizedDb,
  FM_AI_ALLOW_SQLITE_COMMERCIAL: '1',
  FM_AI_TENANT_ID: 'tenant-f5-e2e',
  FM_AI_UNIDADE_ID: 'matriz-f5-e2e',
  PYTHONPATH: root,
};

const python = process.env.PYTHON || process.env.PYTHON_EXECUTABLE || 'python';
const child = spawn(
  python,
  [
    '-m',
    'streamlit',
    'run',
    resolve(root, 'pages/6_Administracao_Proprietario.py'),
    '--server.address',
    '127.0.0.1',
    '--server.port',
    port,
    '--server.headless',
    'true',
  ],
  { cwd: root, env, stdio: 'inherit', shell: false },
);

child.on('error', error => {
  console.error('[fm-ai-f5-e2e] Falha ao iniciar Streamlit:', error);
  process.exit(1);
});
child.on('exit', (code, signal) => {
  console.log(`[fm-ai-f5-e2e] Streamlit encerrou (code=${code}, signal=${signal}).`);
  process.exit(code ?? (signal ? 1 : 0));
});

function stop(signal) {
  if (!child.killed) child.kill(signal);
}
process.on('SIGTERM', () => stop('SIGTERM'));
process.on('SIGINT', () => stop('SIGINT'));
