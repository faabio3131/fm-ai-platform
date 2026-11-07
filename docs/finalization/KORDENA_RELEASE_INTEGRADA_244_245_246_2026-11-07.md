# Kordena V1 — release integrada do piloto (PRs #244, #245 e #246)

Data: 2026-11-07 (America/Sao_Paulo). **Este documento registra a composição, não certifica produção nem transações reais.**

## Baseline autoritativo e proveniência

- Repositório: `faabio3131/fm-ai-platform`.
- Base `production` verificada: `f35dfd02a907f569b4e64b5b9aebb20467c97191`.
- PR #244: `0f73e97a60872e980e54a84c531d22f89f096aa3` — Pix PagBank PDV, cartão terminal/checkout hospedado, canal 99Food governado; 10/10 workflows verdes na origem.
- PR #245: `1e3ba92e19a8159f13b335e3eb1776d77804822a` — NFCore S2S e tradução da intenção fiscal da venda; 16/16 workflows verdes na origem.
- PR #246: `cf511a64801cbd7cc5005a4db65a03093f595223` — cadastro multigateway e conta bancária no cofre, interface administrativa; 8/8 workflows verdes na origem.

## Reconciliação de conflitos

Foram auditados os arquivos alterados nas três PRs contra a mesma base. Único path compartilhado: `core/integracoes/catalogo.py`. Sua resolução deve reunir **simultaneamente** o registro 99Food, `fiscal.documentos/nfcore`, o novo modelo de `runtime_operacional/credenciais_opcionais`, novos gateways de cadastro e as entradas pré-existentes de SEFAZ, PagBank Pix, Mercado Pago Pix, iFood e Keeta. Demais arquivos são exclusivos de uma das três PRs.

Teste de fitness integrado: `tests/unit/integracoes/test_release_244_245_246_combinado.py`. **Os gates da candidata consolidada devem ser executados no SHA exato; aprovação das PRs independentes não é aprovação da combinação.**

## Configurações externas e limites operacionais

| Capacidade | Construção interna desta release | Ação externa posterior |
|---|---|---|
| PDV Pix PagBank | Cobrança real por adapter, código e consulta PSP | Token, conta, webhooks, transação sandbox/produção autorizada |
| Cartão PagBank hospedado | Checkout sem PAN/CVV no Kordena, consulta PSP | Contrato e meios habilitados no provedor, simulação oficial |
| Cartão terminal presencial | Registro de autorização/NSU atestado pelo operador | Terminal real e comprovante aprovado |
| 99Food | Cadastro, painel e transporte de parceiro governado | Contrato de integração/credenciais/rotas oficiais para adapter operacional |
| NFCore fiscal | Gateway S2S, capability gate, contrato de emissão e eventos | NFCore em estado homologado, credenciais, certificados e SEFAZ/município |
| Contas bancárias e outros PSPs | Cadastro no Vault, por estabelecimento; indica 'apenas cadastro' | Adapters transacionais distintos exigidos antes de movimentar dinheiro |

**STOP de produção:** sem CI da candidata 100% verde, sem backup recuperável, sem healthchecks, sem compatibilidade de schema e sem autorização de publicação, não fazer merge na branch `production` (deploy automático pela Contabo). Durante implantação, não ativar 99Food, NFCore em produção nem PSPs sem documentação/credenciais homologadas; nunca marcar uma cobrança como paga por redirecionamento do browser.

## Procedimento de release

1. Auditar head de `production` e preservar todo commit concorrente.
2. Criar PR candidata, aguardar todos os workflows `SUCCESS` no SHA exato.
3. Executar merge com compare-and-swap do HEAD e verificar novo `production`.
4. Conferir deploy automático com `/opt/fm/kordena/.deployed`, backup, log, containers e healthchecks públicos.
5. Registrar diferenças entre `CI aprovado`, `deploy confirmado` e `homologação externa pendente`.
