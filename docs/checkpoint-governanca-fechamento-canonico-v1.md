# Checkpoint — Governança de Fechamento Canônico V1

Data: 05/09/2026

## Decisão do proprietário

A partir desta decisão, nenhuma fase seguinte da GERENTE AI V1 começa sobre uma fase anterior apenas tecnicamente verde, porém ainda não integrada/reconciliada.

## Gate obrigatório antes da próxima fase

1. SHA final fixado.
2. 100% dos gates da fase e regressões transversais aplicáveis em SUCCESS.
3. Zero failed/cancelled/queued/in_progress no conjunto exigido.
4. Correção e reexecução de qualquer vermelho sem enfraquecer fitness, evidências ou invariantes.
5. Readiness, Documento Mestre, Inventário Mestre, checkpoint, issue e PR reconciliados.
6. PRs/branches históricas classificadas; nenhum delta útil esquecido fora da main.
7. Dependências externas/físicas registradas explicitamente quando não executáveis.
8. Merge da PR canônica.
9. CI de push/pós-merge da main 100% verde.
10. Somente então liberar a próxima fase.

## Autorização permanente de merge

O proprietário autoriza o merge normal da PR canônica de uma fase sem nova pergunta quando o Gate de Fechamento Canônico acima estiver integralmente comprovado.

Esta autorização não inclui deploy, force push, exclusão destrutiva de dados reais, migration produtiva irreversível, transação financeira real, disparo massivo real ou ampliação de privilégios.

## Ordem final da V1

- concluir todas as fases funcionais e cutovers;
- executar homologação final e fechar/classificar dependências externas e físicas;
- executar **Visual Premium como a última fase funcional da V1**;
- somente depois configurar/validar o servidor real;
- deploy/release é pós-funcional e mantém autorização específica separada.

## Fontes oficiais sincronizadas

- Documento Mestre no Google Drive: `GERENTE_AI_V1_PROTOCOLO_MESTRE_DE_EXECUCAO`.
- Inventário Mestre no Google Drive: `GERENTE AI V1.0 — INVENTÁRIO MESTRE DE EXECUÇÃO CHAT × WORK — 2026-08-23`.
- `AGENTS.md` do repositório.

Nenhum deploy é executado por este checkpoint.
