# Ciclo conservativo WP-020 + WP-022 — 09/09/2026

Autoridade: ordem explícita do proprietário para este ciclo e AGENTS.md local.
Skills consultadas: governança Git, System Design Guardian e Validation Release Gate.
Base: `d261a94e854334d9fdf9c073e8af73f557f31114`.
Checkpoint documental WP-030/031/032 publicado: `4822eba7c6c8a2020e3d6cba7d5578ab4b97843b`.

## WP-020 — auditoria e decisão anterior ao código

- Original: `pages/6_Administracao_Proprietario.py` e `infra/streamlit_app/admin_proprietario.py`; Centro Administrativo com abas executivo, empresa/unidades, financeiro, impressão, usuários, integrações e auditoria. O acesso chama `AplicacaoAdministracaoProprietarioV1.registrar_acesso()`.
- Web: `/admin/layout.tsx` já aplica `AdminStepUpGuard`, mas falta `/admin/page.tsx`. Dashboard, Catálogo, Estoque, CRM, AI FinOps e Saúde do sistema já existem e pertencem ao grupo Proprietário do registry.
- Permissões preservadas no registry: todos exigem `admin.acessar`; Dashboard também `financeiro.visualizar`, Estoque `estoque.visualizar`, CRM `cliente.visualizar`. As autoridades filhas continuam validando suas operações. Gerente padrão não tem `admin.acessar`.
- Solução mínima: landing com links derivados do registry, entrada no Shell e HTTP de auditoria delegando a `registrar_acesso()`. Sem novos painéis ou links para módulos ainda não migrados.
- Contexto: sessão assinada e runtime de step-up existentes. Nenhum parâmetro de cliente governa tenant/unidade. Troca operacional e logout permanecem no Shell.
- Persistência/transação: somente auditoria/inicialização já pertencentes a `registrar_acesso()` e seu UoW; sem schema, migration, provider, segredo ou regra nova. Application/Core/Infra sem alterações. Fresh/upgrade mantidos.
- Rollback: reverter somente os novos adapters HTTP/Web e registro de navegação; sem rollback de dados ou migration.
- Provas: contratos HTTP com sessão real, RBAC allow/deny, step-up/revogação, spoofing, auditoria original, navegação executada em Node, regressão dos filhos e checks direcionados Python/frontend.
- STOP: publicar implementação, conferir SHA remoto, publicar reconciliação documental e conferir novamente antes de WP-022. Sem Smoke Mestre/certificação integrada/merge/deploy.

## WP-013 — auditoria exclusivamente documental

Original auditado: `app.py::render_cadastro_ficha_tecnica` e aba de Engenharia de Cardápio. Cadastro de prato/categoria, composição por insumos, CMV, margem/preço sugerido, preço final e importação Gemini por texto/imagem/PDF estão representados em `/admin/catalogo`, `CatalogoWorkspace`, `FichaTecnicaWorkspace`, `http_api/catalogo.py` e WP-014. Listagem/categorias, criação básica e disponibilidade já pertencem ao catálogo existente. Não foi identificada capacidade original adicional que exija outra superfície WP-013. Preservar como implementação presente aguardando certificação; nenhuma alteração de código WP-013 neste ciclo. Diferença preexistente na interação de preço registrada nas pendências; a cobertura de capacidades não equivale à certificação de comportamento.

## WP-020 — prova técnica do candidato

- 17 testes: `test_admin_backoffice_http_contract.py`, `test_auth_admin_stepup_http_contract.py`, `test_web_shell_wp003_wp004.py`.
- 34 testes de regressão: contratos HTTP Dashboard, AI FinOps, Catálogo e CRM; fitness `test_f13e_admin_dashboard_cutover.py` e `test_f13f_ai_finops_web_cutover.py`.
- 2 testes Node: `node --test tests/backoffice-navigation.test.mjs`; RBAC real do registry e seleção de rota ativa, incluindo filhos.
- Ruff direcionado: aprovado em `http_api/admin_backoffice.py`, `http_api/frontend_app.py`, teste HTTP novo. Mypy `--follow-imports=silent`: aprovado nos dois arquivos HTTP afetados.
- Frontend: `npm.cmd run lint`, `tsc.cmd --noEmit` e `npm.cmd run build` aprovados; rota `/admin` presente no build. A primeira tentativa de lint detectou imports CommonJS no novo teste; corrigidos para ES Modules e revalidados sem relaxar regras.
- `git diff --check` aprovado; Core, Infra e Application sem alterações. Dependências locais instaladas sem alterar manifests/lockfiles; artefatos gerados pelo build não integram o checkpoint.
- Situação: implementação candidata tecnicamente validada neste ambiente local; certificação integrada e Smoke Mestre adiados. Não é homologação final da V1.
