# ADR-KCA-007 — Entitlement local projetado
Status: ADOTADO; IMPLEMENTAÇÃO KCA-04

## Decisão
A FM Commercial Platform calcula entitlement comercial. Cada produto mantém projeção local versionada para não depender de chamada síncrona ao FMCC em cada request.

## Regras
Revisões antigas não podem sobrescrever novas; ausência/estado desconhecido não concede FULL; last-known-good usa política explícita de validade.

## Consequências
Maior disponibilidade com consistência eventual controlada.
