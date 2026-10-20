# WP-008 — EVIDÊNCIA DE IMPLEMENTAÇÃO

**Produto:** Kordena V1
**Work Package:** WP-008 — Atendimento do Garçom mobile/tablet
**Estado:** IMPLEMENTED_UNCERTIFIED
**Data:** 18/09/2026
**PR:** #118
**Branch:** `feat/web-parity-v1-total-original-migration`
**HEAD inicial:** `50adcc6021f39a6ff99ce7b057defe5ec205c66f`
**SHA de implementação testado:** `3c59dff6e4460d743f50214c6e79cdc886a2fdd5`

## Escopo implementado

O WP-008 foi implementado sem criar segunda autoridade para Garçom, Salão, Comandas, Pedidos, KDS, Pagamentos, autenticação, tenant ou unidade.

A superfície Web utiliza sessão operacional existente e exige modo de autenticação por sessão no router do Garçom. O escopo de tenant e unidade é derivado da identidade da sessão. O fluxo reutiliza `AplicacaoGarcomV1`, `ServicoGarcom`, `AplicacaoSalaoV1`, o motor canônico de pagamentos, o repositório de Salão/KDS e `ConfiguracaoEstabelecimento`.

Foram implementados:

- Garçom Web touch-first em `/garcom`;
- abertura e continuidade da mesma comanda durante a visita;
- pedidos sucessivos pela autoridade existente do Salão;
- solicitação de conta e retomada de consumo antes da consolidação;
- demonstrativo com consumo, couvert, taxa de serviço e desconto separados;
- inclusão ou recusa da taxa de serviço, sem converter recusa em desconto;
- configuração por unidade dos modos `na_mesa`, `no_caixa` e `hibrido`;
- configuração simples por unidade do couvert artístico dentro da configuração canônica existente;
- controle de couvert na primeira superfície do Caixa/PDV, protegido por `configuracao.alterar`;
- snapshot dos componentes aplicados no fechamento, preservando histórico;
- escolha do destino de recebimento sem duplicar comanda;
- divisão e múltiplos métodos por meio da autoridade canônica;
- criação, confirmação e aplicação de pagamentos pelo motor financeiro existente;
- bloqueio de fechamento enquanto houver saldo;
- verificação server-side de produções KDS ativas antes do fechamento;
- fechamento canônico e liberação da mesa após quitação;
- versionamento otimista e idempotência nos comandos críticos.

## Evidência de testes

Workflow dedicado: **Web Parity WP008 Implementation Gates**
Run: **35305972483**
SHA: `3c59dff6e4460d743f50214c6e79cdc886a2fdd5`

Resultados:

- compilação Python da superfície WP-008: **SUCCESS**;
- Ruff WP-008: **SUCCESS**;
- mypy: **SUCCESS — no issues found in 5 source files**;
- matriz direcionada WP-008/Garçom/Salão/Auth/PDV: **59 passed, 0 failed, 2 warnings**;
- regressão Python completa: **1516 passed, 0 failed, 5 skipped, 99 warnings**;
- instalação Web: **SUCCESS**;
- ESLint dos arquivos WP-008: **SUCCESS**;
- TypeScript `tsc --noEmit`: **SUCCESS**;
- teste Web relacionado: **SUCCESS**;
- Next production build: **SUCCESS**;
- `git diff --check`: **SUCCESS**.

Os skips já pertencem à suíte integral existente; nenhum skip/xfail foi criado para mascarar falha do WP-008.

## Falhas encontradas e corrigidas durante a execução

1. Ruff detectou acessos dinâmicos desnecessários no novo boundary HTTP. Corrigido por tipagem concreta.
2. Ruff detectou quatro problemas menores de estilo no compositor de fechamento. Corrigidos.
3. Dois testes novos validavam a mensagem genérica de `ErroSalao` em vez do código estruturado. Corrigidos para validar `exc.codigo`.
4. A regressão completa detectou inferência inválida de response model do FastAPI nas rotas com `dict | JSONResponse`. Corrigido com `response_model=None` nos decorators correspondentes. Após a correção, toda a regressão passou.

## Governança e pendências

- PR #118 deve permanecer **OPEN/DRAFT**.
- Nenhum merge foi executado.
- Nenhum deploy foi executado.
- A `main` não foi alterada.
- Nenhum force push ou rebase destrutivo foi executado.
- WP-008 **não está CERTIFIED**. A certificação integral independente permanece para gate posterior.
- Existe uma inconsistência histórica pré-existente no canonical state ledger: WP-001 a WP-007 aparecem como `CERTIFIED` sem os campos de evidência hoje exigidos pelo validador. Essa pendência não foi alterada no WP-008 para evitar expansão de escopo e fabricação de evidência histórica.

## Estado de saída

`WP-008 = IMPLEMENTED_UNCERTIFIED`

A implementação possui código, commit remoto e evidência real de testes. A certificação posterior não foi antecipada.
