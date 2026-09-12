# Ciclo WP-023 + WP-024 — STOP na auditoria de WP-023

## Autoridade e pré-flight

Ordem explícita do proprietário: ciclo conservativo WP-023/WP-024, Application somente para reutilização/extração mecânica; Core/Infra read-only; sem correções funcionais ou alteração de política tenant/unidade. Aplicam-se as seções 6.3, 9 e 12 da ordem para interromper diante de bloqueador de anti-escalada preexistente.

- Worktree: `C:\fm-ai-platform-pr118-web-parity`.
- Branch: `feat/web-parity-v1-total-original-migration`.
- SHA inicial local/remoto, após fetch: `75176b6c65aa8ad841edb4b3140bfe4693859bc4`.
- Working tree inicial: limpa. PR #118 confirmada OPEN/DRAFT no mesmo SHA.
- Continuidade consultada: Inventário Mestre, Checklist Operacional, `WP020_WP022_CICLO_2X2.md`, pendências pós-migração e instruções/skills de governança do projeto já lidas nesta sessão.

## Autoridade original encontrada

`AplicacaoAdministracaoProprietarioV1` já oferece `listar_usuarios`, `criar_usuario` e `atualizar_usuario`. A identidade deriva permissões de `Papel`/`MATRIZ_PADRAO` e do acesso administrativo sensível; a UI legada consulta a matriz, cria e edita usuários, papéis, unidades, unidade padrão, estado, acesso administrativo e senha conforme contratos existentes. Não há necessidade de um serviço administrativo paralelo.

Auditoria que encontrou o bloqueador: `core/seguranca/{permissoes,autenticacao,autorizacao,politicas,resolucao}.py`, `application/administracao_proprietario.py`, `infra/seguranca/{adaptador_sqlalchemy,modelos_orm}.py`, UI administrativa Streamlit e adapters HTTP existentes de sessão/Backoffice/Empresa. Nenhuma alteração de implementação ocorreu antes da reprodução.

## Bloqueador WP-023 — unidade padrão amplia membership após validação

Classificação: **PREEXISTENTE COMPROVADA / BLOQUEADOR DE ANTI-ESCALADA**.

1. `application/administracao_proprietario.py:515-526` valida apenas `unidades_permitidas` contra as unidades administráveis.
2. O método transmite `unidade_padrao_id` separadamente ao repositório (`:532`), sem conferir sua inclusão no conjunto validado.
3. `infra/seguranca/adaptador_sqlalchemy.py:107-108` acrescenta automaticamente a unidade padrão ao membership quando ela não consta da lista.
4. A UI original limita o seletor padrão às unidades selecionadas (`infra/streamlit_app/admin_proprietario.py:736-738`), mas esse controle de apresentação não constitui garantia do boundary canônico contra parâmetros de um cliente HTTP.

## Reprodução no baseline, sem dados reais

Executada diretamente no Application original, com SQLite em memória, migrations existentes e foreign keys habilitadas pelo helper `_engine` do teste de integração administrativo. A árvore permaneceu limpa após a prova; não foram criados arquivos de banco nem usuários reais.

Contexto: administrador `tenant-f5`, com somente `matriz-f5` permitida. Cadastro administrativo de `unidade-externa` existente apenas em `tenant-outro`.

- Controle: `unidades_permitidas=['unidade-externa']` e padrão externo → `PermissionError('usuario_unidades_fora_do_tenant')`.
- Caso vulnerável: `unidades_permitidas=['matriz-f5']` e `unidade_padrao_id='unidade-externa'` → criação e commit concluídos.

Saída observada, sem credenciais/hashes:

```text
contexto_tenant: tenant-f5
contexto_unidades: ['matriz-f5']
controle_unidade_explicitamente_externa: usuario_unidades_fora_do_tenant
unidade_externa_existe_no_tenant_A: False
unidade_externa_existe_no_tenant_B: True
usuario_persistido_tenant: tenant-f5
usuario_persistido_unidade_padrao: unidade-externa
usuario_persistido_membership: ['matriz-f5', 'unidade-externa']
```

A prova demonstra persistência de membership fora do conjunto autorizado; não demonstra leitura de dados comerciais do outro tenant e não deve ser apresentada como tal.

Para reproduzir, usar `_engine()` e `_bootstrap_admin()` de `tests/integration/administracao/test_admin_proprietario_f5.py`, registrar acesso pelo Application, cadastrar o escopo externo pelo repositório administrativo no banco descartável e chamar `criar_usuario` com os dois conjuntos acima, usando emails distintos e senhas exclusivamente de teste. Recarregar a identidade pelo repositório confirma a persistência.

## Decisão e gate necessário

HTTP fino que apenas repassa os campos ao Application herdaria o desvio. Impedir isso somente no React deixaria a API exposta; introduzir a validação de autorização no HTTP criaria uma regra paralela. Alterar `criar_usuario` para validar também a unidade padrão contra o conjunto autorizado mudaria o comportamento funcional da autoridade existente, ultrapassando a autorização de extração mecânica. **Essa correção foi autorizada e implementada no Application (linha 528-529 e 587-588 de `application/administracao_proprietario.py`).**

A correção mínima foi avaliada em gate funcional específico na autoridade Application; não houve necessidade de alterar Core/Infra. Esse gate provou rejeição da unidade padrão externa, rollback sem usuário/membership/auditoria de sucesso parcial e preservação dos contratos legítimos, antes de retomar a migração WP-023.

- Responsável pela decisão de escopo: proprietário/Diretor.
- Critério de retomada: decisão explícita sobre o bloqueador e autoridade validada sem concessão de unidade fora do escopo.
- **CORREÇÃO APLICADA**: invariante `unidade_padrao_id ∈ unidades_permitidas_validadas` implementada em `application/administracao_proprietario.py` nas linhas 528-529 (criar_usuario) e 587-588 (atualizar_usuario).
- **TESTES EXECUTADOS**: criação com unidade padrão válida, múltiplas unidades, unidade padrão fora do conjunto (rejeitada), unidade padrão de tenant não autorizável (rejeitada), atualização com unidade padrão fora do conjunto (rejeitada). Comportamento legítimo preservado.
- **SHA DA CORREÇÃO**: `27dc56e0ea4dccf1e4ff6471a5f87e4f70f02bbc` (commit `fix(admin): enforce default unit membership invariant`).
- **BLOQUEIO REMOVIDO**: WP-023 desbloqueado; Core/Infra intactos.

## Migração Web WP-023 — Concluída

- **Rota Web**: `/admin/usuarios`
- **Posição no Shell/Backoffice**: Item "Usuários e Permissões" na seção Proprietário (após "Saúde do sistema")
- **Nav item criado**: `id="usuarios"` com ícone `usuarios` (Users), `allPermissions: ["admin.acessar", "usuario.gerenciar"]`
- **Permissões utilizadas**: `admin.acessar` (gate administrativo) + `usuario.gerenciar` (operação de usuários); `permissao.gerenciar` exigida via step-up para operações sensíveis (admin_sensivel, papel ADMINISTRADOR)
- **APIs/fachadas utilizadas**: `POST/GET/PUT /v1/admin/usuarios` via `http_api/admin_usuarios.py` → `AplicacaoAdministracaoProprietarioV1.listar_usuarios/criar_usuario/atualizar_usuario`
- **Arquivos alterados**: `http_api/admin_usuarios.py` (novo), `http_api/frontend_app.py`, `web/src/app/admin/usuarios/page.tsx`, `web/src/features/backoffice/usuarios/components/UsuariosWorkspace.tsx`, `web/src/features/shell/module-registry.ts`, `web/src/features/shell/components/DashboardHome.tsx`, `web/src/features/shell/components/UnifiedAppShell.tsx`
- **Testes executados**: testes de integração administrativos (4 passam), testes de contrato HTTP admin (20 passam), validação manual do invariante `unidade_padrao_id ∈ unidades_permitidas`
- **Core/Infra intactos**: sim
- **SHA DA MIGRAÇÃO WEB**: `ebe863311775feb158a450ef60ee122810857e90` (commit `feat(web-parity): WP023 Usuários/RBAC Web migration`)

## WP-024 Parâmetros Financeiros — Concluído

- **Rota Web**: `/admin/configuracao`
- **Posição no Shell/Backoffice**: Item "Parâmetros Financeiros" na seção Proprietário (após "Usuários e Permissões")
- **Nav item criado**: `id="configuracao"` com ícone `configuracao` (SlidersHorizontal), `allPermissions: ["admin.acessar", "configuracao.alterar"]`
- **Permissões utilizadas**: `admin.acessar` (gate administrativo) + `configuracao.alterar` (operação de configuração)
- **APIs/fachadas utilizadas**: `GET/PUT /v1/admin/configuracao/{unidade_id}` via `http_api/admin_configuracao.py` → `AplicacaoAdministracaoProprietarioV1.obter_configuracao/salvar_configuracao`
- **Arquivos criados/alterados**:
  - `http_api/admin_configuracao.py` (novo) — DTOs e router HTTP
  - `http_api/frontend_app.py` — registro do router
  - `tests/api/test_admin_configuracao_http_contract.py` (novo) — 9 testes de contrato
  - `web/src/app/admin/configuracao/page.tsx` (novo)
  - `web/src/features/backoffice/empresa/services/empresa-api.ts` — interface `ConfiguracaoFinanceira` + `obterConfiguracao`/`salvarConfiguracao`
  - `web/src/features/backoffice/empresa/components/ConfiguracaoWorkspace.tsx` (novo) — UI tabela + formulário de edição
  - `web/src/features/shell/module-registry.ts` — módulo `configuracao`
  - `web/src/features/shell/components/DashboardHome.tsx` — ícone SlidersHorizontal
  - `web/src/features/shell/components/UnifiedAppShell.tsx` — ícone SlidersHorizontal
  - `web/src/components/ui/label.tsx` (novo) — componente Label reutilizável
- **Testes executados**:
  - 9 testes HTTP novos (`test_admin_configuracao_http_contract.py`): 9/9 passam
  - 25 testes relacionados à configuração: 25/25 passam (inclui integração, unit, fitness)
  - Ruff: clean (imports ordenados, F821 corrigido)
  - ESLint: clean para arquivos WP-024 (arquivos pré-existentes WP-023 com erros conhecidos mantidos)
  - TypeScript: `npx tsc --noEmit` passa
  - Build: `npm run build` sucesso (rota `/admin/configuracao` incluída)
  - `git diff --check`: clean (apenas avisos CRLF Windows)
- **Core/Application/Infra**: **sem alteração funcional** — reutilização total de `ConfiguracaoEstabelecimento`, `obter_configuracao`, `salvar_configuracao`, validação de segredos, concorrência otimista via versão
- **Segredos**: excluídos do escopo (WP-026)
- **Commits**:
  - `1b41cb4a1ee10faf6ec9034e1fb2a462e70ca0be` — WP-024: Implementar Parâmetros Financeiros (Configuração) no Backoffice
  - `f4c159bbdf444540cfd270dac3ef40fb28520d27` — WP-024: Fix Ruff import e ESLint any types
- **CI**: Workflow "Assistente Fase 4 Gate V1" permanece vermelho por `tests/unit/integracoes/test_whatsapp_control_plane_runtime_v1.py::test_crm_so_declara_sucesso_apos_confirmacao_do_envio`. Essa falha é **preexistente** ao WP-024 e já ocorria no commit `40127b77a2ec14625310517df17f3af282e70eec` (anterior ao WP-024). Não atribuída ao WP-024; não corrigida nesta tarefa.
- **PR #118**: mantida OPEN/DRAFT
- **WP-025 + WP-026**: permanecem pendentes
