# Pagamento e consequência financeira Venda V1

## Decisão e modelo

`Pedido`, `Pagamento` e `Venda` são agregados distintos. Produção e pagamento têm
máquinas independentes: confirmar pagamento não envia pedido à cozinha e reconhecer
Venda não reserva, consome ou devolve estoque, não concede cashback e não aciona KDS.
A Venda é uma consequência de um `CriterioFinanceiro` elegível, nunca um gatilho de
efeitos operacionais.

Os contratos imutáveis são `Pagamento`, `ObrigacaoPagamento`,
`TransacaoPagamento`, `ConfirmacaoPagamento`, `EstornoPagamento`,
`CriterioFinanceiro`, `ResultadoPagamento`, `ResultadoReconhecimentoVenda` e
`ResultadoReconciliacao`. Valores novos usam `Dinheiro`/`Decimal`, moeda ISO e duas
casas; `float` aparece apenas na projeção de compatibilidade do legado, na borda.

## Obrigação, estados e métodos

A obrigação preserva o total originalmente previsto e sua versão. Confirmações
podem ser parciais e mistas, mas o total econômico líquido não supera a obrigação.
Dinheiro recebido acima do saldo produz troco; somente o saldo é confirmado como
receita. São suportados dinheiro, Pix, crédito, débito, voucher/outro, pagamento na
entrega e recebimento posterior. Os estados vêm exclusivamente da máquina do PR 5:
`nao_iniciado`, `pendente`, `aguardando_entrega`, `aguardando_fechamento`,
`parcialmente_pago`, `pago`, `falhou`, `cancelado`, `estornado_parcial` e
`estornado`.

## Transações, webhook e provedores

Transações são append-only. Correções e estornos são lançamentos compensatórios;
não há update destrutivo ou hard delete. O resumo rejeita dados PCI/segredos por
contrato e auditoria sanitizada. O adapter de provedor oferece `criar_cobranca`,
`consultar_transacao`, `normalizar_webhook` e `reconciliar`; a implementação V1 é
sandbox determinística e não faz rede. QR exibido ou cobrança pendente não confirma
pagamento. Webhooks sem assinatura validada ou sem estado financeiro confirmado são
ignorados; a chave composta de provedor/evento torna duplicatas econômicas inócuas.

## Critério, Venda e legado

Os critérios explícitos são `PAGAMENTO_CONFIRMADO`, `COMANDA_FECHADA` com saldo
resolvido e `RECEBIMENTO_POSTERIOR_AUTORIZADO`. Este último exige política,
responsável, motivo e confirmação humana; Gerente IA nunca autoriza sozinho. O
reconhecimento usa tenant, unidade, pedido, versão do critério e chave idempotente,
com unicidade lógica e persistida, para materializar exatamente uma
`VendaFinanceira`.

`AdapterVendaLegada` apenas produz, quando chamado explicitamente, os campos atuais
de `Venda` usados por dashboard/relatórios. Ele não está ligado a `app.py`, PDV,
cashback ou estoque. Não foi adicionado `pedido_id` à tabela `vendas`: o vínculo fica
em `vendas_financeiras_v1`, evitando alteração ou backfill histórico. Vendas antigas,
inclusive sem qualquer pedido, continuam válidas e legíveis.

## Concorrência, idempotência e reconciliação

O repositório in-memory executa comandos sob lock reentrante; persistência define
versão para CAS e constraints escopadas. Mesma chave/conteúdo devolve o resultado;
mesma chave/conteúdo diferente gera `conflito_idempotencia`. Confirmações concorrentes
usam `expected_version`; webhook repetido e reconhecimento concorrente materializam
uma única consequência.

A reconciliação compara obrigação, agregado, transações confirmadas, referência
externa e Venda. Ela relata, sem autocorreção crítica: confirmação sem obrigação,
pagamento sem confirmação, valor divergente, Venda ausente e transação externa
desconhecida. Ajustes exigem novo comando idempotente e auditado.

## Estorno e recebimento posterior

Estorno parcial/integral exige valor, motivo, permissão/alçada, correlação e
auditoria. A transação original e a Venda original permanecem; eventual documento
fiscal/ajuste financeiro completo é intenção futura, não inventada aqui. Recebimento
posterior mantém a obrigação rastreável e somente gera critério com responsável
autorizado, justificativa e confirmação humana.

## Segurança, eventos e auditoria

Todas as buscas e mutações usam `(tenant_id, unidade_id, id)`, com resposta uniforme
fora do escopo. RBAC é deny-by-default: Caixa registra/confirma conforme permissão;
Financeiro reconcilia/estorna; Gerente aprova exceções conforme alçada; identidade
reconciliadora precisa ser `system` explícita e ter motivo. Gerente IA consulta ou
solicita, mas não confirma, autoriza posterior nem executa estorno.

Eventos usam o envelope do PR 3 e carregam IDs, agregado/versão, tenant/unidade,
pedido, correlação, causação, idempotência, UTC e payload mínimo. Auditorias registram
ator/papel, ação, antes/depois, valor, método, pedido/pagamento/critério, motivo e
escopo, sem segredo ou PCI.

## Persistência, migration e rollback

A migration aditiva cria `pagamentos_v1`, `transacoes_pagamento_v1`,
`obrigacoes_pagamento_v1`, `criterios_financeiros_v1` e
`vendas_financeiras_v1`, com `Numeric(14,2)`, índices, FKs restritivas e unicidades
escopadas. Ela recebe `Engine` explícita, aceita apenas SQLite in-memory ou arquivo
claramente de teste e recusa `banco_erp_local.db` e bancos não marcados. O downgrade
remove somente essas tabelas. Migration real não é executada por esta entrega.

`RepositorioPagamentosSQLAlchemy` implementa obrigação, agregado Pagamento com CAS,
transação append-only, critério imutável e Venda financeira exatamente uma vez. Não
expõe delete nem update retroativo de transação, critério ou Venda. Todas as queries
recebem tenant e unidade. O commit pertence ao unit of work chamador, de modo que uma
falha de CAS ou constraint possa reverter também os lançamentos do comando.

SQLite serializa escritores e não representa toda a concorrência de um SGBD de
produção. Os testes usam sessões independentes, sem `sleep`, e provam no banco as
constraints de evento externo/Venda e o `UPDATE ... WHERE versao = esperada` do CAS.
O adapter não depende de comportamento específico de lock para preservar as
invariantes.

## Flags, compatibilidade, riscos e não escopo

`payments_v1_enabled`, `sales_from_orders_enabled` e
`legacy_sale_adapter_enabled` têm default `OFF`. A camada permanece dormente: não há
mudança em `app.py`, PDV, dashboard, Mica, KDS, marketplace, adquirente ou banco real.
O rollout/canary pertence ao PR 8.

Riscos restantes: a materialização ORM do legado e ajustes fiscais compensatórios
precisam de decisão no vertical slice; reconciliação V1 só detecta, não corrige. O
rollback é desativar flags (já off) e, somente em banco efêmero/teste, executar o
downgrade das tabelas novas.
