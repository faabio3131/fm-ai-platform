import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const login = fs.readFileSync("src/app/login/page.tsx", "utf8");
const signup = fs.readFileSync("src/app/signup/page.tsx", "utf8");
const api = fs.readFileSync("src/features/auth/services/signup-api.ts", "utf8");
const verify = fs.readFileSync("src/app/signup/verify/page.tsx", "utf8");

test("KCA-06 mantém o cadastro público desabilitado por padrão", () => {
  assert.match(login, /NEXT_PUBLIC_KORDENA_SIGNUP_ENABLED === "true"/);
  assert.match(login, /Começar teste grátis/);
  assert.match(signup, /Cadastro em preparação/);
  assert.match(signup, /NEXT_PUBLIC_KORDENA_SIGNUP_ENABLED === "true"/);
});

test("KCA-06 envia somente contrato público ao backend", () => {
  assert.match(api, /\/v1\/public\/signup/);
  assert.doesNotMatch(api, /tenant_id/);
  assert.doesNotMatch(api, /plan_code/);
  assert.doesNotMatch(api, /entitlement/);
});

test("KCA-06 trata loading erro e sucesso", () => {
  assert.match(signup, /submitting/);
  assert.match(signup, /role="alert"/);
  assert.match(signup, /Confira seu e-mail/);
});


test("KCA-17 fecha a jornada de verificação pública no frontend", () => {
  assert.match(api, /verifySignupEmail/);
  assert.match(api, /\/verify-email/);
  assert.match(api, /encodeURIComponent\(normalizedSignupId\)/);
  assert.match(verify, /URLSearchParams\\(window\\.location\\.hash/);
  assert.match(verify, /history\\.replaceState/);\n  assert.match(verify, /history\\.replaceState/);\n  assert.match(verify, /E-mail confirmado/);
  assert.match(verify, /Entrar no Kordena/);
  assert.match(verify, /NEXT_PUBLIC_KORDENA_SIGNUP_ENABLED === "true"/);
});
