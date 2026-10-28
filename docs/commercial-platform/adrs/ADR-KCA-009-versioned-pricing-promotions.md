# ADR-KCA-009 — Pricing e promoções versionados
Status: ADOTADO

## Decisão
Preço-base, versão de plano e promoção são entidades históricas. Promoção é overlay e não sobrescreve preço-base.

Mudança de preço declara política de efeito sobre assinantes existentes.

## Consequências
Auditoria, previsibilidade contratual, agendamento e rollback lógico sem reescrever histórico.

## Implementação
Pertence ao KCA-03.
