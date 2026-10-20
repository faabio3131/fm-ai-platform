# WP-020 — Área Proprietário / Backoffice — Certificação

## Estado

**CERTIFICAÇÃO AUTOMATIZADA EM FECHAMENTO.**

A implementação Web do WP-020 já estava presente na branch oficial antes deste documento. Esta certificação não reconstrói o Backoffice: ela revalida a implementação canônica existente e adiciona um gate dedicado ao bloco.

A certificação formal deste documento só deve ser considerada concluída quando o SHA que contém este arquivo estiver com os gates obrigatórios do CI verdes na PR #118.

## Escopo canônico

O WP-020 representa a entrada Web da Área Proprietário / Backoffice e preserva as autoridades existentes:

- `AplicacaoAdministracaoProprietarioV1`;
- sessão assinada e identidade operacional canônicas;
- `admin.acessar` como requisito de autorização;
- step-up administrativo já existente;
- registry canônico de módulos do Shell;
- auditoria administrativa original;
- tenant e unidade derivados exclusivamente da sessão autenticada.

Não foi criado segundo Backoffice, segunda matriz RBAC, novo domínio administrativo, nova política de sessão ou mecanismo paralelo de auditoria.

## Superfície validada

### HTTP

`POST /v1/admin/acesso` em `http_api/admin_backoffice.py`:

- exige sessão autenticada;
- exige `admin.acessar`;
- exige step-up administrativo ativo;
- constrói `ContextoExecucao` a partir da identidade da sessão;
- ignora parâmetros externos de tenant/unidade como autoridade;
- delega o registro de acesso à `AplicacaoAdministracaoProprietarioV1.registrar_acesso()`;
- mantém tratamento fail-closed de autenticação/autorização.

### Web

`/admin` usa `BackofficeHome` como landing do Centro Administrativo.

A navegação é derivada de `availableShellModules(auth.permissions)` e limitada ao grupo `proprietario`, preservando as permissões declaradas no registry. A entrada registra o acesso administrativo pelo endpoint canônico e não substitui o guard de step-up.

## Provas automatizadas existentes

`tests/api/test_admin_backoffice_http_contract.py` cobre:

1. sessão obrigatória;
2. step-up obrigatório;
3. acesso após elevação;
4. revogação do step-up na troca de unidade;
5. revogação efetiva após logout;
6. gerente/cozinha sem `admin.acessar` não recebem acesso automático;
7. tentativa de step-up por papel sem autorização permanece bloqueada;
8. spoofing por query/header não expande tenant/unidade;
9. auditoria usa tenant/unidade da sessão e preserva correlation id.

`tests/api/test_auth_admin_stepup_http_contract.py` permanece como regressão da autoridade canônica de step-up.

`web/tests/backoffice-navigation.test.mjs` permanece como prova de navegação/RBAC do Shell.

## Gate dedicado WP-020

Foi adicionado `.github/workflows/web-parity-wp020-certification.yml` para executar no candidato:

- compilação Python da superfície WP-020;
- Ruff direcionado;
- mypy direcionado;
- matriz focal de contratos HTTP;
- regressão Python completa;
- ESLint da landing e componente Backoffice;
- TypeScript;
- teste Node de navegação do Backoffice;
- build Next.js de produção;
- `git diff --check`.

Nenhum teste foi removido, relaxado, convertido em `skip`/`xfail` ou substituído por mock para fabricar verde.

## Governança preservada

- PR oficial: `#118`;
- branch oficial: `feat/web-parity-v1-total-original-migration`;
- PR deve permanecer OPEN/DRAFT;
- nenhum merge;
- nenhum deploy;
- nenhuma alteração da `main`;
- nenhum force push/rebase destrutivo;
- nenhuma promoção para WP-021 antes do SHA final deste bloco estar 100% verde.

## Dívida técnica preservada

A divergência AF04/fingerprint de schema observada no Windows continua dívida cross-platform separada. Não alterar baseline às cegas, não remover o gate e não mascarar a divergência.

## Pendências históricas não absorvidas pelo WP-020

Continuam abertas até evidência específica:

- WP-005 — caixa/PDV;
- WP-005/WP-029 — settlement end-to-end;
- WP-007 — roteamento KDS;
- WP-009 — mensagens;
- WP-007/WP-009 — cadeia Pedido → Produção/KDS.

## Próxima etapa permitida

Somente após o SHA final deste documento e do gate WP-020 ficar 100% verde, com PR #118 ainda OPEN/DRAFT e sem merge/deploy, avançar para:

**WP-021 — revalidação do step-up administrativo existente.**

WP-021 é checkpoint/revalidação; não deve ser reimplementado como um segundo mecanismo.
