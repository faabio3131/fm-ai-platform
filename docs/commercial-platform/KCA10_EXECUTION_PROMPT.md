# PROMPT MESTRE — KCA-10

## Webhook Inbox + Reconciliation

### Missão
Transformar eventos externos de billing em estado interno confiável, auditável e recuperável, sem antecipar KCA-11.

### Dependência
- KCA-09 / KCA-G9: PASS.
- KCA-09B / KCA-G9B: PASS.
- KCA-10 só inicia após HEAD documental G9B 100% verde.

### Objetivos canônicos
Implementar:
1. durable webhook inbox;
2. signature verification;
3. provider event ID;
4. body hash;
5. idempotência;
6. replay protection;
7. normalização provider-neutral;
8. ordering/out-of-order protection;
9. retry governado;
10. DLQ;
11. replay/reprocessamento controlado;
12. reconciliation job/serviço;
13. Billing Ledger mínimo para estado interno confiável;
14. auditoria/correlation/causation;
15. métricas/readiness suficientes para KCA-G10.

### Fluxo
HTTP webhook
→ identificar provider account
→ verificar assinatura pelo adapter
→ calcular body hash
→ persistir inbox durável
→ detectar duplicate/replay conflict
→ normalizar evento
→ validar binding interno
→ proteger ordering
→ aplicar Billing Ledger e/ou comando de Subscription Engine
→ marcar PROCESSED
→ em falha retryable: FAILED_RETRYABLE
→ após limite: DEAD_LETTER
→ replay administrativo controlado

### Provider-neutral normalization
O domínio central não interpreta payload proprietário.
Cada adapter deve converter webhook validado em evento normalizado canônico.

Evento normalizado mínimo:
- provider_code
- provider_account_id
- external_event_id
- canonical_event_type
- occurred_at UTC
- provider_sequence opcional
- external_subscription_ref opcional
- external_transaction_ref opcional
- internal subscription_id quando resolvido
- transaction status/type quando aplicável
- amount/currency quando aplicável
- period_start/period_end quando aplicável
- metadata_safe sem segredo.

### Billing Ledger mínimo
Persistir estado canônico interno de transações financeiras suficiente para:
- payment success/failure;
- refund quando aplicável;
- external transaction reference;
- assinatura interna vinculada;
- status atual;
- amount/currency;
- last provider event/sequence/time;
- version;
- reconciliation status/timestamps.

IDs externos nunca substituem IDs internos.

### Inbox status
- RECEIVED
- VERIFIED
- PROCESSING
- PROCESSED
- FAILED_RETRYABLE
- DEAD_LETTER
- IGNORED_OUT_OF_ORDER
- REJECTED

### Regras críticas
- assinatura forjada nunca altera estado financeiro/assinatura;
- event ID duplicado + mesmo body hash é idempotente;
- event ID duplicado + body hash diferente é replay conflict e falha fechado;
- evento mais antigo que cursor já aplicado não pode regredir estado;
- provider resend não duplica efeitos;
- retry automático somente para erro classificado retryable e com limite explícito;
- DEAD_LETTER exige ação/replay governado;
- replay não ignora assinatura/idempotência/ordering;
- reconciliation consulta o provider pela abstração KCA-09 e repara divergência de ledger de forma auditada;
- qualquer mutação de assinatura usa Subscription Engine canônico;
- nenhuma tabela operacional do Kordena é gravada diretamente;
- sem provider real;
- sem credencial real;
- sem cobrança real;
- sem KCA-11 paywall/recovery/dunning.

### Persistência
Usar próxima migration livre real após 0057, se CURRENT confirmar.
Migration aditiva e versionada.
Atualizar runner, manifest, schema baseline e testes de sequência.

### Testes obrigatórios do cronograma
- duplicate webhook;
- forged signature;
- event out of order;
- timeout;
- provider resend;
- reconciliation repairs state.

### Testes adicionais obrigatórios
- event ID collision com body diferente;
- retry → processed;
- retry exhaustion → DLQ;
- replay controlado;
- assinatura não exposta/logada;
- provider account desabilitada ou sem webhook capability;
- ambiente/binding incompatível;
- cross-provider event binding;
- normalized event inválido;
- transaction ledger idempotente;
- optimistic concurrency;
- subscription transition via canonical service;
- KCA-11 não antecipado.

### Gate KCA-G10
PASS somente com:
- migration/manifest/schema verdes;
- targeted KCA tests verdes;
- regressão Python completa verde;
- Web/TypeScript/build verde;
- security/fitness verdes;
- CI obrigatório 100% verde;
- implementation record e tracker reconciliados.

### Estado final
- PR permanece OPEN/DRAFT;
- nenhum merge;
- nenhum deploy;
- main não alterada;
- nenhum provider/credencial/cliente/cobrança real;
- KCA-11 NÃO INICIADO.
