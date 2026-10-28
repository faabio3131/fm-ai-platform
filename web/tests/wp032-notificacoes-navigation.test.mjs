import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const source = fs.readFileSync(
  new URL("../src/features/shell/module-registry.ts", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
});
const context = { exports: {} };
vm.runInNewContext(compiled.outputText, context);
const { availableShellModules } = context.exports;

test("notificações internas exigem admin e permissão dedicada", () => {
  for (const permissions of [
    [],
    ["admin.acessar"],
    ["notificacao_interna.gerenciar"],
  ]) {
    assert.equal(
      availableShellModules(permissions).some(
        (module) => module.href === "/admin/notificacoes",
      ),
      false,
    );
  }
  assert.equal(
    availableShellModules([
      "admin.acessar",
      "notificacao_interna.gerenciar",
    ]).filter((module) => module.href === "/admin/notificacoes").length,
    1,
  );
});
