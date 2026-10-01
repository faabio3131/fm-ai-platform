# WP-017 — Central Web de Campanhas — Execução WM-00 → WM-07

## Autoridade e baseline

- Fonte: auditoria profunda PDF × Web de 01/10/2026.
- Repositório: `faabio3131/fm-ai-platform`.
- Baseline: `staging/kordena-premium@ce63748c8a8495067262b2577e63ebc4fda9b38b`.
- Railway no baseline: aplicação e PostgreSQL em SUCCESS.
- Branch de execução: `feat/kordena-wp017-campaign-web-parity`.

## WM-00 — Freeze e prova do CURRENT

A auditoria reconciliada distingue duas coisas que antes foram tratadas como equivalentes:

1. **WP-017 histórico certificado**: seleção de inativos + sugestão Gemini/fallback + consentimento + despacho WhatsApp idempotente dentro de `/admin/crm`.
2. **WP-017 exigido pelo produto**: lifecycle Web completo de campanha, incluindo rascunho, audiência, edição, submissão, aprovação, publicação/despacho, histórico e integração explícita com Gerente IA.

Por isso o ledger foi rebaixado temporariamente para `IMPLEMENTED_UNCERTIFIED`. Nenhum outro WP foi reaberto.

**Gate WM-00:** `WEB_PARITY_BASELINE_CONFIRMED`.

## WM-01 — System Design cirúrgico

### Autoridades reutilizadas

Não será criada segunda campanha, segundo CRM, segunda autorização ou segunda outbox.

- campanha canônica: `crm_rascunhos_campanha_v1` / `RascunhoCampanhaORM`;
- transições humanas: `CampanhasGovernadasSQLAlchemy` + `ServicoGerenteIA`;
- consentimento: `crm_consentimentos_v1` / `LeitorConsentimentosMarketingSQLAlchemy`;
- clientes/contatos: `core/crm` + `infra/crm`;
- despacho externo: `EnvioWhatsAppMarketingComercial`;
- proteção at-most-once: Outbox V1 via `EnvioMarketingIdempotenteSQLAlchemy`;
- auditoria: autoridade canônica existente;
- sessão/tenant/unidade: `AuthSessionRuntime` + `obter_identidade_operacional`;
- step-up: `auth_runtime.admin_status`.

### Rota Web

`/admin/campanhas`

### API Web

`/v1/campanhas`

Contratos planejados:

- `GET /v1/campanhas` — listar;
- `POST /v1/campanhas` — criar rascunho;
- `GET /v1/campanhas/{id}` — detalhe/preview;
- `PATCH /v1/campanhas/{id}` — editar somente rascunho;
- `GET /v1/campanhas/{id}/audiencia` — elegibilidade/consentimento;
- `PUT /v1/campanhas/{id}/audiencia` — persistir seleção governada;
- `POST /v1/campanhas/{id}/submeter` — aguardando aprovação;
- `POST /v1/campanhas/{id}/aprovar` — aprovação humana;
- `POST /v1/campanhas/{id}/publicar` — gera referência publicável; não envia automaticamente;
- `POST /v1/campanhas/{id}/despachar` — comando explícito de envio;
- `GET /v1/campanhas/{id}/historico` — transições/resultados.

### State machine Web

```text
RASCUNHO
  ├─ editar
  ├─ definir audiência
  └─ submeter
       ↓
AGUARDANDO_APROVACAO
       ↓ humano autorizado + step-up
APROVADA
       ↓ humano autorizado + step-up
PUBLICAVEL
       ↓ comando explícito + revalidação de consentimento
DESPACHOS REGISTRADOS NO HISTÓRICO
```

Compatibilidade: a API/serviço legado que já aprovava um rascunho diretamente não será quebrada; a nova superfície Web exige submissão antes da aprovação.

### Audiência sem novo banco paralelo

A seleção de audiência será registrada no `EventoCoreORM` como evento de campanha, contendo apenas IDs opacos de clientes. A tabela canônica do rascunho continua sendo a campanha. Consentimento é sempre relido da autoridade CRM antes do despacho; revogação posterior bloqueia o envio.

### Segurança

- nenhum `tenant_id` ou `unidade_id` é aceito do body como autoridade;
- leitura/criação exige permissões de cliente/campanha;
- mutações críticas exigem `campanha.aprovar` e step-up Web ativo;
- aprovação/publicação são humanas; identidade de sistema/LLM não pode promovê-las;
- `Idempotency-Key` obrigatória nas mutações;
- cross-tenant falha fechado;
- provider externo indisponível/falha retorna estado de falha/indisponibilidade e nunca sucesso sintético.

### Gerente IA

O tool `PREPARAR_CAMPANHA` continua capaz apenas de criar **rascunho**. A UI passará a reconhecer esse resultado e oferecer abertura do rascunho na Central de Campanhas. O LLM não recebe endpoint de aprovação, publicação ou despacho.

**Gate WM-01:** `CAMPAIGN_WEB_BOUNDARY_APPROVED`.

## Ordem restante

- WM-02 — API governada;
- WM-03 — Central Web;
- WM-04 — CRM → Campanhas;
- WM-05 — Gerente IA → rascunho;
- WM-06 — regressão estrutural 33/33;
- WM-07 — certificação final e reconciliação do ledger.

A promoção de WP-017 novamente para `CERTIFIED` só pode ocorrer após evidência verde de WM-02→WM-07.
