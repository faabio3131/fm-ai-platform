const { spawn } = require('node:child_process');
const { mkdirSync } = require('node:fs');
const { resolve } = require('node:path');

const root = resolve(__dirname, '..', '..');
const tmpDir = resolve(root, '.tmp', 'fm-ai-playwright');
mkdirSync(tmpDir, { recursive: true });

const env = {
  ...process.env,
  FM_AI_TEST_MODE: '1',
  FM_AI_TEST_RESET_ON_START: '0',
  FM_AI_TEST_TMPDIR: tmpDir,
  FM_AI_TEST_KEEP_TMP: '1',
};

const child = spawn('streamlit', ['run', 'app.py', '--server.port', '8501', '--server.headless', 'true'], {
  cwd: root,
  env,
  stdio: 'inherit',
  shell: process.platform === 'win32',
});

child.on('exit', code => process.exit(code ?? 0));
process.on('SIGTERM', () => child.kill('SIGTERM'));
process.on('SIGINT', () => child.kill('SIGINT'));
