const { spawn } = require('node:child_process');
const { mkdirSync } = require('node:fs');
const { resolve } = require('node:path');
const { resolvePython } = require('../e2e/python-runtime.cjs');

const root = resolve(__dirname, '..', '..');
const tmpDir = process.env.FM_AI_TEST_TMPDIR
  ? resolve(process.env.FM_AI_TEST_TMPDIR)
  : resolve(root, '.tmp', 'fm-ai-playwright', 'salao');
const port = process.env.FM_AI_E2E_PORT || '8523';
mkdirSync(tmpDir, { recursive: true });

const env = {
  ...process.env,
  FM_AI_TEST_MODE: '1',
  FM_AI_SALAO_V1: '1',
  FM_AI_TEST_RESET_ON_START: '0',
  FM_AI_TEST_TMPDIR: tmpDir,
  FM_AI_TEST_KEEP_TMP: '1',
};

const python = resolvePython(env);
const app = resolve(__dirname, 'app_salao.py');
const child = spawn(
  python,
  [
    '-m',
    'streamlit',
    'run',
    app,
    '--server.address',
    '127.0.0.1',
    '--server.port',
    port,
    '--server.headless',
    'true',
  ],
  {
    cwd: root,
    env,
    stdio: 'inherit',
    shell: false,
  },
);

child.on('error', error => {
  console.error(`[fm-ai-salao-e2e] Falha ao iniciar ${python}:`, error);
  process.exit(1);
});
child.on('exit', (code, signal) => {
  console.log(`[fm-ai-salao-e2e] Streamlit encerrou (code=${code}, signal=${signal}).`);
  process.exit(code ?? (signal ? 1 : 0));
});

function stopChild(signal) {
  if (!child.killed) child.kill(signal);
}

process.on('SIGTERM', () => stopChild('SIGTERM'));
process.on('SIGINT', () => stopChild('SIGINT'));
