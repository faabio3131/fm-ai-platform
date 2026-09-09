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

## WP-022 — auditoria e decisão anterior ao código

- Entrada liberada após checkpoint WP-020 documental `c91d0a7ef371c056ba1404f307e12a8f990f6d5d` confirmado local/remoto e árvore limpa.
- Original: `_render_empresa_unidades` em `infra/streamlit_app/admin_proprietario.py`. Empresa: nome, moeda, timezone, ativa e versão. Unidade: ID estável, código, nome fantasia, tipo matriz/filial/unidade, documento fiscal, telefone, email, descrição de endereço/horários, ativa e versão. Não há parent/hierarquia adicional.
- Operações existentes: `obter_empresa`, `listar_unidades`, `atualizar_empresa`, `atualizar_unidade` e **`criar_unidade`**, com formulário original de criação; portanto criação faz parte da migração, sem nova capacidade. O formulário de criação original contém apenas ID/código/nome/tipo/endereço/horários; contatos e estado são editados depois.
- Autoridade: `AplicacaoAdministracaoProprietarioV1`, `core/administracao` e repositório administrativo existente. `registrar_acesso` inicializa o cadastro como no original. A aplicação exige admin + configuração; atualização da empresa e criação são exclusivas do administrador do tenant. Gerente com autorização administrativa explícita só administra suas unidades; gerente padrão não entra. Administrador pode administrar as unidades do seu tenant por regra já existente, sem alterar a unidade ativa.
- Solução: DTOs e adaptação HTTP dos campos do formulário, serialização das leituras e rota única `/admin/empresa`; item no Shell Proprietário e landing WP-020, com `admin.acessar` + `configuracao.alterar`. Sem novo domínio, facade, regra ou Application.
- Contexto e proteção: reutilizar sessão assinada/step-up WP-020. DTOs rejeitam campos extras de tenant/escopo; IDs cadastrais de unidades são recursos sujeitos à autoridade Application, jamais substituem o contexto. Web não chama troca de unidade como parte da administração.
- Persistência/UoW/auditoria/membership e concorrência por versão permanecem exclusivamente nas autoridades originais. ID repetido continua recusado; versão obsoleta continua falhando. Sem idempotência ou política de retry nova. Sem schema/migrations; fresh/upgrade intactos. Rollback dos adapters, sem reversão destrutiva dos dados.
- Provas: HTTP com Application/repositório reais e dois tenants; administrador, gerente padrão e gerente explicitamente autorizado com unidade limitada; spoofing em headers/query/body, step-up e troca operacional, criação/edição/replay de versão/auditoria; fitness para ausência de regra paralela; regressão WP-020 e administração original; Ruff/mypy, lint/typecheck/build e diff check.
- STOP esperado: implementação + documentos publicados e SHA confirmado; não iniciar WP-023.

## WP-022 — prova técnica do candidato

- 28 testes aprovados: contratos novos de Empresa/Unidades, fitness do boundary, contratos WP-020, integração administrativa original e modelos administrativos originais. Banco SQLite descartável com migrations existentes e autoridades reais; dois tenants, unidade homônima entre tenants e gerente explicitamente limitado a uma unidade.
- 12 testes adicionais aprovados: contratos de autenticação e step-up existentes, incluindo revogação na troca operacional. Total direcionado: **40 testes Python**.
- 3 testes Node de navegação aprovados, incluindo `admin.acessar` + `configuracao.alterar` para Empresa/Unidades.
- Ruff e mypy `--follow-imports=silent` direcionados aprovados. Frontend lint, `tsc.cmd --noEmit --incremental false`, build de produção com `/admin/empresa` e diff check aprovados.
- A primeira execução identificou erro introduzido no adapter ao tratar `ErroSeguranca` como `ValueError` genérico. A precedência foi corrigida no HTTP e o conjunto foi repetido com sucesso, preservando respostas 401/403. Nenhuma correção funcional preexistente foi incorporada.
- Core/Infra/Application sem alterações desde o SHA inicial. Não houve extração Application, migration, provider, regra, matriz RBAC, política de sessão ou idempotência nova. Artefatos gerados pelo build foram retirados do diff após conferência de proveniência.
- RESULTADO DO GATE TÉCNICO: APROVADO. Situação funcional: implementação presente, aguarda certificação. Estado técnico/PR: candidato da PR #118 Draft, sujeito ao checkpoint remoto obrigatório. Estado operacional: não homologado para release; Smoke Mestre, certificação integrada, merge e deploy não executados.
