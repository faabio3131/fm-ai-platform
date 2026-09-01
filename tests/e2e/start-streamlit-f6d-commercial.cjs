const { spawn } = require('node:child_process');
const { resolve } = require('node:path');
const { resolvePython } = require('./python-runtime.cjs');

const root = resolve(__dirname, '..', '..');
const port = process.env.FM_AI_E2E_PORT || '8527';

if (process.env.FM_AI_TEST_MODE === '1') {
  throw new Error('F6-D commercial launcher refuses FM_AI_TEST_MODE=1');
}

const env = { ...process.env };
delete env.FM_AI_TEST_MODE;
delete env.FM_AI_TEST_RESET_ON_START;
delete env.FM_AI_TEST_TMPDIR;

const python = resolvePython(env);
const child = spawn(
  python,
  [
    '-m',
    'streamlit',
    'run',
    resolve(root, 'app.py'),
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
  console.error('[f6d-commercial] Falha ao iniciar Streamlit:', error);
  process.exit(1);
});
child.on('exit', (code, signal) => {
  console.log(`[f6d-commercial] Streamlit encerrou (code=${code}, signal=${signal}).`);
  process.exit(code ?? (signal ? 1 : 0));
});

function stopChild(signal) {
  if (!child.killed) child.kill(signal);
}

process.on('SIGTERM', () => stopChild('SIGTERM'));
process.on('SIGINT', () => stopChild('SIGINT'));
