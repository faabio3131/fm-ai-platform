# KCA-14 — Security Hardening + Tenant Isolation Audit

## Status

**IN PROGRESS — candidate ainda não certificado.**

Base canônica pós-KCA-13:

`staging/kordena-premium@c8374e187bbcf782274e2c4e07f76283a1ad34cd`

Branch:

`feat/kordena-kca14-security-hardening`

Migration: **não aplicável**. O CURRENT já contém as autoridades de auth/session/RBAC/comercial; o KCA-14 endurece e certifica essas fronteiras sem criar segunda autoridade.

## CURRENT reconciliado

- sessão web `fm_ai_session` assinada e server-side;
- rotação de session id em troca de unidade, troca de membership e admin step-up;
- cookie HttpOnly, SameSite=Lax e Secure em runtime comercial;
- cookie inválido não faz downgrade para Basic Auth;
- headers X-Tenant-ID/X-Unit-ID não sobrescrevem sessão assinada;
- membership switch restringido à mesma Global Identity e product_code;
- autorização deny-by-default com tenant/unidade antes de permissão;
- admin step-up individual e revogado em mudança de unidade/membership;
- Public Signup com payload extra proibido, anti-enumeration e rate limit;
- Product Account/Subscription/Entitlement com validações de tenant;
- Billing Webhook com assinatura provider-neutral, inbox durável, body hash, replay protection, ordering e DLQ;
- FMCC server-to-server com token mínimo, compare_digest, step-up e idempotência;
- KCA-13 observability read-only, INTERNAL_TEST excluído e isolamento cross-product.

## Delta KCA-14

Nenhuma regra comercial nova. Foram adicionadas provas adversariais para gaps de certificação:

- session fixation;
- session replay após unit switch;
- session replay após membership switch;
- session replay após admin step-up;
- expired session;
- cookie/CORS/CSRF posture;
- Tenant A -> B write em Salão;
- duplicate webhook idempotente;
- replay webhook com mesmo event_id e body divergente;
- price race por expected version stale;
- promotion race por expected version stale;
- subscription race por expected version stale.

O gate KCA Commercial passa a executar uma etapa explícita `KCA-14 adversarial security matrix`.

## Matriz adversarial

| Cenário | Evidência |
|---|---|
| Tenant A -> B read | mapa Salão + RBAC/IDOR cross-tenant existentes |
| Tenant A -> B write | novo teste HTTP Salão |
| Unit A -> B não autorizada | auth select-unit + F14 IDOR cross-unit |
| forged tenant_id / unit_id | sessão ignora headers; Basic valida escopo; Public Signup extra=forbid |
| forged product_account_id | Subscription/Entitlement tenant-product-account mismatch fail-closed |
| membership escalation | KCA-02 HTTP membership ownership |
| RBAC/admin escalation | F14 + admin step-up HTTP |
| step-up bypass | admin mutations exigem step-up |
| fixation/replay/expired | nova suíte KCA-14 de sessão |
| invalid cookie / Basic downgrade | operational SSO contract |
| duplicate signup/provisioning | KCA-05/KCA-06 idempotência |
| duplicate/forged/replay/out-of-order webhook | KCA-10 + novos HTTP replay tests |
| stale/missing/old entitlement | KCA-04/KCA-11 |
| price/promotion/subscription race | novos testes de optimistic concurrency |
| billing spoof | forged signature + unknown provider |
| cross-product contamination | KCA-13 Kordena × IRON |
| INTERNAL_TEST contamination | KCA-13 exclusion + Public Signup -> TRIAL |
| frontend/direct API bypass | backend RBAC + admin boundary tests |
| FMCC unauthorized mutation | KCA-12 control-plane auth/step-up |
| secret leakage | SecretStore/session guard + webhook non-echo |

## Gate

KCA-G14 somente poderá ser marcado PASS quando:

- adversarial matrix = PASS;
- targeted KCA = PASS;
- full Python = PASS;
- Web lint/TypeScript/tests/build = PASS;
- schema/migrations = PASS;
- required CI = 100% SUCCESS;
- audit final encontrar **CRITICAL OPEN = 0** e **HIGH OPEN = 0**;
- HEAD exato for recertificado;
- merge em staging e pós-merge forem verdes.
