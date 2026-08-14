# Gate Final Interno V1 — Core e Runtime executado

## Decisão conclusiva

A composição real do Gerente IA era requisito obrigatório da V1 e não podia ser
postergada para PR22/V2. Os Gates V1-A a V1-D foram implementados na branch
`work/v1-core-runtime`, sem merge, deploy, credenciais reais ou operação externa.

O Core deixou de depender de `RuntimeGerenteIATeste` no caminho de produção. O
composition root canônico é `application.gerente_ia_runtime`, composto apenas por
adapters SQLAlchemy, auditoria persistente, configuração tenant-aware e gateway
Gemini por referência de segredo.

## Matriz dos gates

| Gate | Estado | Evidência principal |
|---|---|---|
| V1-A — fontes e consultas | Concluído internamente | `/v1/core/tools` autentica o usuário, deriva tenant/unidade da identidade e consulta pedidos, financeiro, KDS, salão, delivery, estoque, CRM, integrações e eventos persistentes. |
| V1-B — eventos e correlação | Concluído internamente | Outbox persistente projeta `EnvelopeMensagem` no consumer idempotente do Core na mesma transação; relatório central emite recomendações determinísticas com fonte e impacto. |
| V1-C — ações seguras | Concluído internamente | Previews, fingerprints e resultados idempotentes são persistentes; priorização KDS e pausa de produto passam por preview, confirmação humana, RBAC, reconsulta anti-stale, auditoria e commit atômico; campanhas permanecem rascunhos. |
| V1-D — entrada e LLM | Concluído internamente | API autenticada expõe tools, confirmação, identidade do assistente e pergunta em linguagem natural. O planejador Gemini resolve configuração e segredo por tenant/unidade e só produz chamada de tool validada pelo Core. |

## Persistência aditiva

A migration reversível `0013_core_runtime_v1` cria:

- `assistente_atendimento_identidade_v1`;
- `gerente_ia_eventos_v1`;
- `gerente_ia_previews_v1`;
- `gerente_ia_resultados_acao_v1`;
- `produto_disponibilidade_v1`;
- `crm_consentimentos_atuais_v1`;
- `crm_rascunhos_campanha_v1`.

Todas as tabelas operacionais carregam escopo tenant/unidade quando aplicável. A
migration foi executada somente em bancos locais/descartáveis durante a validação.

## Fluxo ponta a ponta comprovado

O teste `tests/integration/gerente_ia/test_core_runtime_v1_e2e.py` cobre o fluxo:

1. cria dois tenants e usuários administradores persistentes;
2. autentica cada requisição HTTP com credenciais armazenadas por hash;
3. deriva `ContextoExecucao` da identidade, sem aceitar tenant/unidade no payload;
4. grava evento CRM real na outbox e o projeta no Core de forma transacional e
   idempotente, com redação de campo sensível;
5. consulta relatório e conversão em fontes persistentes;
6. cria campanha apenas como rascunho e calcula audiência consentida;
7. persiste preview, rejeita confirmação cross-tenant, confirma como humano
   autorizado, altera KDS e prova replay idempotente;
8. persiste pausa de produto em autoridade tenant-scoped;
9. configura e altera nomes diferentes do assistente para os dois tenants;
10. passa linguagem natural pelo planejador e depois por `ServicoGerenteIA`;
11. prova que o adapter Gemini de produção seleciona modelo e segredo distintos
    por tenant, usando transporte capturado sem credencial externa real.

## Assistente de Atendimento configurável

O nome canônico de domínio é **Assistente de Atendimento**. O nome público é
obtido dinamicamente de `assistente_atendimento_identidade_v1`; na ausência de
registro, o fallback seguro é `Assistente de Atendimento`.

A configuração suporta atributos públicos primitivos para evolução futura, possui
versão otimista, ator, correlação e auditoria. Chaves sensíveis são recusadas. A
lógica de negócio não toma decisões com base no nome público.

O Streamlit usa a entrada canônica
`core.assistente_atendimento.ui_streamlit` e recebe o nome persistido. O fluxo
histórico do bot continua test-only e fail-closed; seus nomes Python antigos foram
preservados apenas como compatibilidade de testes e configurações já existentes.

## Referências restantes a “Mica”

As referências restantes foram classificadas e não representam identidade fixa do
runtime:

- `core/mica`, `tests/unit/mica` e `tests/e2e-mica`: API e fixtures históricas
  preservadas para compatibilidade e regressão do fluxo test-only;
- `FM_AI_MICA_V1` e `playwright.mica.config.ts`: alias de flag e configuração E2E
  antigos; a flag canônica nova é `FM_AI_ASSISTENTE_ATENDIMENTO_V1`;
- valores `MICA` nos enums de canal/origem: compatibilidade de dados persistidos e
  integrações antigas, não nome público;
- “Mica Burger/Burguer” e exemplos de produtos/cupons: dados da marca fictícia do
  estabelecimento de demonstração, não identidade do assistente;
- documentação histórica: registro de decisões anteriores, sem efeito no runtime.

Nenhum prompt, título ou regra nova do Core fixa “Mica” como nome do assistente.

## Dependências exclusivamente externas

Permanecem externas e fora desta execução:

- conta, quota/billing e credencial Gemini real;
- sandboxes, credenciais e contratos dos demais provedores;
- webhooks públicos e homologação de tráfego externo;
- migration em banco real, deploy e observação em ambiente real;
- merge em `main`, que exige autorização específica.

Essas dependências não impedem a execução interna do Core: o caminho tipado e os
testes com bancos descartáveis funcionam sem elas e falham de modo fechado quando
a configuração externa homologada não existe.
