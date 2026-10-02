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
  assert.match(verify, /URLSearchParams\(window\.location\.hash/);
  assert.match(verify, /history\.replaceState/);
  assert.match(verify, /E-mail confirmado/);
  assert.match(verify, /Entrar no Kordena/);
  assert.match(verify, /NEXT_PUBLIC_KORDENA_SIGNUP_ENABLED === "true"/);
});


test("KF-08 mantém signup e verificação como superfícies públicas sem shell autenticado", () => {
  const guard = fs.readFileSync("src/features/auth/components/AuthSessionGuard.tsx", "utf8");
  const shell = fs.readFileSync("src/features/shell/components/UnifiedAppShell.tsx", "utf8");

  assert.match(guard, /PUBLIC_PATHS = \["\/login", "\/signup", "\/cardapio", "\/legal"\]/);
  assert.match(shell, /pathname === "\/signup"/);
  assert.match(shell, /pathname\.startsWith\("\/signup\/"\)/);
  assert.match(shell, /pathname === "\/legal"/);
  assert.match(shell, /pathname\.startsWith\("\/legal\/"\)/);
});

test("Legal V1 vincula cadastro a versões e hashes oficiais sem misturar marketing", () => {
  const legalApi = fs.readFileSync("src/features/legal/services/legal-api.ts", "utf8");
  const legalPage = fs.readFileSync("src/features/legal/components/PublicLegalDocument.tsx", "utf8");

  assert.match(signup, /getActiveLegalDocuments/);
  assert.match(signup, /legal_documents: Object\.fromEntries/);
  assert.match(signup, /Termos de Uso v/);
  assert.match(signup, /Política de Privacidade v/);
  assert.match(signup, /DPA v/);
  assert.match(signup, /comunicações comerciais opcionais/);
  assert.match(signup, /independente do aceite necessário/);
  assert.match(api, /legal_documents:/);
  assert.match(legalApi, /\/v1\/public\/legal\/documents/);
  assert.match(legalPage, /SHA-256:/);
});
