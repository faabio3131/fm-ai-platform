# Kordena V1 — Sequência Final Oficial de Execução

**Data de congelamento:** 18/09/2026
**Branch:** `feat/web-parity-v1-total-original-migration`
**PR:** #118
**Regra de avanço:** nenhum bloco autoriza o seguinte enquanto os gates aplicáveis não estiverem 100% verdes. Corrigir falhas causadas pelo bloco antes de avançar. Nenhum merge, deploy, force push ou V2.

## Sequência

1. **WP-008 — fechar gate**
   - Implementação Web concluída em `/garcom`.
   - Gate dedicado no HEAD `9daaacc9ef4754558ad570bd568a316367b9260d`: SUCCESS.
   - Estado canônico permanece `IMPLEMENTED_UNCERTIFIED` até certificação integral posterior.

2. **WP-018 — certificar Dashboard Financeiro / Indicadores — CONCLUÍDO**
   - CERTIFIED no SHA `b7a64b2dc5a47763a86fded903a15fd2be2cc23d`.
   - Step-up HTTP reforçado.
   - Gate integral SUCCESS; próximo bloco liberado: WP-012.

3. **WP-012 — implantar Web de Marketplaces — CONCLUÍDO**
   - CERTIFIED no SHA `e4ce2c1e2e315811425535c5ca74b5a56570050b`.
   - Gate `Web Parity WP012 Marketplaces` run `35369209616`: SUCCESS.
   - `core/marketplaces`, Central/Pedido canônicos, isolamento tenant/unidade, transaction ownership e migration `0042` preservados.
   - Homologação externa de provider continua dependente de evidência real; não é inferida pela certificação técnica interna.

4. **WP-032 — implantar Web de Notificações Internas — CONCLUÍDO**
   - Reutilizar `core/notificacoes_internas`, `application/notificacoes_internas.py` e `infra/notificacoes_internas`.
   - Escopo: destinatários, preferências e alertas administrativos.
   - Não criar inbox/feed/badge genérico fora do escopo.

5. **WP-033 — implantar Web de Auditoria / Histórico**
   - Reutilizar `core/seguranca/auditoria.py` e `infra/seguranca/auditoria_sqlalchemy.py`.
   - Consulta read-only, tenant-safe, sem exposição de segredos.
   - Proibida segunda auditoria.

6. **WP-031 — implantar Fiscal pronto**
   - Antes de qualquer código: localizar a implementação pronta e provar sua autoridade/versão.
   - Importar/implantar/integrar; não reconstruir motor fiscal.
   - Conectar ao Kordena, testar, homologar e certificar.
   - Fiscal é obrigatório para fechamento da V1.

7. **Auditoria Mestre V1 completa**
   - Reconciliar código, rotas, ledger, inventário, checklist, testes e evidências.
   - Resolver divergências documentais somente com evidência real.

8. **Gate 100% funcional**
   - Regressão integral.
   - Gates frontend/backend.
   - Smokes/E2E aplicáveis.
   - Nenhum bloqueio funcional obrigatório restante.

9. **Visual Premium final**
   - Só iniciar após todos os blocos anteriores estarem encerrados e certificados conforme aplicável.

## Estado CURRENT no congelamento

- 33 Work Packages oficiais.
- 31 `CERTIFIED`.
- 1 `IMPLEMENTED_UNCERTIFIED`: WP-008.
- 1 `PENDING`: WP-031 Fiscal (deliberadamente fora desta rodada).
- WP-008 gate de implementação: SUCCESS.
- PR #118 permanece OPEN/DRAFT e não mergeada.


## Exceção operacional do ciclo autônomo atual

Por decisão explícita do proprietário, o ciclo em execução após a certificação do WP-012 segue **WP-032 → WP-033 → Auditoria Mestre não fiscal → Gate Mestre não fiscal**. O **WP-031 Fiscal permanece PENDING e deliberadamente fora desta rodada**, assim como o **Visual Premium**. Esta exceção não remove o Fiscal da V1 final; apenas o reserva para rodada própria posterior.


## Checkpoint pré-Auditoria Mestre — 18/09/2026

- WP-032 certificado: SHA `c94d17ed85183c51ace803b5a97ecda84cbf447f`, run `35373830703` SUCCESS.
- WP-033 certificado: SHA `01d5f7695cd72ab67cb7107c13c9e004de74f3d1`, run `35376561635` SUCCESS.
- Próximo passo: Auditoria Mestre não fiscal, incluindo reavaliação do WP-008 e recuperação de evidências históricas faltantes.
