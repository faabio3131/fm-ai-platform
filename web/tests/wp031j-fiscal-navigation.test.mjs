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

test("fiscal exige admin e permissao fiscal dedicada", () => {
  for (const permissions of [
    [],
    ["admin.acessar"],
    ["fiscal.visualizar"],
    ["fiscal.cancelar", "fiscal.inutilizar"],
  ]) {
    assert.equal(
      availableShellModules(permissions).some(
        (module) => module.href === "/admin/fiscal",
      ),
      false,
    );
  }

  const modules = availableShellModules([
    "admin.acessar",
    "fiscal.visualizar",
  ]);
  assert.equal(
    modules.filter((module) => module.href === "/admin/fiscal").length,
    1,
  );
  assert.equal(
    modules.find((module) => module.href === "/admin/fiscal").group,
    "proprietario",
  );
});
