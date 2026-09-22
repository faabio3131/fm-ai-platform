# ADR-KCA-006 — Saga + Outbox/Inbox
Status: ADOTADO

## Contexto
Provisioning e sincronização cruzam Commercial Platform e produtos.

## Decisão
Usar Saga/state machine para processos multi-contexto e Outbox/Inbox para eventos idempotentes. Não usar 2PC distribuído.

## Consequências
Consistência entre contextos é eventual e observável; retries, compensação e reconciliação são explícitos.

## KCA-01
Outbox transacional registra eventos mínimos; provisioning completo fica para KCA posterior.
