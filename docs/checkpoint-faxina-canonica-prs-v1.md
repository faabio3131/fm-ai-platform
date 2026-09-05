# Checkpoint — Faxina Canônica de PRs e Patrimônio V1

**Data operacional:** 2026-09-04 (America/Sao_Paulo)  
**Objetivo:** remover falsas pendências de branches/PRs antigas, integrar patrimônio realmente concluído e preservar requisitos ainda válidos antes de continuar a V1.

## 1. Integrações corrigidas nesta faxina

### Fase 10 — Expedição / Entregador
- PR #81: **MERGED**;
- merge commit: `ace003d3340620047124d4220972978323fa690f`;
- F10-A..F10-E fechadas tecnicamente/documentalmente antes do merge;
- matriz final do HEAD documental: 29/29 verde;
- nenhum deploy.

### Fase 9 — Impressão Operacional
- PR #79: **MERGED** durante esta faxina;
- merge commit: `58b2c75b653130420c0a07912591beec94899059`;
- integrou F9-D/F9-E: adapter RAW TCP/JetDirect, configuração durável, UI comercial, composition KDS->spool->adapter e Commercial Runtime E2E;
- pendência física da impressora continua explícita para homologação final;
- `physical_test` não é fabricado e o blocker físico não é removido;
- pós-merge na `main`: **5/5 workflows de push concluídos com sucesso**, zero queued/in-progress/failure;
- nenhum deploy.

## 2. PRs encerradas como superseded/absorvidas

As PRs abaixo foram encerradas sem merge direto nesta faxina porque a linha atual já absorveu/evoluiu seu patrimônio ou porque a branch se tornou historicamente perigosa para merge:

- #78 — Fase 9 alternativa F9-A; substituída por #76 + #79;
- #64 — Recovery Fase 4; HEAD comprovadamente ancestral da `main` (ahead 0);
- #63 — primeira versão do Commercial Runtime Readiness; substituída pelo gate atual evoluído;
- #59 — correção antiga de login; linha absorvida, requisito VOICE preservado separadamente;
- #58 — antiga linha canônica de estabilização; absorvida por recovery/cutovers posteriores;
- #57 — Administração/Integrações; HEAD comprovadamente ancestral da `main` (ahead 0);
- #52 — antiga Onda 2 de restaurante; substituída pelos cutovers F7–F9;
- #50 — antiga Onda 1 transacional/PagBank; substituída pela Fase 6+; blocker externo do PagBank permanece documentado;
- #49 — antiga Onda 0 de runtime/segurança; substituída pela baseline e Fases 5–10;
- #48 — correção antiga de Mica empilhada na branch visual; Assistente evoluiu pela Fase 4+;
- #47 — implementação visual histórica; não deve ser mergeada diretamente sobre a `main` atual.

**Política aplicada:** fechar PR superseded não apaga histórico Git nem autoriza exclusão de evidência. Nenhuma dessas branches foi usada como fonte de verdade após a classificação.

## 3. Patrimônio recuperado antes do encerramento

### VOICE-V1
Foi recuperado para a linha canônica:
- `docs/VOICE_V1_SCOPE_CORRECTION.md`.

A voz assistiva do Gerente IA continua requisito funcional da V1 antes do fechamento funcional. Voz é interface, não nova autoridade; não amplia tenant/RBAC/permissões e não autoriza PDV/caixa automático por voz.

### Transformação visual premium
Foi preservada a direção do produto em:
- `docs/V1_PREMIUM_VISUAL_REFERENCE.md`.

A antiga implementação visual não será transplantada. A transformação visual premium final deverá ser reconstruída sobre a `main` funcionalmente fechada, preservando integralmente domínio, persistência, integrações, RBAC e contratos E2E.

## 4. Pendências deliberadamente preservadas

Esta faxina **não** transforma dependência externa em conclusão fictícia. Permanecem para homologação/fase final conforme os inventários canônicos:

- PagBank — homologação/configuração externa real;
- Mercado Pago — homologação/configuração externa real;
- Meta/WhatsApp — homologação/configuração externa real;
- Impressora física — prova em hardware real;
- demais blockers externos que o `commercial_runtime_readiness_v1.json` mantiver explicitamente.

Também permanecem como trabalho V1 futuro, não como PR velha aberta:

- VOICE-V1;
- transformação visual premium final após fechamento funcional.

## 5. Estado do backlog após a limpeza

Após os encerramentos desta rodada, a única PR aberta é a PR de manutenção/faxina canônica que carrega este checkpoint e os dois documentos recuperados.

Isso elimina a ambiguidade entre:
- código já integrado;
- branch histórica;
- dependência externa;
- requisito futuro ainda legítimo.

## 6. Regra para as próximas fases

A partir deste checkpoint:

1. cada fase/bloco fechado deve ter decisão explícita de integração ou supersessão antes de avançar muitas fases;
2. PR tecnicamente fechada não pode ficar indefinidamente aberta sem classificação;
3. branches antigas nunca devem ser mergeadas por título/status apenas — comparar contra `main` e validar patrimônio primeiro;
4. requisitos válidos encontrados em branch superseded devem ser preservados na linha canônica antes do encerramento;
5. todo merge funcional exige gates verdes e validação pós-merge proporcional;
6. deploy permanece uma autorização separada.

## 7. Estado operacional

**FAXINA CANÔNICA: CONCLUÍDA TECNICAMENTE, aguardando apenas o CI/merge do checkpoint documental.**

Nenhum deploy foi executado.