# ADR-KCA-008 — Billing Provider Abstraction
Status: ADOTADO

## Decisão
Subscription/Billing usa um contrato interno provider-neutral. IDs de Cakto, Mercado Pago, Stripe ou outro provider permanecem referências externas.

Billing da Nova FM é separado dos pagamentos operacionais dos estabelecimentos.

## Consequências
Provider pode ser trocado sem redefinir customer/subscription/entitlement.

## Implementação
Pertence aos KCA de billing, não ao KCA-01.
