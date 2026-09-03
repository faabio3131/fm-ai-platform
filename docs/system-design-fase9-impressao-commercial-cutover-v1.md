# SYSTEM DESIGN — FASE 9 — IMPRESSÃO POR SETOR — CUTOVER COMERCIAL V1

**Projeto:** KORDENA / GERENTE AI V1.0  
**Fase:** 9 — Impressão por Setor  
**Issue:** #77  
**Branch:** `recovery/v1-fase9-impressao-commercial-cutover`

## 1. Objetivo

Promover a Impressão por Setor V1 já existente ao runtime comercial sem reescrever o domínio/spool e sem transformar impressão em autoridade de negócio.

A impressão é um side effect operacional opcional, posterior à decisão autoritativa do KDS. Hardware, rede ou spool externo podem falhar; KDS/Pedido não podem ser revertidos por isso.

## 2. Autoridades

- Pedido: `core/pedidos`.
- Produção: KDS autoritativo.
- Spool de impressão: `core/impressao`.
- Identidade/RBAC: contexto autenticado canônico.
- Auditoria: infraestrutura canônica já existente.
- Adapter físico: implementação da porta `PortaImpressora`; nunca autoridade de estado do pedido.

## 3. Fluxo Target

1. Um item entra na produção pelo fluxo canônico do KDS.
2. Após a decisão autoritativa de roteamento/produção, uma integração de side effect recebe os dados mínimos do item/setor.
3. A integração invoca `ServicoSpoolImpressao.enfileirar_item_kds` com contexto real e idempotency key determinística.
4. O spool persiste o job antes da tentativa física.
5. Um processor/worker operacional solicita o job persistido e chama `PortaImpressora.imprimir`.
6. Sucesso marca o job como impresso.
7. Falha normalizada incrementa tentativa; ao atingir a política configurada, o job entra em contingência.
8. KDS/Pedido permanecem inalterados em qualquer falha de impressão.
9. Reimpressão exige RBAC, motivo e auditoria.

## 4. Fronteira transacional

### 4.1 Regra principal

A transação autoritativa do KDS não deve depender do sucesso físico da impressora.

Não é permitido:
- abrir conexão com hardware dentro da transação autoritativa do KDS;
- rollback de KDS/Pedido por falha de impressão;
- `commit()` escondido em UI, adapter físico ou domínio;
- marcar sucesso de impressão antes do adapter confirmar retorno sem erro.

### 4.2 Integração recomendada

A integração KDS → impressão deve ser baseada em evento/outbox ou em um pós-commit governado equivalente já existente no runtime, preservando:
- at-least-once delivery;
- idempotência no spool;
- recuperação/replay;
- correlação;
- isolamento tenant/unidade.

O spool já contém deduplicação e deve ser a proteção final contra duplicação física causada por replay de integração.

## 5. Adapter comercial de impressão

### 5.1 Contrato existente

Implementar exatamente `PortaImpressora`:

`imprimir(*, impressora_id: str, job_id: str, conteudo: str) -> None`

O domínio não deve conhecer fabricante, protocolo ou sistema operacional.

### 5.2 Estratégia plugável

O runtime comercial deve permitir adapters substituíveis, por exemplo:
- spool do sistema operacional;
- fila TCP/RAW para impressora de rede;
- serviço local/print-agent;
- provider gerenciado futuro.

A escolha concreta deve ficar fora de `core/impressao`.

### 5.3 Erros

Todo erro de I/O/protocolo deve ser traduzido para `ErroAdaptadorImpressao` ou contrato normalizado equivalente na borda.

Não vazar exceções específicas de driver para o domínio.

## 6. Print Agent e topologia física

Para produção profissional, a arquitetura preferencial é separar o servidor SaaS da rede física do restaurante.

Target recomendado:
- cloud/runtime comercial gera e persiste spool;
- um Print Agent autenticado por unidade busca/recebe jobs autorizados;
- o agent fala com impressoras locais por protocolo apropriado;
- ACK/falha volta ao spool;
- credenciais e impressoras são tenant/unidade-scoped.

Isto evita exigir acesso direto da nuvem à LAN do cliente e permite evolução multi-tenant com isolamento.

A F9 pode começar por um adapter comercial controlado compatível com o ambiente de homologação, mas a porta deve permanecer preparada para o Print Agent profissional.

## 7. Configuração

Destino de impressão deve ser resolvido por:
- tenant_id;
- unidade_id;
- setor_id;
- impressora_id;
- ativo/inativo;
- max_tentativas;
- provider/adapter selecionado pelo runtime.

É proibido hardcode global de uma impressora para todos os tenants.

## 8. Segurança e privacidade

Ticket operacional deve conter apenas dados necessários à produção.

Por padrão, não imprimir:
- cartão;
- dados financeiros;
- telefone;
- e-mail;
- endereço completo;
- tokens/segredos.

Reimpressão exige `IMPRESSAO_REIMPRIMIR`, motivo e auditoria.

## 9. Resiliência

Obrigatório provar:
- adapter indisponível;
- timeout;
- retry;
- contingência;
- duplicação de evento;
- replay;
- concorrência no mesmo job;
- tenant/unidade cruzados recusados;
- reimpressão idempotente/auditada;
- recuperação após retorno da impressora.

## 10. Observabilidade mínima

Métricas/eventos úteis:
- jobs pendentes por unidade/setor;
- idade do job mais antigo;
- tentativas;
- jobs em contingência;
- taxa de sucesso/falha por impressora;
- tempo enfileirado → impresso;
- reimpressões e motivos;
- adapter indisponível.

Nenhuma métrica deve carregar conteúdo integral do ticket como label/log.

## 11. Migration policy

O schema atual do spool deve ser reutilizado. Migration F9 nova somente se a implementação revelar drift objetivo que não possa ser resolvido por composição/configuração.

## 12. Gates previstos

### F9-B
- commercial composition boundary;
- adapter registry real;
- anti-fake fitness;
- compile/Ruff/mypy;
- regressões impressão/KDS.

### F9-C
- KDS → event/outbox → spool;
- idempotência/replay;
- ownership transacional;
- PostgreSQL.

### F9-D
- falhas do adapter;
- retry/contingência;
- CAS/concorrência;
- isolamento;
- reimpressão auditada.

### F9-E
- runtime comercial sem TEST_MODE;
- identidade real;
- PostgreSQL e migrations oficiais;
- KDS real → spool real → adapter comercial;
- browser/runtime E2E;
- evidência física/real de impressão quando hardware/print-agent estiver disponível.

## 13. Critério de fechamento

Fase 9 somente fecha como candidata comercial quando:
- nenhum Fake/Mock está no caminho comercial;
- KDS → spool está integrado e idempotente;
- adapter comercial existe e falha de forma controlada;
- resiliência está provada;
- matriz transversal permanece verde;
- readiness é reconciliado;
- evidência física/real exigida pelo Documento Mestre está registrada ou explicitamente classificada como dependência externa sem falsificar homologação.
