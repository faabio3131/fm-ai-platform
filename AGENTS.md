# Kordena / GERENTE AI — instruções permanentes para agentes

Estas instruções são subordinadas às autoridades oficiais do projeto e não as substituem.

## Hierarquia de autoridade

1. **Documento Mestre** — `GERENTE_AI_V1_PROTOCOLO_MESTRE_DE_EXECUCAO` (Drive ID `1oCZpdvettJxo2udyoWTEE5h0X3clB9BQ`).
2. **System Design Master** — `GERENTE AI V1.0 — SYSTEM DESIGN MASTER` (Drive ID `1QB-v7P7CchvUMuir3tGtHwnBSeQAo53TDdof6wtH_f0`).
3. ADRs/decisões arquiteturais vigentes, inclusive ADRs corretivos adotados.
4. Gate/tarefa atual explicitamente autorizada.
5. Código, testes e documentação local.

Se houver conflito entre código/conversa e Documento Mestre/System Design, **pare de forma segura e peça reconciliação**. Não invente uma resolução.

Para fatos de Git (branches, SHA, merge, PR, remoto), o **GitHub remoto** é a autoridade factual.

## Skills do projeto

Quando a tarefa corresponder ao escopo, use as Skills em `.agents/skills/`:

- `kordena-system-design-guardian`: arquitetura, autoridade de domínio, multi-tenant, migrations, segurança e impacto estrutural.
- `kordena-validation-release-gate`: testes, fitness tests, regressão, homologação física e definição de pronto.
- `kordena-git-repository-governance`: branches, commits, worktrees, PRs, preservação e sincronização Work/GitHub/VS Code.

## Princípios permanentes

- **Preservar o que funciona; evoluir o incompleto; substituir somente com justificativa técnica demonstrável.** Não reescrever por elegância.
- Arquitetura alvo: **Monólito Modular Governado**; boundaries e autoridades explícitas; simplicidade operacional acima de complexidade acidental.
- Active Execution Scope é autoridade de contexto; nenhum fallback silencioso para primeira loja, loja global ou valor de UI.
- Multi-tenant/unidade, RBAC, auditoria, idempotência, migration/rollback e ownership transacional devem ser avaliados em mudanças estruturais.
- Falhar fechado quando não for possível provar tenant/unidade, permissão, mapping, integridade ou origem de dado.
- IA não recebe autoridade operacional implícita; operações críticas passam por contratos e domínios autoritativos.
- O nome do assistente é configurável por tenant; não hardcode `Mica` como identidade de produto.
- V2 permanece fora de escopo até fechamento funcional da V1, salvo autorização explícita.

## Regra de execução

Fluxo padrão:

`auditar → desenhar → implementar → provar → revisar → publicar checkpoint → reproduzir fisicamente → homologar`

Antes de código estrutural, registrar pelo menos:

- autoridade/source of truth afetada;
- contratos/boundaries;
- impacto tenant/unidade/RBAC/auditoria;
- migrations e compatibilidade fresh/upgrade;
- rollback/fail-closed;
- testes/fitness necessários;
- STOP/gate esperado.

Se surgir novo bloqueador estrutural fora do gate atual, **pare e reporte**. Não abra uma cadeia infinita de correções por conta própria.

## Work Cloud, Codex Local e ambiente físico

- Work Cloud é ambiente de execução assistida/sandbox, **não cofre permanente nem autoridade final**.
- Nenhuma mudança relevante pode permanecer somente no Work.
- Gate técnico aprovado deve gerar checkpoint rastreável em Git antes de acumular outro grande bloco.
- O mesmo SHA candidato deve ser reproduzido no **VS Code/PC físico** antes de status final de homologação.
- `passou no Work` significa evidência técnica intermediária; **não significa 100% pronto**.
- O fluxo preferencial é: `CHAT/System Design → Work ou Codex Local → Gate → GitHub → VS Code físico/Codex Local → testes/runtime → homologação`.

## Git e segurança do patrimônio

- Nunca use `git add -A` nem `git add .`; stage somente paths/hunks explícitos e auditados.
- Nunca reset/clean/restore/checkout destrutivo sobre worktree dirty sem preservação e autorização.
- Nunca force push, rebase destrutivo ou merge cego de PRs históricas.
- Não descarte untracked sem inventário e proveniência.
- Worktree dirty do usuário é patrimônio até prova em contrário.
- PR aberta não é obrigação de merge; primeiro classifique como incorporada, parcial, necessária, superseded ou referência.
- `main` não recebe merge/deploy sem gate e autorização explícita do proprietário.

## Definição de pronto

Tela isolada, unit test, migration, backend ou PR individual **não bastam** para declarar V1 pronta.

Um bloco só pode receber status final quando, conforme aplicável:

- implementação e integração concluídas;
- testes direcionados e regressão verdes ou divergências formalmente classificadas;
- fresh/upgrade de schema comprovados;
- tenant/unidade/RBAC/auditoria/idempotência comprovados;
- runtime/jornada real comprovados;
- homologação física/manual realizada;
- PostgreSQL/browser/dispositivo/provedor real comprovados quando forem requisitos do bloco;
- nenhuma pendência crítica incompatível com o Documento Mestre.

## Autoridade humana

O proprietário mantém a autorização final para gates críticos, integração Git, merge em `main`, migration produtiva, deploy e encerramento comercial da V1.
