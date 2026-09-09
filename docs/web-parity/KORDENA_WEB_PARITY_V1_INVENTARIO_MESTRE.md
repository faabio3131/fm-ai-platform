# Kordena V1 - Inventario Mestre de Paridade Web (WEB-PARITY-V1)

**Baseline auditada:** `main @ 5a17b0c8a1cb6dad576ce5b089166748b138900c`  
**Data:** 08/09/2026  
**Versao do inventario:** 2.1 - STOP WP-023: bloqueador preexistente de unidade padrão
**Status:** DOCUMENTO MESTRE DE EXECUCAO

## 1. Regra constitucional deste inventario
Uma capacidade so pode ser marcada como **MIGRADO** quando a cadeia necessaria estiver comprovada: dominio/core preservado, application/infra utilizavel, contrato HTTP Web adequado, interface Next.js, isolamento tenant/unidade + RBAC/step-up quando aplicavel e teste suficiente. Existir no backend ou ter E2E legado **nao** significa estar migrado para a nova Web.

## 2. Diagnostico executivo
- Capacidades inventariadas: **33**.
- Totalmente migradas: **9** (27.3% das linhas inventariadas, contagem nao ponderada).
- PARCIAL: **9**.
- IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO: **3** (WP-013, WP-020 e WP-022).
- GAP WEB: **0**.
- GAP HTTP/WEB: **9**.
- GAP HTTP/WEB/PÚBLICO: **1** (WP-030, obrigatória para V1.0).
- GAP HTTP/WEB ADMINISTRATIVO: **1** (WP-032, obrigatória para V1.0).
- BACKLOG FUTURO: **1** (WP-031, fora da migração conservativa Web V1 atual).
- A VERIFICAR: **0**.
- A rota `/` usa Home/Dashboard comercial real dentro do Shell Corporativo Unificado; o antigo harness tecnico permanece em `/admin/system-health`.
- A Central de Pedidos omnichannel esta certificada na nova Web em `/pedidos`, com sessao assinada, RBAC, fila unificada, detalhe, financeiro, timeline e mutacao governada.
- Visual Premium permanece bloqueado ate a paridade funcional Web da V1 atingir 100% das capacidades obrigatorias.

## 3. O que foi migrado
- **WP-001 - Login / SSO corporativo**: /login.
- **WP-002 - Escopo tenant/unidade + troca de unidade**: sessao assinada + seletor no Shell.
- **WP-003 - Roteamento por perfil e permissao**: navegacao corporativa central filtrada por RBAC.
- **WP-004 - Home / Dashboard / Shell corporativo**: Shell persistente + dashboard real em `/`.
- **WP-005 - PDV Touch**: /pdv.
- **WP-006 - Salao / Mesas / Comandas**: /salao.
- **WP-007 - KDS / Cozinha**: /kds.
- **WP-009 - Central de Pedidos omnichannel**: /pedidos.
- **WP-021 - Step-up administrativo / reautenticacao**: Guard de /admin.

## 4. Matriz mestre de paridade

| ID | Capacidade | Evidencia backend/legado | HTTP atual | Next.js atual | Status | Proxima acao obrigatoria |
|---|---|---|---|---|---|---|
| WP-001 | Login / SSO corporativo | http_api/auth.py; web/src/features/auth | Contrato dedicado e cookie assinado | /login | MIGRADO | Preservar e incluir no Smoke Mestre. |
| WP-002 | Escopo tenant/unidade + troca de unidade | http_api/auth.py; operational_auth.py; auth feature | Sessao assinada governa tenant/unidade | Seletor/status no Shell | MIGRADO | Preservar em todos os novos modulos e fixtures. |
| WP-003 | Roteamento por perfil e permissao | Seguranca/RBAC + guards Web + module registry | Sessao e permissoes governam a superficie Web | Shell central filtra navegacao por permissao | MIGRADO | Preservar o registry como fonte unica para novos modulos e testes. |
| WP-004 | Home / Dashboard / Shell corporativo | UnifiedAppShell + DashboardHome | Health tecnico preservado fora da Home comercial | `/` = dashboard real; Shell persistente nas rotas autenticadas | MIGRADO | Preservar Shell em todos os WPs seguintes; refinamento estetico fica para Visual Premium. |
| WP-005 | PDV Touch | core/pdv; application; http_api/pdv.py | Router dedicado, sessao Web | /pdv | MIGRADO | Manter; semear dados homologacao e incluir fluxo completo de pagamento. |
| WP-006 | Salao / Mesas / Comandas | core/salao; application; http_api/salao.py | Router dedicado, sessao Web | /salao | MIGRADO | Manter; semear mesas/comandas e certificar jornada operacional. |
| WP-007 | KDS / Cozinha | core/kds; application; http_api/kds.py | Router dedicado, sessao Web | /kds | MIGRADO | Manter; semear estacoes/pedidos e certificar estados. |
| WP-008 | Atendimento do Garcom mobile/tablet | core/garcom; application/garcom_transacoes.py; pages/8_Atendimento_Garcom.py | Sem router Web dedicado identificado | Nenhuma rota Next.js | GAP HTTP/WEB | Criar contrato HTTP session-aware e rota /garcom touch-first. |
| WP-009 | Central de Pedidos omnichannel | core/central_pedidos; application/central_pedidos_transacoes.py; http_api/central_pedidos.py | Router first-class session-aware com leitura, detalhe e comandos idempotentes | /pedidos com fila unificada, detalhe, financeiro, timeline e acoes governadas | MIGRADO | Preservar no Smoke Mestre e integrar os proximos canais sem duplicar regra de negocio. |
| WP-010 | Delivery Proprio | core/delivery; application/delivery_*; infra/delivery; E2E legado | Sem router Web dedicado identificado | Nenhuma rota Next.js | GAP HTTP/WEB | Criar contrato HTTP e /delivery: fila, pedido, checkout, despacho e status. |
| WP-011 | Expedicao / Entrega | core/entrega; application/entrega_*; pages/9_Expedicao_Entrega.py | Sem router Web dedicado identificado | Nenhuma rota Next.js | GAP HTTP/WEB | Criar contrato HTTP e integrar expedicao/entrega a /delivery com RBAC Expedicao/Entregador. |
| WP-012 | Marketplaces / pedidos externos | core/marketplaces; infra adapters; tests/e2e-marketplace | Sem console/contrato Web de operacao identificado | Nenhuma rota Next.js | GAP HTTP/WEB | Expor ingestao/monitoramento first-class e integrar a /pedidos e /delivery. |
| WP-013 | Catálogo administrativo básico | Catálogo existente + WP-014; auditoria de app.py::render_cadastro_ficha_tecnica | Router dedicado e boundaries existentes | `/admin/catalogo` cobre as capacidades originais junto a WP-014 | IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO | Reconciliação exclusivamente documental; sem código novo. Diferença de interação de preço registrada nas pendências para certificação. |
| WP-014 | Engenharia de Cardapio + Ficha Tecnica | application/legacy_cardapio_transacoes.py; application/legacy_cardapio_gemini.py; app.py adaptado | Router de Catalogo cobre ficha manual e importacao Gemini por texto/imagem/PDF, reutilizando o mesmo boundary | `/admin/catalogo` representa ficha e importacao automatica | PARCIAL | Preservar a implementacao candidata e aguardar certificacao integrada; nao corrigir nem melhorar a regra nesta fase. |
| WP-015 | Estoque / Almoxarifado / Validades | core/estoque; application/legacy_estoque_transacoes.py; application/legacy_estoque_forecasting.py; application/legacy_estoque_leitura_visual.py; app.py adaptado | Router de Estoque cobre gestao/lote, forecasting/alertas e leitura visual reutilizando os mesmos boundaries | `/admin/estoque` representa gestao, forecasting e leitor de nota/rotulo | PARCIAL | Preservar a implementacao candidata e aguardar certificacao integrada; lote fisico/FEFO continuam fora do escopo. |
| WP-016 | CRM / Clientes / Cashback | core/crm; infra/crm; application/crm_cashback_* | Router session-aware lista clientes escopados, saldo/historico do ledger e credito manual pelo boundary existente | `/admin/crm` no Shell Proprietario, governada por `admin.acessar` + `cliente.visualizar` e step-up nas mutacoes | PARCIAL | Preservar a implementacao candidata e aguardar certificacao integrada; campanhas sao representadas separadamente no WP-017. |
| WP-017 | Marketing / Resgate / Campanhas | application/crm_marketing_comercial.py; campanhas_governadas.py; infra/crm; app.py adaptado | Router CRM session-aware lista oportunidades escopadas e delega o despacho ao boundary canônico com consentimento e idempotencia preservados | `/admin/crm` representa resgate sem criar segunda area CRM, sob Shell Proprietario e step-up | PARCIAL | Preservar a implementacao candidata e aguardar certificacao integrada; nao corrigir nem ampliar regras de campanha nesta fase. |
| WP-018 | Dashboard Financeiro / Indicadores | app.py legado; application/administracao_proprietario.py | Router administrativo session-aware serializa diretamente `painel_executivo()` para o escopo autorizado | `/admin/dashboard` no Shell Proprietario, governada por `admin.acessar` + `financeiro.visualizar` | PARCIAL | Preservar a implementacao candidata e aguardar certificacao integrada; parametros financeiros permanecem no WP-024. |
| WP-019 | AI FinOps | core/ai_finops.py; application/ai_finops_dashboard.py; infra/ai_finops_read_model.py | Router session-aware consulta somente agregados por período e reutiliza a síntese determinística, sem projector ou chamada de IA | `/admin/ai-finops` no Shell Proprietario, governada por `admin.acessar` | PARCIAL | Preservar a implementacao candidata e aguardar certificacao integrada; nao estimar custos desconhecidos. |
| WP-020 | Área Proprietário / Backoffice | Centro Administrativo legado; application/administracao_proprietario.registrar_acesso; registry e guards existentes | `/v1/admin/acesso` delega auditoria à autoridade original com sessão e step-up | `/admin` no Shell Proprietário; links RBAC para módulos existentes sem duplicação | IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO | Implementação `7935987981a78fe0ee8088020c30efd494d9e62e` publicada; preservar contêiner e governança. Áreas filhas pendentes continuam em seus próprios WPs. |
| WP-021 | Step-up administrativo / reautenticacao | PR #114; auth + AdminStepUpGuard | Sessao elevada 15 min, revogada em troca/logout | Guard de /admin | MIGRADO | Preservar como barreira unica; reutilizar em todas mutacoes sensiveis. |
| WP-022 | Empresa / Matriz / Filiais / Unidades | core/administracao + AplicacaoAdministracaoProprietarioV1; formulário original de empresa/unidades | Consulta, edição e criação original via `/v1/admin/empresa` e `/v1/admin/unidades`, com sessão/step-up e autoridade Application | Rota única `/admin/empresa`, no Shell Proprietário e landing WP-020; `admin.acessar` + `configuracao.alterar` | IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO | Implementação `152ccc6260530503f3d3af87c07fbe750285c2b5` publicada; preservar tenant, unidades administráveis, concorrência, auditoria e membership originais. Administração separada da troca operacional. |
| WP-023 | Usuários / Papéis / Permissões | Application e UI originais localizados; reprodução comprovou ampliação indevida de membership pela unidade padrão | Não implementado; STOP antes da exposição da criação | Sem tela Next.js | GAP HTTP/WEB | BLOQUEADO NA AUDITORIA: reconciliar correção funcional na autoridade de criação de usuário antes de migrar; evidência em `WP023_WP024_CICLO_2X2.md`. Não corrigido neste ciclo. |
| WP-024 | Parametros Financeiros | administracao_proprietario; pagamentos | Web atual cobre operacao PDV, nao configuracao completa | Sem tela administrativa Next.js | GAP HTTP/WEB | Criar parametros financeiros nao secretos no Backoffice; segredos ficam em Credenciais. |
| WP-025 | Impressao Operacional / Configuracao | core/impressao; application/impressao_*; E2E legado | Sem router Web dedicado identificado | Nenhuma rota Next.js | GAP HTTP/WEB | Criar configuracao e operacao Web sem quebrar KDS/PDV. |
| WP-026 | Integracoes e Credenciais | core/integracoes; application/integracoes_admin_transacoes.py; infra/streamlit_app/integracoes_admin.py | Webhooks/healthchecks existem; console session-aware nao | Nenhuma rota Next.js | GAP HTTP/WEB | Criar /admin/credenciais e /admin/integracoes com cofre, step-up, healthcheck e homologacao. |
| WP-027 | Assistente de Atendimento - operacao/governanca | core/assistente_atendimento; application/assistente_*; WhatsApp webhook; E2E legado | Identidade GET/PUT e webhooks existem; parte usa Basic legado | Nenhuma rota Next.js | PARCIAL | Criar HTTP session-aware e /atendimento ou /admin/ia; nome exibido deve vir da identidade configurada. |
| WP-028 | Gerente IA | core/gerente_ia; application/gerente_ia_* | /v1/core/tools, confirmar, perguntar; Basic legado | Nenhuma rota Next.js | PARCIAL | Criar facade session-aware, UI conversacional/decisao e trilha de confirmacao. |
| WP-029 | Pagamentos / PIX / Provedores | core/pagamentos; application/pagbank.py; webhook PagBank; PDV | Operacao existe; configuracao/observabilidade Web incompletas | Pagamento aparece no PDV, sem console provedor | PARCIAL | Certificar checkout Web + conciliacao; mover configuracao de provedores para Credenciais. |
| WP-030 | Cardápio Digital público / Autosserviço | Reutilizar futuramente Catálogo, Pedido/Checkout, Delivery, Central de Pedidos e Pagamentos | GAP HTTP/WEB/PÚBLICO | PENDENTE DE IMPLANTAÇÃO | OBRIGATÓRIA PARA V1.0 | Implantar em ciclo futuro; sem segundo catálogo/pedido/checkout, domínio paralelo ou totem/hardware. |
| WP-031 | Fiscal / NFC-e / SAT | Classificação aprovada pelo proprietário neste ciclo | Fora do escopo | Fora do escopo | BACKLOG FUTURO | FORA DA MIGRAÇÃO CONSERVATIVA WEB V1 ATUAL; não criar NFC-e, SAT, provider fiscal ou novo domínio fiscal. |
| WP-032 | Notificações Internas | DOMÍNIO CANÔNICO EXISTENTE: core/notificacoes_internas; application/notificacoes_internas | GAP HTTP/WEB ADMINISTRATIVO | PENDENTE | OBRIGATÓRIA PARA V1.0 | Futuramente expor configuração de destinatários, preferências e alertas; sem inbox, feed, lido/não lido, badge ou central genérica de mensagens. |
| WP-033 | Auditoria / Historico administrativo | admin proprietario legado; repositorios de auditoria | Sem tela/contrato Web de consulta confirmado | Sem tela Next.js | GAP HTTP/WEB | Criar consulta auditavel no Backoffice, sem expor segredos. |

## 5. Capacidades historicas comprovadas na UI Streamlit
O `app.py` legado comprova abas para Engenharia de Cardapio, CRM/Resgate/Cashback, PDV/Pix, Estoque/Validades, Dashboard Financeiro, Assistente de Atendimento e AI FinOps, com abas condicionais para Central de Pedidos, KDS, Mesas/Comandas, Delivery Proprio e Impressao Operacional. As paginas separadas comprovam ainda Administracao/Proprietario, Integracoes e Credenciais, Atendimento do Garcom e Expedicao/Entrega.

## 6. Gaps arquiteturais que o resgate deve corrigir
1. **Contratos HTTP incompletos:** varios dominios maduros ainda nao possuem API first-class, session-aware, adequada ao Next.js.
2. **E2E legado nao garante paridade Next.js:** testes de Delivery, Entrega, Garcom, Assistente e Order Center comprovam fluxo historico, mas nao a nova Web.
3. **Dados de homologacao insuficientes:** PDV, Salao e KDS abrem na Web, mas fixtures ainda sao incompletas. No Smoke da Onda 1, `unidade-auth-b` preservou a sessao corretamente, porem o catalogo respondeu `403 catalogo_indisponivel_no_escopo` por ausencia/invalidade do vinculo seguro com a loja legada. O comportamento fail-closed deve ser preservado; o gap e de provisionamento/homologacao.
4. **Identidade do assistente:** a UI nova deve usar o nome configurado por tenant, nunca fixar nome historico como nome de produto.

## 7. Ordem Mestre de Execucao
### Onda 1 - Shell Corporativo Unificado
**CERTIFICADA.** Shell persistente, Home real, unidade ativa, operador, logout, troca de unidade, navegacao governada por RBAC, separacao Operacao x Proprietario e step-up administrativo preservado.
### Onda 2 - Coracao operacional faltante
**WP-009 CERTIFICADA.** Central de Pedidos concluida e integrada a `main`. Proxima sequencia obrigatoria: WP-010 Delivery -> WP-011 Expedicao/Entrega -> WP-012 Marketplaces -> WP-008 Garcom, sempre fechando Core/Application -> HTTP -> Next -> RBAC -> testes antes do proximo bloco.
### Onda 3 - Retaguarda completa
Cardapio/Ficha Tecnica -> Estoque -> CRM/Cashback -> Marketing -> Financeiro -> Empresa/Unidades -> Usuarios/Permissoes -> Impressao -> Auditoria.
### Onda 4 - IA e Integracoes
Assistente de Atendimento -> Gerente IA -> AI FinOps -> Integracoes/Credenciais -> Pagamentos/provedores e healthchecks administrativos.
### Onda 5 - Certificacao de Paridade
Smoke Mestre completo e Gate de Paridade Web. Nenhuma linha obrigatoria pode permanecer PARCIAL, GAP ou A VERIFICAR para declarar V1 Web concluida.

## 8. Gate obrigatorio por PR
Cada PR do WEB-PARITY-V1 deve: (a) citar IDs WP afetados; (b) atualizar este inventario; (c) preservar regras de negocio no Core/Application; (d) usar sessao assinada e RBAC/step-up; (e) adicionar/atualizar testes; (f) manter lint, typecheck/build e regressao verdes; (g) nao promover para MIGRADO sem evidencias da cadeia inteira.

## 9. Definition of Done de uma capacidade
- Dominio/core identificado e preservado.
- Application/infra reutilizada, sem duplicar regra de negocio no React.
- HTTP first-class session-aware, tenant/unit safe, idempotente quando aplicavel.
- RBAC e step-up aplicados conforme risco.
- Rota Next.js completa com loading/error/empty states.
- Fixture de homologacao e testes unitarios/HTTP/E2E suficientes.
- Smoke manual no navegador concluido.
- Linha WP atualizada para MIGRADO.

## 10. Evidencias principais auditadas
- `web/src/app/`
- `web/src/features/`
- `web/src/app/admin/`
- `http_api/`
- `http_api/app.py`
- `core/`
- `application/`
- `infra/delivery/`
- `infra/assistente_atendimento/`
- `infra/crm/`
- `infra/gerente_ia/`
- `infra/integracoes/`
- `core/estoque/modelos.py`
- `app.py`
- `pages/`
- `infra/streamlit_app/admin_proprietario.py`
- `infra/streamlit_app/integracoes_admin.py`
- `tests/`
- `tests/e2e/`

## 11. Registro de execucao
- **Ciclo WP-023 + WP-024 — STOP no baseline `75176b6c65aa8ad841edb4b3140bfe4693859bc4`:** pré-flight confirmado, PR #118 OPEN/DRAFT e árvore limpa. A criação canônica de usuários permitiu persistir unidade padrão externa ao conjunto administrável; controle e reprodução documentados em `WP023_WP024_CICLO_2X2.md`. WP-023 bloqueado antes da implementação, WP-024 não iniciado. Somente documentação publicada; nenhum WP promovido nem regra corrigida.
- **09/09/2026 - WP-022 publicado e ciclo encerrado:** implementação `152ccc6260530503f3d3af87c07fbe750285c2b5`, local = remoto após push/fetch. Consulta, edição e criação existentes em `/admin/empresa`, sem alteração de Application/Core/Infra. 40 testes Python, 3 testes Node, Ruff/mypy direcionados, lint/typecheck/build frontend e diff check aprovados. Evidência e auditoria em `WP020_WP022_CICLO_2X2.md`. WP-020 teve checkpoint documental final confirmado em `c91d0a7ef371c056ba1404f307e12a8f990f6d5d`. STOP após este checkpoint documental; WP-023 + WP-024 apenas planejados para próximo ciclo. PR #118 permanece Draft; sem merge, deploy, Smoke Mestre ou certificação integrada.
- **09/09/2026 - WP-020 publicado:** implementação `7935987981a78fe0ee8088020c30efd494d9e62e`, local = remoto após push/fetch. Landing `/admin`, registry único e auditoria via Application existente; Application/Core/Infra intactos. 51 testes Python, 2 testes Node, Ruff/mypy direcionados, lint/typecheck/build frontend e diff check aprovados. WP-013 reconciliado somente em documentação como capacidades representadas por `/admin/catalogo` + WP-014; diferença preexistente de interação registrada. Evidências em `WP020_WP022_CICLO_2X2.md`; sem certificação integrada, Smoke Mestre, merge ou deploy.
- **09/09/2026 - Checkpoint documental do ciclo WP-020 + WP-022:** por decisão explícita do proprietário, WP-030 e WP-032 são obrigatórias para V1.0 e permanecem pendentes; WP-031 é backlog futuro, fora desta migração. Este checkpoint não implementa essas capacidades. Base inicial confirmada local/remoto: `d261a94e854334d9fdf9c073e8af73f557f31114`, PR #118 OPEN/DRAFT. Este ciclo termina após WP-022; sem WP-023, Smoke Mestre, certificação integrada, merge ou deploy.
- **08/09/2026 - WP-003 + WP-004 iniciados** na branch `feat/web-parity-v1-wp003-wp004-shell-dashboard`, a partir da baseline certificada `22bf22c05641fb4340c48f65d39514dc37d649fe`.
- O candidato implementou Shell persistente, navegacao filtrada por RBAC, troca de unidade, logout, Home comercial real, fail-closed para todas as rotas Web nao publicas e realocacao do health harness para `/admin/system-health`.
- **Matriz automatizada da PR #115: 15/15 workflows SUCCESS**, incluindo lint, production build/typecheck, regressao backend e gates comerciais existentes.
- **Smoke manual concluido:** PDV -> Home -> Salao -> Home -> KDS -> Home sem segundo login; troca `unidade-auth-a` -> `unidade-auth-b` preservou a sessao; logout invalidou a sessao e exigiu novo login para reentrada.
- O `403 catalogo_indisponivel_no_escopo` observado apos trocar para `unidade-auth-b` foi classificado separadamente como gap de provisionamento/homologacao da unidade, mantendo a fronteira fail-closed de isolamento.
- **WP-003 e WP-004 promovidos para MIGRADO somente apos os gates automaticos e o Smoke manual concluirem com sucesso.**
- **08/09/2026 - WP-009 Central de Pedidos certificada** na PR #116, HEAD `f88f127a69b548d7b3b53cc9abe306ed7a2d2700`, apos smoke funcional completo e **22/22 workflows SUCCESS**.
- O smoke WP-009 comprovou sessao unica, fila unificada, leitura de pedido criado no PDV, detalhe, financeiro, alertas, timeline e cancelamento governado com atualizacao de versao e evento `pedido.cancelado`; o atalho `Dashboard` foi incluido no cabecalho antes da certificacao final.
- A falha intermitente do E2E legado CRM/cashback foi estabilizada no helper Playwright de combobox antes da matriz final, sem relaxar gates nem regras de negocio.
- **PR #116 integrada a `main` no merge commit `5a17b0c8a1cb6dad576ce5b089166748b138900c`.**
- **08/09/2026 - Bloco WP-010 + WP-011 iniciado** na branch sequencial `feat/web-parity-v1-wp010-wp011-delivery-entrega`, criada diretamente da `main` certificada apos o merge da PR #116.
- **09/09/2026 - Migracao conservativa total iniciada** na branch `feat/web-parity-v1-total-original-migration`, criada exatamente de `731f6db17ec46a8173d10dd29897c8c623e52f16`; a tentativa Codex anterior de WP-014/WP-015 foi descartada integralmente.
- **WP-013/WP-014/WP-015 em implementacao candidata parcial:** o Catalogo existente foi preservado e ampliado com a superficie manual de Ficha Tecnica e a importacao Gemini reutilizavel em `application/legacy_cardapio_gemini.py` (`9871814`). Estoque/Almoxarifado/Validades preservou a gestao manual/lote e passou a reutilizar os boundaries de forecasting/alertas (`96e551d`) e leitura visual de nota/rotulo (`c910153`) no Streamlit e no HTTP/Web. Os tres commits estao publicados na Draft PR #118 com remote HEAD confirmado em `c91015319207fa955cd381af74912c41e547e075`. Nenhuma promocao para MIGRADO foi realizada; Smoke Mestre e certificacao integrada permanecem adiados.
- **09/09/2026 - WP-016 em implementacao candidata parcial:** CRM/Clientes/Cashback ganhou contrato HTTP session-aware e rota `/admin/crm`, reutilizando os leitores CRM e o ledger canônico para consulta e `application/crm_cashback_comercial.py` para crédito manual governado. O checkpoint `0c4e5b3dc0ef8f76145dc7d1c65bb00d2ee66046` está publicado na Draft PR #118; campanhas/resgate permanecem exclusivamente no WP-017. Nenhuma promocao para MIGRADO foi realizada; Smoke Mestre e certificacao integrada permanecem adiados.
- **09/09/2026 - WP-017 em implementacao candidata parcial:** a selecao de clientes inativos, o prompt Gemini, o fallback e os identificadores diarios de campanha foram extraidos mecanicamente de `app.py` para `application/crm_marketing_comercial.py`. Streamlit e HTTP reutilizam o mesmo boundary; `/admin/crm` ganhou a superficie de resgate sem duplicar o CRM. O checkpoint `d03bf1adae93d3a800d00a968afbdf8f7973519a` está publicado na Draft PR #118, com tenant/unidade, RBAC, step-up, consentimento e idempotencia preservados. Nenhuma promocao para MIGRADO foi realizada; Smoke Mestre e certificacao integrada permanecem adiados.
- **09/09/2026 - WP-018 em implementacao candidata parcial:** o read model existente `AplicacaoAdministracaoProprietarioV1.painel_executivo()` foi exposto por HTTP session-aware e materializado em `/admin/dashboard`, com item unico no Shell Proprietario e sem alterar `core/`, `application/` ou `infra/`. O checkpoint `46eb468a3a04fe1679da1b481265e2ed228666ec` está publicado na Draft PR #118; tenant/unidade e as permissoes `admin.acessar` + `financeiro.visualizar` permanecem governantes. Nenhuma promocao para MIGRADO foi realizada; Smoke Mestre e certificacao integrada permanecem adiados.
- **09/09/2026 - WP-019 em implementacao candidata parcial:** o read model `AIFinOpsSQLAlchemyReadModel` e a síntese `resumir_ai_finops()` foram expostos por HTTP session-aware e materializados em `/admin/ai-finops`, sem alterar `core/`, `application/` ou `infra/`. O checkpoint `e4fa395958199fa562659298e7f0132cb3e52658` está publicado na Draft PR #118; a consulta permanece read-only, escopada por tenant/unidade e período, sem executar projector nem chamada de IA. Nenhuma promocao para MIGRADO foi realizada; Smoke Mestre e certificacao integrada permanecem adiados.
- **UX follow-up nao bloqueante:** o card inferior "Unidade operacional" e informativo; o seletor oficial fica na topbar. Tornar o card inferior tambem acionavel pode ser refinado depois sem alterar a regra de sessao.

---
**Regra de mudanca:** este documento e vivo e versionado por baseline. Qualquer nova descoberta deve atualizar a linha correspondente antes de iniciar implementacao que dependa dela. A arquitetura visual premium so reabre depois do Gate de Paridade Web.
