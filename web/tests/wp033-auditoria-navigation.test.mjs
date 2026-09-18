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

test("auditoria exige admin e permissão dedicada", () => {
  for (const permissions of [
    [],
    ["admin.acessar"],
    ["auditoria.visualizar"],
  ]) {
    assert.equal(
      availableShellModules(permissions).some(
        (module) => module.href === "/admin/auditoria",
      ),
      false,
    );
  }
  assert.equal(
    availableShellModules([
      "admin.acessar",
      "auditoria.visualizar",
    ]).filter((module) => module.href === "/admin/auditoria").length,
    1,
  );
});
