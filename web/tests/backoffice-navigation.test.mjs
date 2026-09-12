import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const source = fs.readFileSync(new URL("../src/features/shell/module-registry.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } });
const context = { exports: {} };
vm.runInNewContext(compiled.outputText, context);
const { SHELL_MODULES, availableShellModules, isShellModuleActive } = context.exports;

test("backoffice e filhos só aparecem com as permissões existentes", () => {
  for (const permissions of [[], ["configuracao.alterar", "financeiro.visualizar", "estoque.visualizar"]]) {
    assert.equal(availableShellModules(permissions).filter(m => m.group === "proprietario").length, 0);
  }
  const admin = availableShellModules(["admin.acessar"]);
  assert.ok(admin.some(m => m.href === "/admin"));
  assert.ok(admin.some(m => m.href === "/admin/catalogo"));
  assert.ok(!admin.some(m => m.href === "/admin/dashboard"));
  assert.ok(!admin.some(m => m.href === "/admin/estoque"));
  assert.ok(!admin.some(m => m.href === "/admin/crm"));
  const full = availableShellModules(SHELL_MODULES.flatMap(m => [...(m.allPermissions ?? []), ...(m.anyPermissions ?? [])]));
  for (const href of ["/admin", "/admin/dashboard", "/admin/catalogo", "/admin/estoque", "/admin/crm", "/admin/ai-finops", "/admin/system-health"]) {
    assert.equal(full.filter(m => m.href === href).length, 1);
  }
});

test("rota filha não marca a landing como página ativa", () => {
  const home = SHELL_MODULES.find(m => m.href === "/admin");
  const catalogo = SHELL_MODULES.find(m => m.href === "/admin/catalogo");
  assert.equal(isShellModuleActive("/admin", home), true);
  assert.equal(isShellModuleActive("/admin/catalogo", home), false);
  assert.equal(isShellModuleActive("/admin/catalogo", catalogo), true);
  assert.equal(isShellModuleActive("/admin/catalogo/123", catalogo), true);
});

test("empresa exige admin e configuração no registry único", () => {
  for (const permissions of [[], ["admin.acessar"], ["configuracao.alterar"]]) {
    assert.ok(!availableShellModules(permissions).some(m => m.href === "/admin/empresa"));
  }
  const modulos = availableShellModules(["admin.acessar", "configuracao.alterar"]);
  assert.equal(modulos.filter(m => m.href === "/admin/empresa").length, 1);
  assert.equal(modulos.find(m => m.href === "/admin/empresa").group, "proprietario");
});
