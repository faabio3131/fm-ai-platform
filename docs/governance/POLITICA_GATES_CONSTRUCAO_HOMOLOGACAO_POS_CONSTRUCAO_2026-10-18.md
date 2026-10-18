# FM Tecnologia — Política de Separação entre Construção, Testes Externos, Homologação e Produção

**Decisão do proprietário:** 18/10/2026  
**Status:** APROVADA COMO DIRETRIZ DE EXECUÇÃO; integração documental pendente de merge canônico  
**Âmbito:** Kordena V1 como aplicação inicial; diretriz corporativa a ser incorporada nos demais SaaS ao reconciliar seus próprios cronogramas e AGENTS.md.  
**Prioridade:** evitar bloqueios artificiais, retrabalho, regressão e retornos repetidos a etapas concluídas.

## 1. Regra constitucional do processo de engenharia

**Construção 100% concluída não é sinônimo de testes externos aprovados, homologação nem liberação de produção.** Todo trabalho que depende de credenciais reais de terceiros, configuração de conta ou ambiente externo, autorização de instituição, hardware físico, clientes-piloto, dados reais ou execução em campo pertence à etapa posterior de testes externos/homologação, nunca ao gate de conclusão da construção.

Construir até 100% significa implementar e integrar todos os contratos, telas, rotas, backends, fluxos, permissões, persistência, migrações e mecanismos planejados; provar isso com testes internos executáveis e ambientes controlados; corrigir todos os defeitos de engenharia identificáveis nessa fase. Não se admite marcar como construído um stub/fake que substitua uma funcionalidade planejada em produção: mocks e simuladores servem exclusivamente de prova durante a construção, nunca de substituição definitiva do código real.

**Não antecipar testes externos à construção 100%.** Pesquisas técnicas e implementações orientadas pela documentação de fornecedores são permitidas durante construção, mas homologação/credenciais/transações externas reais só após o checkpoint formal de construção. Não solicitar que o proprietário realize configuração externa ou teste real para permitir que a construção avance.

## 2. Estados obrigatórios e gates independentes

| Estado | Condição de ingresso | Evidência exigida | Não exige |
|---|---|---|---|
| `EM_CONSTRUCAO` | tarefas de engenharia abertas | itens, responsáveis, progresso, evidência incremental | qualquer homologação externa |
| `CONSTRUCAO_100_CONCLUIDA` | funcionalidades e integrações de software previstas implementadas, CI/regressão interna verde, testes locais com PostgreSQL real descartável quando aplicáveis, contratos e interfaces verificados, documentação reconciliada | SHAs, PRs, testes internos, migrações fresh/upgrade/rollback em ambiente descartável, provas de segurança, anti-bypass, cenários simulados e aceite técnico de engenharia | credenciais reais, fatura de fornecedor, contato com órgão oficial, teste físico ou cliente-piloto |
| `PRONTO_PARA_TESTES_EXTERNOS` | construção 100% fechada e roteiro seguro de homologação preparado | inventário de dependências externas, runbooks, plano de teste, reversão, responsáveis, matriz de evidências | resultado aprovado do teste externo |
| `HOMOLOGADO_APROVADO` | testes reais/externos executados e aprovados, bloqueios reais resolvidos | registros de provedores, fluxos externos, hardware, cliente-piloto e evidência apropriada | publicação comercial automática |
| `PRODUCAO_LIBERADA` | decisão de release/deploy específica e critérios operacionais aprovados | segurança, backups e restauração, infraestrutura, observabilidade, rollback, aprovação formal de produção | nenhuma aprovação presumida |

Cada um desses estados é independente. É correto declarar `CONSTRUCAO_100_CONCLUIDA` e `HOMOLOGACAO_EXTERNA_PENDENTE` ao mesmo tempo; é incorreto declarar `HOMOLOGADO_APROVADO` apenas porque o CI passou.

## 3. O que é permitido em cada fase

### Durante construção (sem depender de terceiros reais)
- Análise do repositório, projeto, implementação completa de API, UI e integrações; validações de entrada, concorrência, idempotência, autenticação, multi-tenant, mensagens, auditoria, fail-closed.
- Testes unitários, de contrato e integração em ambientes internos isolados; PostgreSQL real **descartável**; fixtures, mocks e provedores simulados; testes de capacidade internos; migrations dry run/fresh/upgrade e rollback em bases descartáveis.
- PRs e merges de construção após gates de engenharia 100% verdes, preservadas as regras de proteção de branch e autorização permanente vigente. O merge certifica apenas o código testado, não a operação externa.
- Revisão visual e premium após o encerramento das funcionalidades, conforme a ordem vigente do cronograma.

### Somente após construção 100% / na homologação externa
- Configurar credenciais reais e integrações de prestadores externos em suas contas oficiais, vincular gateways reais, ativar webhooks e efetuar movimentações reais.
- Testes end-to-end com OpenAI/Gemini cobrados em conta real, meta/WhatsApp, provedores fiscais, bancos, plataformas de pagamento, hardware físico, clientes reais e órgãos públicos.
- Medição econômica real e definição final de parâmetros comerciais que dependem de consumo observado em campo.
- Migração de dados reais e publicação produtiva somente com suas autorizações próprias; não inferir deploy de homologação ou merge.

## 4. Bloqueios e avanço do cronograma

1. Se uma tarefa **de código** falhar em teste interno, é uma pendência de construção: corrigir agora, executar os testes afetados e continuar na ordem do cronograma.
2. Se uma tarefa já estiver implementada e testada internamente, mas depender de credencial, hardware ou teste externo, classificá-la como `CONSTRUCAO_CONCLUIDA__HOMOLOGACAO_EXTERNA_PENDENTE`, registrar dependência e **prosseguir automaticamente** com as demais tarefas de construção.
3. Não colocar `provider real`, `piloto físico` ou `teste de produção` como condição para merge de PR puramente de construção. Quando workflows misturarem gates, separá-los em gates de engenharia e de homologação, sem eliminar qualquer teste.
4. Não voltar a fases, sessões, PRs ou tarefas finalizadas só para repetir prova já certificada. Reabrir somente diante de novo defeito demonstrado, mudança de requisito/contrato ou regressão evidenciada, referenciando SHA, teste e motivo.
5. Não marcar integrações ausentes ou simuladas como `100% construídas`. A separação de gates **não flexibiliza** a qualidade nem permite inventar implementação, teste ou aprovação.
6. Manter rastreabilidade distinta para: **pendências de engenharia**, **dependências/configurações externas**, **testes/homologação externa**, **liberação/deploy**. Pendências de um conjunto não devem rebaixar o status do outro.
7. Toda atividade deve partir do checkpoint do repositório e cronograma: primeiro descobrir o que existe e está concluído; não recomeçar o trabalho por falta de memória conversacional.

## 5. Critério de 100% da construção

Um módulo pode ser assinalado `CONSTRUCAO_100_CONCLUIDA` somente se:
- Nenhum TODO/placeholder/mock estiver substituindo o comportamento funcional previsto na versão de produto.
- UI, backend, domínio, banco, controle de acesso, integração interna e tratamento de erros necessários estiverem completos.
- Testes unitários, contratos, integração interna, segurança, migrações descartáveis, regressão afetada e CI aplicável estiverem 100% verdes.
- O código estiver versionado, revisado e reconciliado; casos impossíveis de provar internamente estiverem registrados **apenas** na matriz de homologação externa, não na dívida de construção.
- Existir um roteiro de teste real para ser executado **depois**, sem exigir sua execução prévia para fechar o status de engenharia.

## 6. Aplicação imediata à AI FinOps / franquias do Kordena

**Construção a fechar:** conectar calculadora de custo e rota real de uso; completar medição/ledger; implantar reserva transacional, idempotência, limites de franquia, bloqueio preventivo; sincronização local de direitos do Command; interface FinOps existente para saldo/avisos; integração entre UI/API/banco; testes simulados de consumo, concorrência e fail-closed; documentação e CI.

**Após construção:** configuração de provedores reais quando necessária, testes faturados de tokens, faturas oficiais e reconciliação externa; testes de campo com restaurantes; dimensionamento final da franquia e preços dependentes da medição real; homologação comercial e release. Os parâmetros de teste interno podem ser fictícios, explicitamente classificados como fixtures e nunca publicados como preços aprovados.

**Status correto enquanto código estiver incompleto:** `EM_CONSTRUCAO`; após completar tudo em código e gates internos: `CONSTRUCAO_100_CONCLUIDA` mesmo com `HOMOLOGACAO_EXTERNA_PENDENTE`.

## 7. Mudança de governança / compatibilidade

Esta diretriz atualiza o sentido de `100%` nos gates anteriores do `AGENTS.md`, documentos mestre, trackers e certificações. Onde documento histórico exigir provider real, hardware ou teste externo antes de **encerrar a construção**, o requisito permanece obrigatório **na etapa de homologação externa**, não é cancelado. Onde documentação histórica exigir prova de software integrada, segurança ou regressão interna, o requisito permanece no gate de construção.

**Proibido:** usar uma pendência externa para bloquear programação restante, misturar estados, retroceder por repetição de sessão, ou declarar produção sem homologação.

O executor deverá registrar explicitamente:
- `CONSTRUCAO: x/y tarefas; status e SHA`
- `GATES_INTERNOS: aprovados/pendentes`
- `DEPENDENCIAS_EXTERNAS: inventariadas, não executadas prematuramente`
- `HOMOLOGACAO_EXTERNA: não iniciada/em andamento/aprovada`
- `RELEASE: não autorizado/autorizado`

**Registro:** documento de governança da FM Tecnologia para uso no Kordena. Sem execução de provedor real, mudança de código funcional, migrations de produção, deploy ou merge nesta entrega.
