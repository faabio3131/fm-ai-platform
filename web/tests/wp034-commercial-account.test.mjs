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
  new URL("../src/app/admin/assinatura/page.tsx", import.meta.url),
  "utf8",
);
const workspace = readFileSync(
  new URL("../src/features/commercial/components/CommercialAccountWorkspace.tsx", import.meta.url),
  "utf8",
);
const api = readFileSync(
  new URL("../src/features/commercial/services/commercial-access-api.ts", import.meta.url),
  "utf8",
);

test("WP-034 expõe Plano e Assinatura somente na área Proprietário", () => {
  assert.equal(
    availableShellModules([]).some((module) => module.href === "/admin/assinatura"),
    false,
  );
  const modules = availableShellModules(["admin.acessar"]);
  assert.equal(
    modules.filter((module) => module.href === "/admin/assinatura").length,
    1,
  );
  assert.equal(
    modules.find((module) => module.href === "/admin/assinatura").group,
    "proprietario",
  );
});

test("WP-034 reutiliza a autoridade comercial KCA sem hardcode de plano/preço", () => {
  assert.match(page, /CommercialAccountWorkspace/);
  assert.match(api, /\/v1\/commercial\/access/);
  assert.match(api, /\/v1\/commercial\/plans/);
  assert.match(api, /\/v1\/commercial\/subscription/);
  assert.match(api, /\/v1\/commercial\/checkout/);
  assert.match(workspace, /getCommercialSubscription/);
  assert.match(workspace, /startCommercialCheckout/);
  assert.match(workspace, /access\.operational_allowed/);
  assert.doesNotMatch(workspace, /KORDENA_PLAN_[A-D]/);
  assert.match(workspace, /nenhum valor comercial é hardcoded/i);
});
