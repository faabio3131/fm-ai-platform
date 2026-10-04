import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const login = fs.readFileSync("src/app/login/page.tsx", "utf8");
const forgot = fs.readFileSync("src/app/forgot-password/page.tsx", "utf8");
const reset = fs.readFileSync("src/app/reset-password/page.tsx", "utf8");
const api = fs.readFileSync("src/features/auth/services/auth-api.ts", "utf8");
const guard = fs.readFileSync("src/features/auth/components/AuthSessionGuard.tsx", "utf8");
const shell = fs.readFileSync("src/features/shell/components/UnifiedAppShell.tsx", "utf8");

test("login expõe recuperação de senha sem alterar o login canônico", () => {
  assert.match(login, /href="\/forgot-password"/);
  assert.match(login, /Esqueci minha senha/);
  assert.match(login, /await login\(email\.trim\(\), senha\)/);
});

test("recuperação usa resposta neutra e jornada pública dedicada", () => {
  assert.match(forgot, /Se existir uma conta elegível/);
  assert.match(forgot, /requestPasswordRecovery/);
  assert.match(api, /\/v1\/auth\/forgot-password/);
  assert.match(guard, /"\/forgot-password"/);
  assert.match(shell, /pathname === "\/forgot-password"/);
});

test("token de reset fica no fragment e é removido da URL antes do uso", () => {
  assert.match(reset, /window\.location\.hash/);
  assert.match(reset, /history\.replaceState/);
  assert.match(reset, /resetPassword\(token, password\)/);
  assert.match(api, /\/v1\/auth\/reset-password/);
  assert.match(guard, /"\/reset-password"/);
  assert.match(shell, /pathname === "\/reset-password"/);
});

test("nova senha exige confirmação e mínimo canônico de 10 caracteres", () => {
  assert.match(reset, /password\.length < 10/);
  assert.match(reset, /password !== confirm/);
  assert.match(reset, /minLength=\{10\}/);
});
