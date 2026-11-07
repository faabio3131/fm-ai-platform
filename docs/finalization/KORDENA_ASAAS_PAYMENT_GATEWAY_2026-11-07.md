# Kordena V1 — Asaas Pix + cartão hospedado: fechamento interno de desenvolvimento (07/11/2026)

## Autoridade e escopo
- Base: \`production@d5c3af116ff51d99d83b758dc0aecb1edbe2323d\` (PR #247, Contabo).
- Construção em branch isolada: \`feat/kordena-payment-gateways-operacionais-20261107\`; **não mesclada, não implantada**.
- Este bloco incorpora **integração transacional Asaas**, não apenas cadastro; **não** declara homologação junto ao Asaas, dinheiro real, nem 100% de todos os provedores.
- O Kordena não processa PAN/CVV: cartão é direcionado à URL de fatura hospedada pela instituição; Pix recebe payload/QR do PSP.
- Authoritative payment ledger/UoW continua em Kordena. Consulta Asaas via API autenticada, não redirecionamento ou webhook isolado, é prova de pagamento.

## Capacidade implementada
1. \`core/pagamentos/asaas.py\` — adapter REST V3 sandbox/prod, cliente, cobrança Pix/cartão, QR, consulta, validação exata valor+referência+tipo, webhook token comparado em tempo constante, solicitação de estorno com status conservador.
2. \`infra/pagamentos/asaas_runtime.py\` — resolve configuração por serviço específico (pix/cartão), tenant/unidade e credencial via Vault, exige evidência de homologação para produção.
3. \`application/pdv_asaas.py\` — orquestra cobrança/consulta, ID externo determinístico e vínculo durável, transação UoW, RBAC, idempotência, liquidação com finalizador único de venda/estoque, reconciliação de estorno pelo status GET, webhook como gatilho autenticado para GET.
4. \`http_api/pdv.py\`, \`http_api/app.py\` — seleção de provedor por venda, rotas Asaas autenticadas por caixa e webhook anônimo com token confiável e escopo derivado de transação previamente registrada.
5. \`core/integracoes/catalogo.py\` — Asaas Pix e cartão com runtime real e credenciais obrigatórias API key + token webhook; mantém os demais apenas cadastráveis quando não têm adapter.
6. \`web/src/features/pdv/\` — seleção PagBank/Asaas, início Pix/cartão, QR, URL hospedada, consulta com retorno do provedor, sem assumir pagamento no navegador.
7. \`application/checkout.py\` — protege replays de checkout contra mudança de método ou PSP usando mesma idempotency key.

## Fontes de contrato oficial
- https://docs.asaas.com/reference/criar-nova-cobranca
- https://docs.asaas.com/reference/recuperar-uma-unica-cobranca
- https://docs.asaas.com/docs/visao-geral
- https://docs.asaas.com/docs/pix
- https://docs.asaas.com/docs/webhooks

## Matriz de testes
- \`tests/unit/payments/test_asaas_gateway_v1.py\`: HTTPX transport fake, criação, replay, validação, QR, URL, evento, estorno solicitado.
- \`tests/api/test_pdv_asaas_http_contract.py\`: API real FastAPI + UoW/ledger SQLAlchemy efêmero, Pix/cartão, pendente→pago, repeat, webhook fraudado, 2 unidades, estorno confirmado.
- \`tests/api/test_pdv_http_contract.py\` e \`tests/unit/integracoes/test_cadastro_financeiro_multigateway_v1.py\`: regressões de checkout, estoque e catálogo.
- Certificação final exige registrar outputs exatos de pytest, Ruff, TypeScript, lint, build e CI no SHA candidato antes do merge.

## Dependências externas exclusivamente reais
- Conta Asaas e aprovação comercial, sandbox oficial, API key por estabelecimento/unidade, webhook token e URL \`https://api.kordenaia.com.br/webhooks/asaas\`.
- Ambiente produtivo somente após sandbox/evidência de homologação, proteção de credenciais Vault, testes físicos/autorização para dinheiro real; não ativar automaticamente.
- Configuração Asaas por serviço \`pagamentos.pix\` e \`pagamentos.cartao\`, com referências distintas no Vault se necessário. Sem migração de schema.
- Verificar versões/contratos oficiais e comportamento de chargeback, parcelas e possíveis divergências de status durante homologação.

## Não confundir conclusão de um provedor com conclusão de todos
- PicPay, Pagar.me, Efí, Mercado Pago cartão, Stone, Cielo, Rede, Getnet, SumUp, InfinitePay e 99Food têm gates independentes de implementação + E2E + contrato real. Nenhuma interface deve afirmar que cadastro implica captura financeira.
- Não realizar transações reais, merge/deploy/segredo para esta PR antes da certificação e autorização específica de produção.
