# F13-B — Current → Target — Cashback Application Boundary

## Baseline certificado

- Origem: F13-A code-certified.
- SHA base: `8748fa338b8ec418609029f100cdaccb7bb5998a`.
- Branch: `recovery/v1-fase13b-cashback-application-boundary`.
- Nenhum merge, deploy ou produção é autorizado por este documento.

## Current comprovado

1. `core/crm/cashback.py` já define o ledger canônico e `ServicoCashback`.
2. `infra/crm/cashback_sqlalchemy.py` persiste movimentos append-only e a projeção transacional de saldo na mesma `Session`.
3. `infra/transacoes/uow.py` é a fronteira transacional única da aplicação; `RecursosTransacionaisV1` reutiliza a `Session` sem assumir commit.
4. `application/finalizacao_pagamento.py` executa a finalização econômica e chama `application/pdv_legacy_projection.py` dentro desse mesmo limite transacional.
5. `application/pdv_legacy_projection.py` ainda calcula, valida, debita e credita `clientes.saldo_cashback` diretamente. Portanto o legado ainda participa da decisão econômica.
6. `EntradaPDV.cliente_id` é identificador legado inteiro. O ledger canônico exige `cliente_id` de `crm_clientes_v1` scoped por tenant/unidade.
7. A ponte oficial já existe em `crm_cliente_legado_v1`; não é permitido usar o ID legado diretamente no ledger.

## Target F13-B

### Fronteira transacional

`RecursosTransacionaisV1` passa a expor os recursos CRM comerciais ligados à mesma `Session`:

- leitor de clientes CRM;
- resolução explícita cliente legado → cliente CRM;
- leitura vigente de consentimentos;
- repositório canônico de cashback.

Nenhum desses recursos cria `Session`, `commit` ou `rollback` próprio.

### Boundary cashback/PDV

Criar boundary de aplicação responsável por:

1. resolver o mapping `legacy_cliente_id` no Active Scope;
2. falhar fechado se o mapping não existir;
3. aplicar débito de resgate no ledger canônico quando houver desconto positivo;
4. aplicar crédito de ganho de compra no ledger canônico;
5. usar chaves idempotentes estáveis derivadas da `EntradaPDV`;
6. retornar o saldo canônico resultante para a projeção de compatibilidade;
7. manter débito, crédito, venda, reconciliação e projeção dentro da mesma transação externa.

### Regularização do legado

Não haverá backfill silencioso. Se o ledger ainda não possuir movimentos para um cliente e `clientes.saldo_cashback` legado for diferente de zero, a operação falha fechado como `cashback_legacy_regularizacao_pendente`.

O saldo legado pode ser observado somente como guard de migração/consistência; nunca como saldo disponível para decisão ou como fallback econômico.

### Projeção legada

`application/pdv_legacy_projection.py` deixa de calcular saldo econômico. Ela poderá:

- persistir venda legada;
- manter marcadores de efeitos de compatibilidade;
- atualizar `total_gasto`, `ultima_compra` e estado legado;
- escrever `clientes.saldo_cashback` somente com o saldo final recebido da autoridade canônica.

Ela não poderá:

- validar saldo disponível;
- debitar saldo por cálculo próprio;
- creditar 5% por cálculo próprio;
- usar o saldo legado como fallback.

## Idempotência

- débito PDV: `<entrada.idempotency_key>:cashback_use`;
- crédito PDV: `<entrada.idempotency_key>:cashback_gain`.

A referência econômica será o `pedido_id` canônico e a origem será `pdv_compra`.

Replay deve produzir os mesmos movimentos sem duplicação.

## Fail-closed

A finalização deve abortar a transação se ocorrer qualquer uma destas condições:

- cliente legado sem mapping CRM;
- mapping fora do tenant/unidade;
- saldo canônico insuficiente;
- saldo legado histórico não regularizado antes do primeiro movimento canônico;
- conflito de idempotência;
- conflito de concorrência.

## Fora do escopo desta subfase

- alteração de `app.py`;
- crédito manual pela UI;
- cutover de leitura da UI;
- marketing/WhatsApp;
- remoção final dos blockers do readiness;
- merge/deploy/produção.

Esses itens permanecem para F13-C/F13-D conforme o inventário mestre da Fase 13.

## Gate mínimo F13-B

- Ruff e mypy nos novos boundaries/adapters;
- testes de mapping obrigatório;
- crédito de compra canônico;
- resgate + crédito na mesma transação;
- replay idempotente;
- saldo insuficiente fail-closed;
- legado não regularizado fail-closed;
- projeção legada igual ao saldo canônico;
- rollback atômico quando projeção/finalização falha;
- suíte Python completa;
- matriz de CI contra `main` antes de certificação.
