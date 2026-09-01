# F6-D — System Design — Commercial Runtime E2E

**Base de abertura:** `f635495049657230391adc452d4571239b5b85b2`  
**Pré-condição:** F6-A, F6-B e F6-C fechadas com matriz transversal verde.

## Objetivo

Provar o PDV canônico no mesmo tipo de runtime exigido para staging/produção,
sem `FM_AI_TEST_MODE`, usando PostgreSQL, autenticação V1, RBAC real e terminal
server-side allowlisted.

F6-D não homologa provider externo. Dinheiro e cartão devem continuar operacionais
sem depender de PagBank/Mercado Pago. Pix sem provider/credencial/homologação válida
deve permanecer fail-closed.

## Ambiente do gate

O workflow `Fase 6D Commercial Runtime E2E Gate` sobe PostgreSQL 16 efêmero e
configura:

- `FM_AI_ENV=staging`;
- `DATABASE_URL=postgresql+psycopg://...`;
- tenant/unidade comerciais explícitos;
- `FM_AI_PDV_MODE=authoritative_canary`;
- autorização server-side do canary;
- terminal `caixa-f6d`;
- allowlist contendo apenas esse terminal.

O gate falha imediatamente se `FM_AI_TEST_MODE=1`.

## Banco e schema

O seed `scripts/seed_f6d_commercial_runtime.py`:

1. executa o runner oficial de migrations;
2. cria somente dados efêmeros de homologação;
3. cria vínculo explícito tenant/unidade → loja legada;
4. cria usuário CAIXA real na persistência de segurança;
5. cria produto, insumo e ficha técnica necessários à jornada.

Nenhum `Base.metadata.create_all` do `app.py` é usado para runtime comercial.
Ao iniciar, a aplicação executa `assert_schema_current`.

## Autenticação e RBAC

O navegador começa na tela real de login. O usuário persistido possui apenas
`Papel.CAIXA`, cujo conjunto de permissões inclui `PDV_OPERAR`.

O contexto do checkout é derivado da identidade autenticada e do Active Execution
Scope. Tenant/unidade não são recebidos de widget do operador.

## Jornada browser

O Playwright comercial usa configuração própria e launcher próprio; ambos removem
as variáveis do harness de teste.

A prova cobre:

- login comercial real;
- abertura da Frente de Caixa;
- venda em dinheiro;
- venda com cartão presencial;
- tentativa Pix sem confirmação válida de gateway.

Dinheiro e cartão devem produzir sucesso canônico. Pix deve exibir
`Pix em produção exige confirmação válida do gateway antes da baixa.` e não pode
produzir mensagem de venda concluída.

## Evidência no PostgreSQL

Após o navegador, o workflow consulta as tabelas canônicas `pedidos_v1` e
`pagamentos_v1` no mesmo banco PostgreSQL do runtime.

Essa evidência complementa, mas não substitui, a confirmação visual da jornada.

## Segurança

F6-D mantém:

- LEGACY como rollback operacional do canary;
- terminal governado por configuração server-side;
- canary fail-closed em configuração parcial;
- autenticação obrigatória em staging;
- Pix fail-closed sem provider homologado;
- ausência de Fakes comerciais;
- nenhuma mudança automática de produção ou merge.

## Definition of Done da F6-D

F6-D só pode ser fechada quando, no mesmo SHA:

1. gate dedicado estiver verde;
2. dinheiro estiver verde no navegador comercial;
3. cartão estiver verde no navegador comercial;
4. Pix sem provider estiver comprovadamente bloqueado;
5. regressões F6-A/F6-C permanecerem verdes;
6. matriz transversal do PR terminar integralmente verde.
