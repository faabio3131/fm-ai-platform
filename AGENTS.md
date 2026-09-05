# Kordena / GERENTE AI — instruções permanentes para agentes

Estas instruções são subordinadas às autoridades superiores do ambiente, às regras de segurança e às decisões explícitas do proprietário. Elas organizam a execução do projeto, mas não substituem essas autoridades.

## Hierarquia de autoridade

1. Instruções de sistema/plataforma e regras de segurança aplicáveis.
2. Instrução, autorização ou decisão mais recente explicitamente aprovada pelo proprietário, inclusive o gate/tarefa atual.
3. Estado real verificado nas fontes factuais adequadas: repositório local, GitHub, Supabase e demais sistemas oficiais acessíveis.
4. **Documento Mestre** — `GERENTE_AI_V1_PROTOCOLO_MESTRE_DE_EXECUCAO` (Drive ID `1oCZpdvettJxo2udyoWTEE5h0X3clB9BQ`).
5. **System Design Master** — `GERENTE AI V1.0 — SYSTEM DESIGN MASTER` (Drive ID `1QB-v7P7CchvUMuir3tGtHwnBSeQAo53TDdof6wtH_f0`).
6. ADRs/decisões arquiteturais vigentes, inclusive ADRs corretivos adotados.
7. Código, testes e documentação local.

Uma decisão mais recente explicitamente aprovada pelo proprietário pode atualizar uma decisão anterior do projeto. Quando houver conflito ambíguo, lacuna de evidência ou dúvida sobre a autorização, **pare de forma segura e peça reconciliação**. Não invente uma resolução.

Para fatos de Git, use a fonte correspondente ao objeto verificado:

- o **GitHub remoto** é a autoridade factual para branches remotas, PRs, merges, `main` remoto e SHAs efetivamente publicados;
- o **repositório local verificado** é a autoridade factual para branches locais, worktrees, staged/untracked, estado dirty e commits ainda não publicados;
- quando local e remoto divergirem, reconcilie por SHA, ancestralidade e proveniência; preserve checkpoints locais legítimos até publicação ou decisão explícita.

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
- **Visual Premium é a última fase funcional da V1.** Nenhuma dívida funcional, de cutover, migration, segurança ou integração pode ser empurrada para o redesign.
- **Deploy é etapa pós-funcional separada:** somente após Visual Premium aprovado e configuração/verificação do servidor real.

## Regra de execução

Fluxo padrão quando o ambiente possui autenticação Git:

`auditar → desenhar → implementar → provar → revisar → reconciliar → mergear → provar main pós-merge → liberar próxima fase`

Fluxo de contingência quando o ambiente de origem não pode publicar:

`auditar → desenhar → implementar → provar → revisar → gerar artefato verificável → transferir ao PC físico autenticado → conferir SHA/proveniência → publicar checkpoint → homologar`

Antes de código estrutural, registrar pelo menos:

- autoridade/source of truth afetada;
- contratos/boundaries;
- impacto tenant/unidade/RBAC/auditoria;
- migrations e compatibilidade fresh/upgrade;
- rollback/fail-closed;
- testes/fitness necessários;
- STOP/gate esperado.

Se surgir novo bloqueador estrutural fora do gate atual, **pare e reporte**. Não abra uma cadeia infinita de correções por conta própria.

## Gate de Fechamento Canônico e autorização permanente de merge

Antes de iniciar qualquer fase/módulo seguinte, o bloco atual deve cumprir integralmente este gate:

1. fixar o SHA final candidato;
2. executar **100% dos gates obrigatórios** da fase e da regressão transversal aplicável;
3. para liberar merge, todos devem terminar `SUCCESS`: não pode restar workflow `failed`, `cancelled`, `queued` ou `in_progress`;
4. corrigir qualquer vermelho e repetir os testes sem enfraquecer fitness, evidência, RBAC, tenant/unidade, idempotência, migration, fail-closed ou Definition of Done;
5. registrar evidências exigidas pelo bloco: Commercial Runtime E2E, PostgreSQL, navegador/dispositivo, provider e prova manual/física quando aplicáveis;
6. reconciliar Documento Mestre, System Design/ADR quando aplicável, Commercial Runtime Readiness, Inventário Mestre, checkpoint, issue e descrição da PR;
7. auditar PRs/branches relacionadas à fase, garantindo que nenhum delta útil fique esquecido fora da `main`; linhas superseded devem ser classificadas/encerradas sem apagar histórico;
8. manter dependências externas ou físicas não executáveis explicitamente registradas com responsável, critério de fechamento e fase final de homologação; nunca marcá-las como concluídas sem evidência;
9. somente então considerar o **MERGE LIBERADO**.

### Autorização permanente do proprietário

Por decisão explícita do proprietário em 05/09/2026, **não é necessário pedir nova autorização para o merge normal da PR canônica de uma fase** quando todos os requisitos do Gate de Fechamento Canônico acima estiverem comprovadamente verdes e reconciliados.

Nessa situação, o agente responsável está autorizado a:

- retirar a PR de draft quando necessário;
- fazer o merge do SHA canônico validado na `main`;
- aguardar e verificar os workflows de `push`/pós-merge da `main`;
- liberar a fase seguinte **somente se o pós-merge também fechar 100% verde**.

Se o CI pós-merge falhar, a sequência permanece bloqueada: investigar, corrigir, revalidar e reconciliar antes de iniciar qualquer nova fase.

Esta autorização permanente **não** autoriza deploy, migration produtiva irreversível, exclusão de dados reais, force push, transação financeira real, disparo massivo real, aumento de privilégios ou qualquer outro ato destrutivo/sensível que mantenha gate/autorização própria.

## Work Cloud, Codex Local e ambiente físico

- Work Cloud é ambiente de execução assistida/sandbox, **não cofre permanente nem autoridade final**.
- Nenhuma mudança relevante pode permanecer somente no Work.
- Gate técnico aprovado deve gerar checkpoint rastreável em Git antes de acumular outro grande bloco.
- O mesmo SHA candidato deve ser reproduzido no **VS Code/PC físico** antes de status final de homologação quando esse requisito for aplicável ao bloco.
- `passou no Work` significa evidência técnica intermediária; **não significa 100% pronto**.
- O fluxo preferencial é: `CHAT/System Design → Work ou Codex Local → Gate → GitHub → VS Code físico/Codex Local → testes/runtime → homologação`.
- Quando o Work não puder autenticar Git, aplique o fluxo de contingência por artefato verificável, sem contornar credenciais.

## Git e segurança do patrimônio

- Nunca use `git add -A` nem `git add .`; stage somente paths/hunks explícitos e auditados.
- Nunca reset/clean/restore/checkout destrutivo sobre worktree dirty sem preservação e autorização.
- Nunca force push, rebase destrutivo ou merge cego de PRs históricas.
- Não descarte untracked sem inventário e proveniência.
- Worktree dirty do usuário é patrimônio até prova em contrário.
- PR aberta não é obrigação de merge; primeiro classifique como incorporada, parcial, necessária, superseded ou referência.
- `main` só recebe merge pelo Gate de Fechamento Canônico. Quando o gate estiver 100% verde, vale a autorização permanente de merge acima. **Deploy nunca é inferido de merge.**

## Definição de pronto

Tela isolada, unit test, migration, backend ou PR individual **não bastam** para declarar V1 pronta.

Um bloco só pode receber status final quando, conforme aplicável:

- implementação e integração concluídas;
- testes direcionados e regressão 100% verdes;
- fresh/upgrade de schema comprovados;
- tenant/unidade/RBAC/auditoria/idempotência comprovados;
- runtime/jornada real comprovados;
- homologação física/manual realizada quando for requisito executável do bloco, ou pendência diferida formalmente para o gate final quando depender de hardware/provider indisponível;
- PostgreSQL/browser/dispositivo/provedor real comprovados quando forem requisitos do bloco;
- readiness/inventário/documentação/issue/PR reconciliados;
- PR canônica mergeada e CI pós-merge da `main` 100% verde;
- nenhuma pendência crítica incompatível com o Documento Mestre.

## Fechamento da V1 e release

- Fases funcionais/cutovers são concluídos primeiro.
- A fase de homologação final fecha pendências funcionais, externas e físicas classificadas.
- **Visual Premium vem por último como última fase funcional.**
- Depois do Visual Premium aprovado, configura-se e valida-se o servidor/ambiente real: banco, migrations, rede/DNS/TLS, segredos/Vault, backups/restore, observabilidade, smoke tests e rollback.
- Somente depois existe gate de deploy/release.
- Merge aprovado não equivale a autorização de deploy.

## Autoridade humana

O proprietário mantém a autoridade constitucional/final do projeto. A autorização permanente acima cobre somente **merge normal de PR canônica após 100% dos gates verdes e reconciliação completa**. Deploy, atos destrutivos ou irreversíveis, decisões de escopo crítico e encerramento comercial final continuam sujeitos aos gates e autorizações específicas definidos pelo Documento Mestre.
