# Kordena V1 — Visual Premium Final — System Design

**Data de reconciliação:** 27/09/2026
**Branch oficial:** `feat/kordena-v1-visual-premium-final`
**PR:** nova PR canônica da fase Visual Premium
**Baseline funcional autorizado:** `staging/kordena-premium@023bb8d78495eb5464568543c248e3337019766f`
**Baseline:** KCA-00→KCA-17 integrados; PR #137 mergeada; `staging/kordena-premium` reconciliado no merge `023bb8d78495eb5464568543c248e3337019766f`; release público continua separado e fail-closed nas dependências externas.

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

O merge normal da PR canônica está autorizado automaticamente após 100% dos gates obrigatórios verdes, reconciliação completa e ausência de STOP condition. Deploy/cutover público, ações destrutivas, migrations produtivas irreversíveis, transações financeiras reais e ampliação de privilégios permanecem fora desta autorização.


## 7. Ordem executiva vigente — 27/09/2026

Por decisão explícita mais recente do proprietário, o fluxo desta fase e das seguintes é:

`executar → corrigir → testar → certificar → mergear → pós-merge → próximo item do Cronograma Mestre`.

Não é necessária nova autorização intermediária para PR, correção, certificação ou merge normal da PR canônica quando todos os gates exigidos estiverem comprovadamente verdes. A execução só deve parar por STOP condition real ou por ação sensível que mantenha gate próprio.

## 8. CURRENT técnico reconciliado

- repositório: `faabio3131/fm-ai-platform`;
- base: `staging/kordena-premium`;
- baseline SHA: `023bb8d78495eb5464568543c248e3337019766f`;
- branch da fase: `feat/kordena-v1-visual-premium-final`;
- aplicação visual canônica: `web/` em Next.js;
- 33/33 Work Packages funcionais certificados antes da fase visual;
- implementação histórica da PR #47 é somente referência e não será mergeada/rebaseada cegamente;
- Visual Premium deve preservar regras de negócio, auth, RBAC, tenant/unidade, contratos HTTP, dados, migrations e autoridades de domínio;
- deploy público não faz parte desta fase.
