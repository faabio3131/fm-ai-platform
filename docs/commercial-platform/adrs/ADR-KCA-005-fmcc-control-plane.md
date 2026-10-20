# ADR-KCA-005 — FM Control Center como Control Plane
Status: ADOTADO

## Decisão
O FM Control Center consolida read models e emite comandos administrativos governados para as autoridades canônicas.

Ele não grava diretamente em tabelas operacionais do Kordena e não participa do hot path obrigatório de cada operação.

## Consequências
O FMCC pode administrar clientes, planos, preços, trials, assinaturas e métricas sem virar segunda fonte de verdade.
