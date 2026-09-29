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


test("WP-026 homologation button accepts configured state with evidence", () => {
  const workspace = source(
    "../src/features/backoffice/integracoes/components/IntegracoesWorkspace.tsx",
  );

  assert.match(
    workspace,
    /!\["configurado", "pronto"\]\.includes\(config\.prontidao\.estado\)/,
  );
  assert.match(
    workspace,
    /!homologacaoEvidencia\.trim\(\)/,
  );
  assert.doesNotMatch(
    workspace,
    /!config\.prontidao\.pronto/,
  );
});


test("WP-026 completed homologation renders read-only ready state", () => {
  const workspace = source(
    "../src/features/backoffice/integracoes/components/IntegracoesWorkspace.tsx",
  );

  assert.match(workspace, /config\?\.homologada \? 'Homologado' : 'Homologar'/);
  assert.match(workspace, /Integração homologada e pronta/);
  assert.match(workspace, /value=\{config\.evidencia_homologacao_ref \|\| ''\}/);
  assert.match(workspace, /id="evidencia_ref_homologada"/);
  assert.match(workspace, />Fechar<\/Button>/);
});


test("WP-026 integrations explain expired administrative step-up", () => {
  const workspace = source(
    "../src/features/backoffice/integracoes/components/IntegracoesWorkspace.tsx",
  );
  const api = source("../src/lib/api.ts");

  assert.match(api, /public readonly code\?: string/);
  assert.match(api, /const payload = \(await response\.json\(\)\) as \{ erro\?: unknown \}/);
  assert.match(api, /code = payload\.erro\.trim\(\)/);
  assert.match(workspace, /error\.code === 'seguranca\.admin_step_up_exigido'/);
  assert.match(
    workspace,
    /Sessão administrativa expirada\. Confirme novamente sua identidade na área Proprietário e tente de novo\. Os campos preenchidos foram preservados\./,
  );
});


test("WP-026 integration action tabs are navigable and explain blockers", () => {
  const workspace = source(
    "../src/features/backoffice/integracoes/components/IntegracoesWorkspace.tsx",
  );

  assert.doesNotMatch(
    workspace,
    /disabled=\{!spec\.healthcheck_supported\}/,
  );
  assert.doesNotMatch(
    workspace,
    /disabled=\{!config \|\| !config\.habilitada/,
  );
  assert.match(
    workspace,
    /Salve a configuração antes de executar o teste real\./,
  );
  assert.match(
    workspace,
    /Salve a configuração antes de homologar esta integração\./,
  );
  assert.match(
    workspace,
    /Ir para Configuração/,
  );
});

test("WP-026 healthcheck evidence auto-fills homologation for every provider", () => {
  const workspace = source(
    "../src/features/backoffice/integracoes/components/IntegracoesWorkspace.tsx",
  );

  assert.match(
    workspace,
    /if \(resultado\.evidencia_ref\) \{[\s\S]*setHomologacaoEvidencia\(resultado\.evidencia_ref\)/,
  );
});

test("WP-026 healthcheck never mutates readiness locally", () => {
  const workspace = source(
    "../src/features/backoffice/integracoes/components/IntegracoesWorkspace.tsx",
  );

  assert.match(
    workspace,
    /const handleHealthcheck = useCallback\(async \(configId: string\) => \{[\s\S]*return executarHealthcheck\(configId\);[\s\S]*\}, \[\]\);/,
  );
  assert.doesNotMatch(
    workspace,
    /estado: result\.executado \? 'configurado'/,
  );
});

test("WP-026 missing configuration is labeled correctly in the dialog", () => {
  const workspace = source(
    "../src/features/backoffice/integracoes/components/IntegracoesWorkspace.tsx",
  );

  assert.match(
    workspace,
    /config \? PRONTIDAO_LABELS\[config\.prontidao\.estado\] : 'Não configurada'/,
  );
});
