# PR13 — Expedição e Entrega V1

## Status

Documento executivo inicial da PR13. A implementação permanece atrás de feature flag e sem deploy ou migration em banco real.

## Problema

Depois que a produção fica pronta, o sistema precisa controlar conferência, embalagem, atribuição, custódia, tentativas, prova de entrega e pagamento na entrega sem confundir estado logístico com estado financeiro.

## Escopo

- checklist de expedição por pedido;
- atribuição e reatribuição de entregador;
- coleta e início de custódia;
- saída/em rota;
- registro de tentativa falha e nova tentativa;
- prova mínima de entrega por referência, sem armazenar segredo ou payload bruto;
- conclusão logística;
- coordenação com pagamento na entrega sem transformar `Entrega` em fonte financeira;
- RBAC para expedição/entregador/gerente;
- tenant + unidade em todos os comandos e leituras;
- concorrência otimista, idempotência, auditoria e métricas sem PII;
- E2E das transições completas e regressão PR10/PR12.

## Não escopo

- roteirização avançada;
- tracking GPS contínuo;
- integração real com frota/marketplace;
- armazenamento de foto/documento bruto de prova;
- captura de dados PCI;
- alteração destrutiva de banco;
- deploy de produção.

## Dependências

PR7 (pagamentos) e PR10 (KDS) são dependências normativas. PR12 já fornece a interface do garçom e permanece independente do fluxo de entrega.

## Máquina de estado normativa

Transições permitidas:

1. `aguardando_producao -> aguardando_expedicao` por sistema quando o pedido estiver pronto;
2. `aguardando_expedicao -> aguardando_entregador` por expedição após checklist completo;
3. `aguardando_producao|aguardando_expedicao|aguardando_entregador -> atribuida` por expedição/adapter com entregador aceito;
4. `atribuida -> coletada` após conferência física;
5. `coletada -> em_rota` após saída registrada;
6. `coletada|em_rota -> entregue` somente com prova/confirmação válida e pagamento na entrega resolvido ou exceção autorizada;
7. `em_rota -> tentativa_falhou` com motivo e número da tentativa;
8. `tentativa_falhou -> atribuida` para nova tentativa, incrementando contador;
9. estados pré-custódia e `tentativa_falhou -> cancelada` por alçada autorizada quando pedido/custódia estiverem resolvidos.

Transições não listadas são recusadas.

## Invariantes

- `Produção.pronta` não conclui Pedido, Venda ou Entrega.
- `Entrega.entregue` não confirma pagamento por si só; o financeiro permanece autoritativo.
- Dinheiro/cartão na entrega só pode ser refletido após confirmação financeira própria ou exceção auditada prevista na política.
- Entregador não recebe permissão financeira por conveniência de interface.
- Prova de entrega é uma referência mínima; não persistimos token, PAN, CVV, segredo ou payload bruto.
- Estado terminal não reabre; contestação/correção é ocorrência separada.
- Toda mutação exige tenant, unidade, ator, `correlation_id`, versão esperada e chave de idempotência.

## Dados mínimos / LGPD

A projeção logística deve trabalhar com identificadores e referência de endereço já autorizada. Telefone, localização e prova são dados pessoais e devem ser minimizados. A PR13 não cria tracking contínuo nem retém payload bruto de localização/prova.

## Feature flag

`FM_AI_ENTREGA_V1=1` somente quando `FM_AI_TEST_MODE=1` nesta etapa. Fora do runtime de teste a flag é fail-closed.

## Observabilidade

Métricas mínimas sem PII:

- entregas aguardando expedição;
- entregas aguardando entregador;
- atribuições/reatribuições;
- coletas;
- entregas concluídas;
- tentativas falhas;
- recusas por RBAC/escopo;
- conflitos de versão/idempotência;
- pagamento na entrega pendente na tentativa de conclusão.

## Rollback

Desabilitar `FM_AI_ENTREGA_V1`. Nenhuma migration real é parte deste início de PR.

## Gates

- Ruff e mypy no escopo PR13;
- testes unitários de estados, validações e flag;
- integração multi-tenant, CAS e idempotência;
- E2E checklist -> atribuição -> coleta -> rota -> entrega;
- E2E tentativa falha -> reatribuição;
- E2E pagamento na entrega pendente bloqueando conclusão;
- regressão KDS e suíte Python completa.

## Aprovação

A PR13 será mantida como draft até os gates ficarem verdes. Merge, deploy, migration real e início da PR14 exigem aprovação humana explícita.
