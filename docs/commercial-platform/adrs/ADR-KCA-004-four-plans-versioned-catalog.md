# ADR-KCA-004 — Quatro planos estáveis + catálogo versionado
Status: ADOTADO

## Decisão
O Kordena possui exatamente quatro códigos comerciais estáveis:
`KORDENA_PLAN_A`, `KORDENA_PLAN_B`, `KORDENA_PLAN_C`, `KORDENA_PLAN_D`.

Nomes, preços, periodicidade, benefícios, limites e promoções são dados configuráveis e versionados.

## Rejeitado
Hardcode em frontend/backend e edição destrutiva de preço.

## Consequências
Mudanças comerciais não exigem deploy e histórico contratual permanece reproduzível.

## Implementação
Pertence ao KCA-03.
