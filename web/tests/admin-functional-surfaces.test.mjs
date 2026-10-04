import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

function read(relativePath) {
  return fs.readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

const apiSource = read("../src/lib/api.ts");
const guardSource = read("../src/features/auth/components/AdminStepUpGuard.tsx");
const usuariosSource = read("../src/features/backoffice/usuarios/components/UsuariosWorkspace.tsx");
const configuracaoSource = read("../src/features/backoffice/empresa/components/ConfiguracaoWorkspace.tsx");
const empresaApiSource = read("../src/features/backoffice/empresa/services/empresa-api.ts");
const fiscalApiSource = read("../src/features/backoffice/fiscal/services/fiscal-api.ts");
const auditoriaApiSource = read("../src/features/backoffice/auditoria/services/auditoria-api.ts");

test("admin step-up expirado reabre a barreira em vez de deixar superfícies em 403", () => {
  assert.match(apiSource, /ADMIN_STEP_UP_REQUIRED_EVENT/);
  assert.match(apiSource, /seguranca\.admin_step_up_exigido/);
  assert.match(apiSource, /dispatchEvent/);
  assert.match(guardSource, /addEventListener\(ADMIN_STEP_UP_REQUIRED_EVENT/);
  assert.match(guardSource, /expiresAt - Date\.now\(\)/);
  assert.match(guardSource, /elevado: false/);
});

test("Usuários e Permissões usa os valores canônicos do enum Papel do backend", () => {
  for (const papel of [
    "administrador",
    "gerente",
    "caixa",
    "garcom",
    "cozinha",
    "expedicao",
    "entregador",
    "atendimento",
    "financeiro",
    "gerente_ia",
  ]) {
    assert.match(usuariosSource, new RegExp(`"${papel}"`));
  }
  assert.doesNotMatch(usuariosSource, /"CLIENTE"/);
  assert.doesNotMatch(usuariosSource, /"ADMINISTRADOR"/);
  assert.match(usuariosSource, /apiRequest<Usuario\[]>\("\/v1\/admin\/usuarios"/);
  assert.match(usuariosSource, /saving: false/);
});

test("Parâmetros Financeiros não fica preso em loading quando a carga administrativa falha ou não há unidades", () => {
  assert.match(configuracaoSource, /obterCadastroEmpresa/);
  assert.match(configuracaoSource, /loading: false/);
  assert.match(configuracaoSource, /unidades\.length === 0 \? false/);
  assert.doesNotMatch(configuracaoSource, /fetch\(.*\/v1\/admin\/empresa/);
  assert.match(empresaApiSource, /apiRequest<T>/);
  assert.match(empresaApiSource, /obterCadastroEmpresa/);
});

test("Fiscal e Auditoria passam pelo cliente comum que sinaliza expiração de step-up", () => {
  assert.match(fiscalApiSource, /apiRequest<FiscalWorkspaceResponse>/);
  assert.match(auditoriaApiSource, /apiRequest<AuditoriaPage>/);
  assert.match(auditoriaApiSource, /seguranca\.admin_step_up_exigido/);
});
