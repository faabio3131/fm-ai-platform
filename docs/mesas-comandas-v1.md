# Mesas e comandas V1 — PR11

## Objetivo

Implementar o ciclo operacional de salão sobre `Pedido`, `Pagamento` e as máquinas normativas existentes, com mapa de mesas, participantes, múltiplos pedidos por comanda, transferência, junção, separação, divisão da conta, pagamento misto e fechamento.

A comanda organiza consumo e fechamento; ela não substitui `Pedido`, `Pagamento` nem `Venda`.

## Dependências

- PR5: máquina normativa de `Comanda` e autorização;
- PR7: pagamento e consequência financeira `Venda`;
- PR9: Central de Pedidos;
- PR10 já concluída e incorporada à `main` antes da criação desta branch.

## Escopo

- `Mesa` física, multi-tenant e por unidade;
- `Comanda` com versão otimista e estados normativos;
- participantes opcionais;
- vínculo de múltiplos `Pedido`s à mesma comanda;
- transferência entre mesas;
- junção e separação de comandas sem duplicar pedidos;
- plano de divisão da conta;
- múltiplos métodos no mesmo fechamento;
- projeção append-only de pagamentos já confirmados pelo domínio financeiro;
- fechamento apenas com saldo resolvido ou recebimento posterior autorizado;
- eventos operacionais idempotentes e auditáveis;
- migration somente em SQLite explicitamente efêmero/teste;
- feature flag fail-closed somente em `FM_AI_TEST_MODE=1`.

## Não escopo

- interface móvel do garçom (PR12);
- expedição/entrega (PR13);
- impressão (PR14);
- adquirente/gateway novo;
- deploy de produção;
- migration no banco real;
- alteração destrutiva das tabelas de Pedido/Pagamento/Venda existentes.

## Máquina normativa de Comanda

Estados preservados de `docs/maquinas-de-estado-v1.md`:

`aberta -> em_consumo -> conta_solicitada -> fechamento_em_andamento -> parcialmente_paga -> fechada`

Também são preservados `conta_solicitada -> em_consumo` e cancelamento permitido somente conforme as regras normativas. Estados terminais não são reabertos.

## Invariantes

1. Todo acesso é escopado por `tenant_id + unidade_id` derivados de `ContextoExecucao`.
2. Código de mesa é único por tenant/unidade.
3. Número da comanda é único por tenant/unidade.
4. Um `pedido_id` pode estar vinculado a no máximo uma comanda por vez.
5. Transferir/juntar/separar não copia Pedido; altera apenas o vínculo operacional.
6. Operações mutáveis usam `versao` e CAS; versão divergente falha fechada.
7. A soma dos pedidos vinculados determina o total operacional da comanda.
8. A soma das parcelas planejadas para fechamento deve ser exatamente o saldo da comanda.
9. Pagamento misto é uma composição de parcelas; cada confirmação financeira continua pertencendo ao domínio de Pagamento da PR7. O Salão valida a linha autoritativa em `pagamentos_v1` e rejeita pagamento ausente, não pago, de outra comanda, com método/valor divergente ou já projetado.
10. A projeção de pagamento da comanda só aceita um pagamento confirmado por referência/idempotency key e não captura dinheiro por conta própria.
11. `Comanda.fechada` exige saldo zero ou recebimento posterior explicitamente autorizado, além de pedidos resolvidos.
12. Fechar a comanda libera a mesa somente quando não houver outra comanda ativa ocupando o mesmo recurso.
13. Eventos e confirmações financeiras são append-only; correções financeiras são compensatórias no domínio de Pagamento.
14. PII de participante é opcional e minimizada; apelido não deve ser usado para dados sensíveis.

## Segurança e RBAC

- abertura: `MESA_ABRIR`;
- transferência de mesa: `MESA_TRANSFERIR`;
- alterações de consumo/divisão: `COMANDA_ALTERAR`;
- fechamento: `COMANDA_FECHAR`;
- confirmação financeira não é fabricada pelo salão: recebe referência de pagamento já confirmado;
- `Gerente IA` não ganha permissão operacional adicional nesta PR.
- cancelamento de comanda é restrito a gerente/administrador, exige pedidos resolvidos e ausência de pagamento confirmado.

## Runtime de teste e autoridade financeira

O E2E isolado pode materializar uma confirmação financeira simulada apenas por helper protegido por `FM_AI_TEST_MODE=1` + `FM_AI_SALAO_V1=1`. O serviço de Salão nunca transforma um identificador arbitrário em pagamento confirmado: ele consulta a persistência financeira autoritativa da PR7 antes de projetar a confirmação na comanda.

## Persistência aditiva

Tabelas novas usam prefixos/nomes V1 exclusivos para mesa, comanda, participantes, vínculos de pedidos, parcelas de fechamento, projeção de pagamentos confirmados e eventos de salão. Nenhuma tabela legada é removida ou reescrita.

## Feature flag e rollout

`FM_AI_SALAO_V1=1` só habilita a superfície executável quando `FM_AI_TEST_MODE=1`. Fora de teste a flag falha fechada. Não há rollout de produção nesta PR.

## Rollback

- desabilitar `FM_AI_SALAO_V1` remove a superfície executável;
- downgrade autorizado somente em banco SQLite efêmero/teste remove apenas tabelas da PR11;
- nenhum downgrade automático é permitido em banco real.

## Gates previstos

- unitários: estados, RBAC, valores, divisão, fechamento e idempotência;
- integração: multi-tenant/IDOR, CAS, múltiplos pedidos, transferência, junção/separação e migration;
- financeiro: soma de parcelas, pagamentos mistos, saldo, recebimento posterior e zero dupla confirmação;
- E2E: mapa de mesas + abertura/consumo/transferência/divisão/fechamento;
- suíte Python completa, Ruff, mypy e E2E padrão permanecem obrigatórios.

Nenhum gate autoriza merge, deploy, migration real ou início da PR12 sem aprovação humana explícita.
