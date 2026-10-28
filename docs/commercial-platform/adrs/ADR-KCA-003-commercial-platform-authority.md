# ADR-KCA-003 — FM Commercial Platform como autoridade
Status: ADOTADO

## Decisão
Customer Registry, Product Accounts, catálogo, pricing, promoções, trial, subscription, billing, entitlement e provisioning pertencem à FM Commercial Platform compartilhada.

Cada SaaS preserva autoridade sobre seu domínio operacional.

## Rejeitado
Implementar trial/billing separadamente dentro de cada SaaS.

## Consequências
Reuso entre Kordena, Iron e produtos futuros; boundaries e eventos devem permanecer explícitos.

## Rollback
Componentes podem ser desabilitados por capacidade sem alterar dados operacionais dos SaaS.
