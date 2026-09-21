# WP-031K — Cognitive Fiscal — Certification

**Status:** CERTIFIED_INTERNAL
**Data:** 20/09/2026
**Repositório:** `faabio3131/fm-ai-platform`
**Branch:** `feat/web-parity-v1-total-original-migration`
**PR:** #118 — OPEN/DRAFT
**HEAD funcional certificado:** `8ee77732f7f1cba5da8403872217bd2ee2cad986`
**Workflow:** `WP-031K Cognitive Fiscal`
**Run:** `35553683984` — SUCCESS
**Matriz do HEAD:** 27/27 workflows SUCCESS

## Escopo certificado

O WP-031K integrou o Fiscal V1 ao Core canônico existente em `core/gerente_ia`, sem criar segundo Core ou autoridade fiscal paralela.

A capacidade `consultar_fiscal` é exclusivamente de consulta e:

- exige `GERENTE_IA_CONSULTAR` e `FISCAL_VISUALIZAR`;
- deriva tenant e unidade do `ContextoExecucao`;
- usa ambiente apenas como filtro explícito de leitura;
- consulta projeções determinísticas de fiscal, inbound, intake, procurement, financeiro/tributário e Control Plane;
- não lê conteúdo bruto do archive/XML;
- não acessa Secret Store nem valor de segredo;
- identifica proveniência/autoridade nos registros;
- representa recomendações como recomendação, com `execucao=nao_executada`;
- não emite, cancela, inutiliza, manifesta, movimenta estoque, paga, decide crédito tributário ou altera configuração/certificado.

## Evidências

No gate dedicado:

- frozen Fiscal V1 baseline: PASS;
- compile: PASS;
- Ruff: PASS;
- mypy: PASS;
- migration manifest: PASS;
- schema baseline: PASS — 100 tabelas, SHA-256 `6724f5e6a6b558ac82f9f88e4c964978fb10b0a94eb81e75ee085a76ca6cb645`;
- WP-031K targeted: 4 passed;
- Gerente IA regression: 42 passed, 2 warnings;
- Fiscal regression: 105 passed, 5 warnings;
- Security regression: 69 passed;
- Full Python regression: 1637 passed, 5 skipped, 102 warnings;
- diff whitespace: PASS.

A primeira implementação revelou regressões de compatibilidade em fakes legados e tipagem transitiva. Elas foram corrigidas sem reduzir testes nem escopo. O HEAD acima foi recertificado integralmente em 27/27 workflows SUCCESS.

## Limites preservados

Esta certificação é interna. Não declara:

- homologação SEFAZ/provider;
- certificado real aprovado;
- CSC real;
- NFC-e/NF-e/NFS-e real homologada;
- produção fiscal;
- `PRODUCTION_APPROVED`.

## Próximo bloco

`WP-031L — Regression / Channel Parity`.

O WP-031 permanece `PENDING` até WP-031L e WP-031 Master Gate serem certificados.
