# ADR-KCA-010 — INTERNAL_TEST fora de KPIs comerciais
Status: ADOTADO

## Contexto
Antes da abertura pública haverá apenas identidade interna do Diretor para homologação.

## Decisão
A conta comercial possui classificação explícita; `INTERNAL_TEST` nunca alimenta clientes comerciais, trials, conversão, MRR, ARR ou churn.

A classificação não é mecanismo de autorização.

## Consequências
Homologação não contamina indicadores da empresa.

## Implementação
KCA-01 cria a classificação; o usuário interno só será criado na fase de homologação.
