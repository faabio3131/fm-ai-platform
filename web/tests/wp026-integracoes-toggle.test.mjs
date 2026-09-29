import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

function source(relativePath) {
  return fs.readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

test("WP-026 integration enabled toggle reflects native checkbox state", () => {
  const workspace = source(
    "../src/features/backoffice/integracoes/components/IntegracoesWorkspace.tsx",
  );

  assert.match(workspace, /checked=\{formData\.habilitada\}/);
  assert.match(
    workspace,
    /onChange=\{\(e: React\.ChangeEvent<HTMLInputElement>\) => setFormData\(\(prev\) => \(\{ \.\.\.prev, habilitada: e\.target\.checked \}\)\)\}/,
  );
  assert.match(
    workspace,
    /formData\.habilitada \? 'bg-primary' : 'bg-input'/,
  );
  assert.match(
    workspace,
    /formData\.habilitada \? 'translate-x-5' : 'translate-x-0'/,
  );
  assert.doesNotMatch(workspace, /peer-data-\[state=checked\]/);
  assert.doesNotMatch(workspace, /peer-data-\[state=unchecked\]/);
});


test("WP-026 first save refreshes integration card by catalog identity", () => {
  const workspace = source(
    "../src/features/backoffice/integracoes/components/IntegracoesWorkspace.tsx",
  );

  assert.match(
    workspace,
    /i\.catalogo\.servico === config\.servico[\s\S]*i\.catalogo\.provedor === config\.provedor/,
  );
  assert.doesNotMatch(
    workspace,
    /i\.configuracao\?\.configuracao_id === config\.configuracao_id/,
  );
});


test("WP-026 healthcheck renders backend result and evidence", () => {
  const workspace = source(
    "../src/features/backoffice/integracoes/components/IntegracoesWorkspace.tsx",
  );

  assert.match(
    workspace,
    /const resultado = await onHealthcheck/,
  );
  assert.match(
    workspace,
    /Healthcheck executado com sucesso/,
  );
  assert.match(
    workspace,
    /evidenciaRef: resultado\.evidencia_ref \|\| undefined/,
  );
  assert.match(
    workspace,
    /mensagem: resultado\.erro \|\| 'Healthcheck não foi executado'/,
  );
});


test("WP-026 integration editor uses a single dialog context", () => {
  const workspace = source(
    "../src/features/backoffice/integracoes/components/IntegracoesWorkspace.tsx",
  );

  assert.doesNotMatch(workspace, /<Dialog open=\{isOpen\}/);
  assert.doesNotMatch(workspace, /const \[isOpen, setIsOpen\]/);
  assert.match(workspace, /<DialogTrigger asChild>/);
  assert.match(workspace, /<DialogContent className="max-w-3xl/);
  assert.match(workspace, /<DialogClose asChild>/);
});

test("WP-026 integrations list is compact and bounded", () => {
  const workspace = source(
    "../src/features/backoffice/integracoes/components/IntegracoesWorkspace.tsx",
  );

  assert.match(workspace, /max-w-5xl space-y-5/);
  assert.match(workspace, /grid gap-3/);
  assert.match(workspace, /size="sm"/);
  assert.match(workspace, /sm:min-w-28/);
});
