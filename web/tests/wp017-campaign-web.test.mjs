import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const registrySource = readFileSync(
  new URL("../src/features/shell/module-registry.ts", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(registrySource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
});
const context = { exports: {} };
vm.runInNewContext(compiled.outputText, context);
const { availableShellModules } = context.exports;

const page = readFileSync(
  new URL("../src/app/admin/campanhas/page.tsx", import.meta.url),
  "utf8",
);
const workspace = readFileSync(
  new URL("../src/features/backoffice/campanhas/components/CampanhasWorkspace.tsx", import.meta.url),
  "utf8",
);
const api = readFileSync(
  new URL("../src/features/backoffice/campanhas/services/campanhas-api.ts", import.meta.url),
  "utf8",
);
const crm = readFileSync(
  new URL("../src/features/backoffice/crm/components/CrmWorkspace.tsx", import.meta.url),
  "utf8",
);
const gerente = readFileSync(
  new URL("../src/features/gerente-ia/components/GerenteIAWorkspace.tsx", import.meta.url),
  "utf8",
);

test("WP-017 aparece como módulo proprietário governado", () => {
  assert.equal(
    availableShellModules([]).some((module) => module.href === "/admin/campanhas"),
    false,
  );
  const modules = availableShellModules([
    "admin.acessar",
    "cliente.visualizar",
    "campanha.criar",
  ]);
  assert.equal(
    modules.filter((module) => module.href === "/admin/campanhas").length,
    1,
  );
});

test("Central Web cobre o lifecycle exigido pela auditoria", () => {
  assert.match(page, /CampanhasWorkspace/);
  for (const fragment of [
    "/v1/campanhas",
    "/audiencia",
    "/submeter",
    "/aprovar",
    "/publicar",
    "/despachar",
    "/historico",
  ]) {
    assert.ok(api.includes(fragment), fragment);
  }
  for (const label of [
    "Criar rascunho",
    "Salvar audiência",
    "Submeter",
    "Aprovar",
    "Publicar",
    "Despachar",
    "Histórico auditável",
  ]) {
    assert.ok(workspace.includes(label), label);
  }
});

test("CRM cria rascunho governado e Gerente IA abre o draft sem publicar sozinho", () => {
  assert.match(crm, /criarCampanhaResgate/);
  assert.match(crm, /definirAudiencia/);
  assert.match(crm, /Envio rápido/);
  assert.match(gerente, /campaignDraftOf/);
  assert.match(gerente, /Abrir rascunho em Campanhas/);
  assert.doesNotMatch(gerente, /publicarCampanha/);
  assert.doesNotMatch(gerente, /despacharCampanha/);
});
