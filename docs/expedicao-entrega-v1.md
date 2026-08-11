# PR13 — Expedição e Entrega V1

## Status

Implementação V1 concluída na branch da PR13 e validada por gates automatizados. Permanece atrás de feature flag, sem deploy ou migration em banco real, e aguarda aprovação humana explícita para merge.

## Problema

Depois que a produção fica pronta, o sistema precisa controlar conferência, embalagem, atribuição, custódia, tentativas, prova de entrega e pagamento na entrega sem confundir estado logístico com estado financeiro.

## Escopo entregue

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
- concorrência otimista por versão, idempotência persistente e eventos auditáveis;
- persistência aditiva materializada apenas no runtime isolado de testes;
- E2E de expedição em tablet e entregador em celular;
- regressão das PR10, PR11 e PR12.

## Não escopo

- roteirização avançada;
- tracking GPS contínuo;
- integração real com frota/marketplace;
- armazenamento de foto/documento bruto de prova;
- captura de dados PCI;
- alteração destrutiva de banco;
- deploy de produção.

## Dependências

PR7 (pagamentos) e PR10 (KDS) são dependências normativas. PR12 fornece a interface do garçom e permanece independente do fluxo de entrega.

## Máquina de estado normativa

Transições permitidas:

1. `aguardando_producao -> aguardando_expedicao` por sistema quando o pedido estiver pronto;
2. `aguardando_expedicao -> aguardando_entregador` por expedição após checklist completo;
3. `aguardando_producao|aguardando_expedicao|aguardando_entregador -> atribuida` por expedição/adapter com entregador aceito;
4. `atribuida -> coletada` após conferência física;
5. `coletada -> em_rota` após saída registrada;
6. `coletada|em_rota -> entregue` somente com prova/confirmação válida e critério financeiro resolvido;
7. `em_rota -> tentativa_falhou` com motivo e número da tentativa;
8. `tentativa_falhou -> atribuida` para nova tentativa, incrementando contador;
9. estados pré-custódia e `tentativa_falhou -> cancelada` por alçada autorizada quando o Pedido autoritativo estiver cancelado.

Transições não listadas são recusadas.

## Invariantes

- `Produção.pronta` não conclui Pedido, Venda ou Entrega.
- `Entrega.entregue` não confirma pagamento por si só; o financeiro permanece autoritativo.
- Dinheiro/cartão na entrega só pode ser refletido após confirmação financeira própria ou recebimento posterior explicitamente autorizado.
- A leitura financeira da PR13 é somente leitura: não cria, captura nem confirma pagamento.
- Entregador não recebe permissão financeira por conveniência de interface.
- Entregador só visualiza/opera entregas atribuídas ao próprio `usuario_id`; consultas são escopadas por tenant + unidade.
- A coleta exige produção pronta e checklist concluído, preservando a transferência de custódia.
- Prova de entrega é uma referência mínima; não persistimos token, PAN, CVV, segredo ou payload bruto.
- Estado terminal não reabre; contestação/correção é ocorrência separada.
- Toda mutação exige tenant, unidade, ator, `correlation_id`, versão esperada e chave de idempotência.

## Dados mínimos / LGPD

A projeção logística trabalha com identificadores e referência de endereço já autorizada. Telefone, localização e prova são dados pessoais e devem ser minimizados. A PR13 não cria tracking contínuo nem retém payload bruto de localização/prova.

## Feature flag

`FM_AI_ENTREGA_V1=1` somente quando `FM_AI_TEST_MODE=1` nesta etapa. Fora do runtime de teste a flag é fail-closed.

## Persistência e banco

`DeliveryBase`, `EntregaORM` e `EventoEntregaORM` são aditivos e materializados apenas pelo runtime isolado de testes da PR13. Não existe migration de produção nesta PR. O E2E rejeita explicitamente `banco_erp_local.db` e só usa `.tmp/fm-ai-playwright`.

## Observabilidade e auditoria

Os eventos de entrega registram escopo, ator, `correlation_id`, `causation_id`, versão, chave de idempotência, hash do comando e payload mínimo. Não são persistidos dados de cartão nem payload bruto de prova.

## Rollback

Desabilitar `FM_AI_ENTREGA_V1`. Nenhuma migration real ou deploy de produção faz parte da PR13.

## Evidência de validação

No código funcional validado antes desta atualização documental:

- Ruff PR13: `All checks passed!`;
- mypy PR13: `Success: no issues found in 13 source files`;
- testes focados de entrega: `10 passed`;
- suíte Python completa: `348 passed`;
- E2E PR13: `3 passed`, cobrindo checklist/atribuição, custódia com financeiro resolvido e bloqueio de conclusão com pagamento `aguardando_entrega`;
- regressão PR10/KDS: verde;
- regressão PR11/Salão: verde;
- regressão PR12/Garçom: verde;
- branch: 0 commits atrás da `main`.

A atualização deste documento também passa pelos mesmos workflows antes da aprovação final de merge.

## Aprovação

A PR13 permanece como draft. Merge, deploy, migration real e início da PR14 exigem aprovação humana explícita.
