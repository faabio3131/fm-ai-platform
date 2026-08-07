const { spawnSync } = require('node:child_process');
const { basename, join } = require('node:path');

function isPythonExecutable(executable) {
  return /^python(?:\d+(?:\.\d+)*)?(?:\.exe)?$/i.test(basename(executable || ''));
}

function resolvePython(env = process.env) {
  if (env.FM_AI_PYTHON) return env.FM_AI_PYTHON;
  if (env.PYTHON) return env.PYTHON;
  if (env.VIRTUAL_ENV && process.platform === 'win32') {
    return join(env.VIRTUAL_ENV, 'Scripts', 'python.exe');
  }
  if (isPythonExecutable(process.execPath)) return process.execPath;
  return 'python';
}

function executePython(args, { cwd, env = process.env, label = 'Python' } = {}) {
  const python = resolvePython(env);
  const result = spawnSync(python, args, {
    cwd,
    env,
    encoding: 'utf-8',
    shell: false,
  });
  if (result.error || result.status !== 0) {
    throw new Error(
      `${label} falhou com ${python} (status=${result.status}, signal=${result.signal})\n` +
        `stdout:\n${result.stdout || ''}\nstderr:\n${result.stderr || ''}`,
      { cause: result.error },
    );
  }
  return { python, stdout: result.stdout, stderr: result.stderr };
}

function logPythonRuntime({ cwd, dbPath, env = process.env }) {
  const script =
    "import json,platform,sys; print(json.dumps({'sys_executable':sys.executable,'version':platform.python_version()}))";
  const runtime = executePython(['-c', script], { cwd, env, label: 'Inspeção do Python E2E' });
  const details = JSON.parse(runtime.stdout.trim());
  console.log(
    `[fm-ai-e2e] python selecionado=${runtime.python}; sys.executable=${details.sys_executable}; ` +
      `versão=${details.version}; cwd=${cwd}; banco=${dbPath}`,
  );
  if (runtime.stderr) process.stderr.write(runtime.stderr);
  return runtime.python;
}

module.exports = { executePython, isPythonExecutable, logPythonRuntime, resolvePython };
