# Kordena V1 — Visual Premium Final — Execution Ledger

**PR:** #138  
**Branch:** `feat/kordena-v1-visual-premium-final`  
**Base canônica:** `staging/kordena-premium@023bb8d78495eb5464568543c248e3337019766f`  
**Status:** EM EXECUÇÃO

## Objetivo

Aplicar o acabamento Visual Premium final sobre a aplicação Next.js canônica do Kordena, preservando integralmente contratos, fluxos, autoridade de domínio, autenticação, RBAC, tenant/unidade, idempotência e dados.

## Invariantes preservados

- nenhuma API foi alterada;
- nenhuma regra de negócio foi alterada;
- nenhuma migration foi criada;
- nenhuma tabela ou schema foi alterado;
- nenhuma autoridade comercial/fiscal/financeira foi movida;
- `availableShellModules`, sessão, logout e troca de unidade permanecem canônicos;
- step-up administrativo permanece canônico;
- Gerente IA mantém preview, fingerprint, confirmação e idempotency key;
- checkout público mantém valor final validado pelo servidor;
- acesso comercial continua fail-closed;
- nenhuma ação desta fase declara deploy ou produção.

## Sistema visual final

Direção vigente:

- base obsidian/midnight/navy;
- superfícies dark em camadas;
- cobalt/sky/cyan como identidade de inteligência e navegação;
- emerald para estado saudável/sucesso;
- amber para atenção;
- red para falha;
- hierarquia forte e densidade operacional;
- foco visível;
- redução de movimento;
- controles touch-friendly;
- sombras e glow disciplinados;
- uma única identidade visual entre módulos.

## Superfícies trabalhadas

### Fundação compartilhada
- `web/src/app/globals.css`
- root dark mode em `web/src/app/layout.tsx`
- Button
- Card
- Input
- Textarea
- Badge
- Tabs
- Dialog
- Sheet
- Dropdown Menu
- Table

### Identidade / acesso
- Login
- Signup
- Verificação de signup
- Unit Selector herdando Dialog/Button premium
- Admin step-up herdando design system premium
- Commercial Access Guard preservado em dark mode

### Shell e home
- Unified App Shell
- navegação desktop
- navegação mobile
- Home operacional
- Centro Administrativo

### Operação
- PDV
- Carrinho do PDV
- Couvert Artístico
- Central de Pedidos
- Marketplaces
- Delivery
- Expedição / Entrega

### Administração
- Auditoria
- Notificações Internas
- Saúde do sistema

### Superfícies já premium no CURRENT e preservadas
- Gerente IA
- Dashboard Financeiro / Indicadores
- Cardápio Público
- KDS
- Salão
- Garçom
- Fiscal
- demais workspaces dark que herdam tokens e componentes compartilhados

## Gate da fase

Obrigatório antes de merge:

1. ESLint Web;
2. TypeScript `--noEmit`;
3. todos os testes Node Web;
4. `visual-premium-v1.test.mjs`;
5. Next production build;
6. diff whitespace;
7. matriz transversal aplicável;
8. auditoria de preservação funcional;
9. reconciliação documental;
10. merge da PR canônica;
11. Visual Premium Gate pós-merge na staging;
12. somente então liberar a etapa pós-funcional de servidor/release.

## Ordem executiva

`executar → corrigir → testar → certificar → mergear → pós-merge → próximo item do Cronograma Mestre`.

Deploy/cutover público e ações sensíveis continuam fora da autorização automática desta fase.
