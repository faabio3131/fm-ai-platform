# Fase 12 — Inventário Current → Target — Marketplaces homologados V1

Baseline certificado: `main @ b362ab9ac2f570a09fb64708522be865f06ca2cb`.

## Autoridade e objetivo

A Fase 12 segue o programa de recuperação e tem como objetivo homologar marketplaces conforme disponibilidade oficial, preservando integralmente as fases já certificadas.

Esta fase é de **cutover/composição/homologação**, não de reescrita do domínio de marketplaces.

## CURRENT

Patrimônio já existente e preservado:

- framework de `MarketplaceAdapter` e `RegistroAdaptersMarketplace`;
- `ServicoMarketplaces` com inbox/outbox, idempotência, retry, DLQ e reconciliação;
- `IfoodHttpAdapter` com OAuth, polling, ACK, consulta e comandos sobre portas HTTP/segredos injetáveis;
- `IfoodSandboxAdapter` e E2E sandbox;
- adapters 99Food e Keeta protegidos por `TransporteParceiroNormalizado` e `contrato_verificado`;
- feature flags/readiness fail-closed do runtime.

Readiness de partida:

- status de marketplaces: `EXTERNAL_HOMOLOGATION_PENDING`;
- blocker interno: `ifood_transport_not_composed_for_real_network`;
- blocker externo: `ifood_99food_keeta_partner_homologation_pending`;
- nenhuma evidência física/real deve ser declarada sem credencial, autorização e execução verificável do parceiro.

## TARGET

### F12-A — composição real iFood, pré-homologação

1. fornecer transporte HTTP real sobre a porta já existente;
2. manter credenciais atrás de `PortaSegredosIfood`, sem segredo hardcoded ou logado;
3. reutilizar as flags/readiness existentes e falhar fechado fora de teste;
4. compor `IfoodHttpAdapter` no `RegistroAdaptersMarketplace` somente quando o adapter real estiver explicitamente habilitado;
5. preservar sandbox e testes sem rede externa;
6. adicionar testes de contrato para transporte, erros transitórios e composição fail-closed;
7. após gates verdes, remover apenas o blocker interno de código do readiness.

### F12-B/F12-C — 99Food e Keeta

Permanecem atrás do contrato parceiro normalizado até documentação/credenciais oficiais e homologação verificável. Não inventar endpoints, autenticação ou payloads.

## Não objetivos

- reescrever `ServicoMarketplaces`, inbox/outbox ou domínio de pedidos;
- colocar credenciais no repositório;
- executar internet real nos testes de CI;
- marcar parceiro como homologado por simulação;
- alterar `main`, fazer merge, deploy ou produção sem o gate/autorização humana aplicável.

## Gates da F12-A

- lint/compile/typecheck aplicáveis;
- testes unitários do transporte/composição;
- E2E sandbox iFood existente;
- regressão dos workflows obrigatórios do repositório;
- readiness deve manter `EXTERNAL_HOMOLOGATION_PENDING` enquanto o blocker externo existir;
- homologação física só poderá ser registrada com evidência real do parceiro.

## Critério de promoção

A F12-A fecha o blocker interno somente quando o adapter iFood estiver composto com transporte de rede real, protegido por configuração fail-closed, e todos os gates de código estiverem verdes. Isso **não** equivale à homologação externa do iFood/99Food/Keeta.