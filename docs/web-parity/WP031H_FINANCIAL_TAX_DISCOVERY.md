# WP-031H — Financial / Tax Bridge — Discovery e decisão

**Data:** 20/09/2026  
**PR:** #118 — OPEN/DRAFT  
**Branch:** `feat/web-parity-v1-total-original-migration`

## CURRENT localizado

A discovery dirigida confirmou que `core/pagamentos` já é a autoridade financeira canônica da Kordena V1. Ela contém:

- obrigação de pagamento, pagamento, transação e estorno;
- critério financeiro e reconhecimento de venda;
- idempotência, compare-and-swap, eventos e auditoria;
- persistência SQLAlchemy em `PaymentsBase`;
- projeções administrativas que leem fontes canônicas sem assumir autoridade.

O fluxo existente representa principalmente valores a receber de vendas. Reutilizá-lo como se uma compra de fornecedor fosse recebimento de cliente inverteria a natureza financeira e poderia criar pagamento indevido.

## Decisão

O WP-031H estende a mesma autoridade `core/pagamentos` com um subdomínio explícito de contas a pagar fiscal, sem criar outro ledger financeiro:

1. `ObrigacaoCompraFiscal`: obrigação a pagar originada por recebimento físico autorizado;
2. `AjusteObrigacaoCompra`: trilha append-only para devolução e cancelamento;
3. `DecisaoCreditoTributario`: decisão determinística, versionada e auditável;
4. `ResumoFinanceiroFiscal`: projeção reconciliável, nunca autoridade.

Nenhum `Pagamento`, liquidação ou transferência é criado automaticamente.

## Regras congeladas

- NF-e/DF-e isolado não cria obrigação.
- Somente recebimento `PARCIAL` ou `CONCLUIDO`, sem divergência e na partição `PRODUCTION`, autoriza obrigação.
- Recebimento parcial reconhece apenas os itens fisicamente aceitos.
- O recebimento final reconcilia o total documental descontando obrigações parciais anteriores.
- Uma obrigação é única por `tenant + unidade + ambiente + recebimento`.
- Replay igual retorna o mesmo resultado; replay divergente falha fechado.
- Devolução/cancelamento ajusta o saldo por registro append-only e preserva o valor original.
- Pagamento e liquidação permanecem operações financeiras separadas e não são executados por este bridge.
- Crédito tributário sem regra explícita vigente resulta em `BLOQUEADO` e valor zero.
- Regra explícita deve declarar identidade, versão, vigência, tributo, CFOPs, CSTs e alíquota máxima.
- Não existe fallback “imposto destacado = crédito”.
- Homologação nunca contamina obrigações operacionais.

## Persistência

Migration aditiva `0048_fiscal_financial_tax_bridge_v1`:

- `obrigacoes_compra_fiscal_v1`;
- `ajustes_obrigacao_compra_v1`;
- `decisoes_credito_tributario_v1`.

As três tabelas pertencem a `PaymentsBase`, são particionadas por tenant, unidade e ambiente e possuem constraints de idempotência.

## Segurança e rastreabilidade

- registro/ajuste exige `financeiro.compras.registrar`;
- decisão tributária exige `financeiro.tributos.decidir`;
- o papel Financeiro recebe ambas as capacidades;
- cada obrigação referencia fornecedor, pedido, recebimento, inbound e chave fiscal;
- decisões guardam regra, versão, ator, timestamp e correlation id;
- projeções expõem IDs de fonte para reconciliação do Core e dashboards.

## Fora do bloco

Signer, certificado, provider/SEFAZ real, Web/UX, pagamento automático, escrituração oficial, Visual Premium, merge e deploy permanecem fora do WP-031H.
