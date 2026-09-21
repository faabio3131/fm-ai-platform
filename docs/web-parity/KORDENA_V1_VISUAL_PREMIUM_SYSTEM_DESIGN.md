# Kordena V1 — Visual Premium Final — System Design

**Data:** 21/09/2026
**Branch oficial:** `feat/web-parity-v1-total-original-migration`
**PR:** #118
**Baseline funcional autorizado:** `7b588012c5cd09a265f7b955f6d485eaa4c7713d`
**Baseline CI:** 29/29 workflows SUCCESS; `WP-031 Master Gate` run `35622812468` SUCCESS.

## 1. Objetivo

Elevar a interface Web canônica do Kordena V1 ao padrão Visual Premium final sem criar segunda aplicação, segunda autoridade, nova regra de negócio ou fluxo paralelo.

O Visual Premium é uma evolução da mesma linha comercial e arquitetural. Backend, contratos HTTP, permissões, step-up, tenant/unidade, idempotência, autoridades financeiras/fiscais e Core cognitivo permanecem inalterados.

## 2. Invariantes obrigatórios

- preservar rotas canônicas;
- preservar `availableShellModules` e a autorização derivada de permissões;
- preservar sessão assinada, troca de unidade e logout existentes;
- preservar `admin.acessar` e step-up administrativo;
- preservar contratos do Gerente IA, inclusive preview/fingerprint/idempotency;
- preservar checkout público com preço final validado pelo servidor;
- preservar módulos operacionais e administrativos na mesma árvore `web/src`;
- não adicionar estado global concorrente, API paralela ou nova fonte de verdade;
- nenhuma alteração desta fase declara homologação externa, deploy ou produção.

## 3. Design system

A identidade Premium utiliza base midnight/navy, cobalt/sky/cyan para inteligência e navegação, emerald para estados saudáveis e amber/red para atenção e falha.

A camada compartilhada inclui:

- tokens globais de cor, raio e superfície;
- painéis claros e escuros com profundidade controlada;
- botões, campos, dialogs, sheets, tables, tabs e badges harmonizados;
- foco visível e estados de interação;
- `prefers-reduced-motion`;
- tipografia e números tabulares;
- responsividade touch-first;
- identidade visual explícita do Kordena Cognitive Core.

## 4. Superfícies prioritárias

1. Login e seleção de unidade.
2. Unified App Shell e navegação.
3. Home operacional.
4. Centro Administrativo.
5. Gerente IA.
6. Dashboard Financeiro e Indicadores.
7. Cardápio Público.
8. Componentes UI compartilhados, herdados pelos demais módulos.

Os demais módulos mantêm seus workspaces funcionais e recebem o novo padrão por shell, tokens e componentes compartilhados. Mudanças locais adicionais somente serão feitas quando necessárias para consistência sem risco funcional.

## 5. Acessibilidade e ergonomia

- foco visível em controles;
- contraste de estados críticos;
- labels e aria-labels preservados;
- suporte a redução de movimento;
- tamanhos touch adequados;
- navegação mobile horizontal preservada;
- nenhum efeito visual pode esconder erro, status ou ação governada.

## 6. Gate de saída

A fase somente pode ser considerada concluída após:

- ESLint Web: SUCCESS;
- TypeScript `--noEmit`: SUCCESS;
- todos os testes Node Web: SUCCESS;
- teste `visual-premium-v1.test.mjs`: SUCCESS;
- Next production build: SUCCESS;
- `git diff --check`: SUCCESS;
- matriz integral da PR sem falha causada pela fase;
- auditoria final de preservação funcional;
- evidência documental do HEAD certificado.

Merge, deploy e promoção para produção permanecem proibidos nesta fase.
