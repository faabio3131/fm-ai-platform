# Vertical slice PDV V1 — Pedido, Pagamento e Venda

## Estado anterior

O checkout Streamlit valida o formulário e o estoque, cria uma única `Venda`,
reduz `Insumo.saldo_atual`, debita/credita cashback e confirma tudo em um commit.
O dashboard lê exclusivamente `Venda`. Esse caminho continua sendo a autoridade
com flags desligadas; o core V1 não importa `app.py`.

## Roteamento e matriz de flags

| modo configurado | orders shadow | orders authoritative | payments/sales/adapter | contexto/coorte confiável | decisão |
|---|---:|---:|---:|---:|---|
| LEGACY | falso | falso | falso | irrelevante | legado |
| SHADOW | verdadeiro | falso | falso | tenant/unidade coincidem | legado e, depois do commit, Pedido sombra |
| CANARY | qualquer | verdadeiro | todos verdadeiros | tenant, unidade e terminal permitidos | autoritativo |
| CANARY incompleto | qualquer | qualquer | algum falso | qualquer | falha fechada |

`stock_ledger_authoritative` permanece falso. Se verdadeiro, o primeiro canary
falha fechado: somente a baixa legada é econômica neste Gate. Tenant, unidade e
flags vêm de `PDVRolloutConfig` server-side, nunca do formulário. Como ainda não
há identidade operacional de produção completa, produção fica default-off. O
canary usa somente `ContextoExecucao` explicitamente confiável de teste.

## Fluxos

### LEGACY

Preserva Venda, estoque e cashback legados exatamente uma vez, sem exigir tabela
V1. Cashback total (saldo financeiro zero) faz fallback seguro para este fluxo,
com motivo `saldo_zero_financeiro_nao_modelado`.

### SHADOW

O legado confirma primeiro. Uma transação separada cria o snapshot de Pedido
(IDs `legacy:produto:<id>` e `legacy:cliente:<id>`). A sombra não cria pagamento,
VendaFinanceira, produção/KDS, estoque ou cashback. Falha da segunda transação
gera reconciliação `reparo_necessario` e nunca desfaz a compra.

### AUTHORITATIVE_CANARY

Pedido nasce por factory em `RASCUNHO`, passa pela máquina normativa para
`AGUARDANDO_CONFIRMACAO` e `CONFIRMADO`, com CAS e evento a cada persistência.
Então reutiliza os casos de uso financeiros do PR7: obrigação, confirmação,
critério e VendaFinanceira. Uma porta de compatibilidade materializa uma única
Venda legada, que continua sendo a única fonte do dashboard. O UoW superior
confirma Pedido, pagamento, VendaFinanceira, link, Venda, estoque, cashback,
efeitos e reconciliação em conjunto; qualquer exceção antes do commit faz
rollback integral.

Dinheiro confirma apenas o total devido e calcula troco sobre o recebido. Cartão
presencial exige confirmação manual explícita e auditada do Caixa. PIX sandbox
pode ser determinístico. Em produção, exibir QR não confirma: sem webhook válido
o pagamento fica pendente, sem Venda, baixa ou cashback. Não há gateway ou
webhook HTTP novo neste PR.

## Idempotência, concorrência e efeitos

A chave estável é `pdv:<terminal>:<checkout>`; sufixos identificam Pedido,
transições, pagamento, confirmação, Venda e efeitos. Constraints por
tenant/unidade/pedido/tipo impedem dupla Venda, baixa e cashback, inclusive em
retry, duplo clique e workers concorrentes. O commit pertence ao UoW; adapters
não confirmam isoladamente no canary.

As tabelas aditivas são `pdv_efeitos_compat_v1`,
`pdv_venda_legada_links_v1` e `pdv_reconciliacoes_v1`. A migration aceita apenas
Engine SQLite explicitamente temporária/de teste, não faz backfill e seu
downgrade remove somente essas tabelas. Nunca é aplicada automaticamente ao
`banco_erp_local.db`.

## Reconciliação, observabilidade e rollback

O relatório registra modo, IDs, valores, estratégia de estoque, cashback,
status e divergências. Detecta Pedido sem Venda, VendaFinanceira sem Venda
legada, quantidade de Vendas/baixas, cashback duplicado e valores divergentes.
Divergência crítica não é autocorrigida. Contadores podem ser derivados por
modo/status/motivo sem PII ou tokens: shadow sucesso/falha, fallback, retry,
rollback e duplicidade bloqueada.

## Implementação concreta

`app.py` é a composition root: mantém o checkout e seus widgets, obtém a coorte
somente do loader server-side, conserva `pdv_checkout_id` entre reruns e injeta
as classes ORM legadas no adapter. `SQLAlchemyPDVUnitOfWork` entrega a mesma
`Session` aos repositórios de Pedido, Pagamento, compatibilidade, Venda, estoque
e cashback. Há apenas um commit no canary; `flush` materializa IDs e qualquer
falha até `before_commit` provoca rollback.

O executor canary persiste o Pedido rascunho, executa as duas transições pela
máquina real, adapta e persiste os dois eventos, e chama diretamente os quatro
casos de uso do PR7. Depois persiste critério, VendaFinanceira, Venda legada,
link, efeitos e reconciliação. O adapter legado consulta o ledger de efeitos
antes de Venda, estoque e cada efeito de cashback. A baixa usa exclusivamente
`FichaTecnica` e `Insumo.saldo_atual`.

No shadow, a sessão legada confirma antes de uma segunda sessão criar Pedido e
reconciliação. Se a sombra falhar, uma terceira transação curta registra
`reparo_necessario`. No PIX de produção sem confirmação autenticada, somente
Pedido, obrigação e Pagamento pendente são confirmados; não existem critério
elegível, Vendas, baixa ou cashback.

Os testes concorrentes usam duas sessões e uma barreira, sem espera temporal.
SQLite pode recusar um dos writers em vez de serializá-lo; em ambos os casos,
constraints e CAS deixam um único conjunto econômico persistido.

Rollback operacional é desligar `orders_authoritative` (e as flags financeiras):
novos checkouts voltam ao legado; dados V1 existentes permanecem legíveis.

## E2E e rollout

O servidor canary deve usar `FM_AI_TEST_MODE=1`, banco em
`.tmp/fm-ai-playwright/`, tenant/unidade/terminal fixos e configuração server-side.
Primeiro validar shadow, depois coorte canary mínima, reconciliar e ampliar. Não
há controle de flags na UI.

## Riscos, dívida e não escopo

A autenticação operacional real e obrigação de valor zero continuam pendentes.
Também ficam fora: estoque ledger autoritativo, KDS/Central de Pedidos, mesas,
garçom, delivery/marketplaces, Mica V2, gateway/webhook real, dashboard novo,
redesign e voz. Pagamento e produção permanecem independentes; Pagamento e Venda
não baixam estoque, e VendaFinanceira não concede cashback.
