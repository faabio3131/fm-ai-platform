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

HTTP fino que apenas repassa os campos ao Application herdaria o desvio. Impedir isso somente no React deixaria a API exposta; introduzir a validação de autorização no HTTP criaria uma regra paralela. Alterar `criar_usuario` para validar também a unidade padrão contra o conjunto autorizado mudaria o comportamento funcional da autoridade existente, ultrapassando a autorização de extração mecânica. Não foi realizada essa correção.

A correção mínima deve ser avaliada em gate funcional específico na autoridade Application; não foi demonstrada necessidade de alterar Core/Infra. Esse gate deve provar rejeição da unidade padrão externa, rollback sem usuário/membership/auditoria de sucesso parcial e preservação dos contratos legítimos, antes de retomar a migração WP-023.

- Responsável pela decisão de escopo: proprietário/Diretor.
- Critério de retomada: decisão explícita sobre o bloqueador e autoridade validada sem concessão de unidade fora do escopo.
- WP-023: **BLOQUEADO NA AUDITORIA**, sem rota/endpoint novo e sem commit de implementação.
- WP-024: **NÃO INICIADO**, dependente da publicação completa de WP-023.
- Application/Core/Infra: não alterados. Papéis, matriz RBAC, schema e dependências: não alterados.
- Gates de implementação Python/frontend: não executados, pois não houve implementação; a reprodução é evidência de defeito, não aprovação da migração. `git diff --check` aplicável somente a este checkpoint documental.
- Merge, deploy, Smoke Mestre, certificação integrada e Visual Premium: não executados.
- Este checkpoint publica somente documentação do bloqueio; **nenhum dos dois WPs está entregue**. WP-025 + WP-026 permanecem apenas planejamento futuro, condicionado ao fechamento deste ciclo.
