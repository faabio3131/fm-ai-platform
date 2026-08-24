---
name: kordena-git-repository-governance
description: Governa Git, branches, worktrees, commits, PRs, preservação e sincronização do Kordena/GERENTE AI. Use ao criar ou trocar branch, stagear, commitar, fazer push, reconciliar PRs, trabalhar com Work Cloud, GitHub ou VS Code físico, e sempre que houver worktree dirty.
metadata:
  version: "1.0.0"
  project: "kordena-gerente-ai"
---

# Kordena Git & Repository Governance

## Objetivo

Evitar perda de patrimônio, branches divergentes, merges cegos e código crítico preso em ambiente efêmero.

## Autoridades

- GitHub remoto é a autoridade factual para branches, SHA, PRs, merges e `main`.
- Documento Mestre/System Design governam **se** uma integração é autorizada.
- O proprietário mantém decisão final sobre merge em `main`, deploy e migração produtiva.

## Antes de qualquer operação Git mutável

Registre:

- `pwd` / raiz do repositório;
- branch atual;
- `git rev-parse HEAD`;
- `git status --short`;
- staged/untracked;
- remotes;
- worktree atual e outros worktrees quando relevante.

Se o usuário possui worktree dirty não reconciliado, trate-o como patrimônio. Não sobrescreva.

## Staging e commits

- **Nunca use `git add -A` nem `git add .`.**
- Stage somente paths ou hunks explícitos pertencentes ao gate atual.
- Arquivo misto exige seleção por hunk ou reconstrução mínima comprovada.
- Não crie commit vazio para simular progresso.
- Commit deve representar um gate/capacidade coerente e testada.
- Antes do commit, rode os testes mínimos definidos pela Skill de validação.

## Worktrees

- Use worktree separado quando houver branches dirty ou frentes independentes.
- Não repurpose terminal/worktree reservado para outra frente.
- Não execute `reset`, `clean`, `restore` ou checkout destrutivo sobre worktree dirty sem backup + autorização explícita.
- Se um comando foi executado no terminal errado, primeiro audite branch/pasta/status; não tente “desfazer” no impulso.

## Work Cloud e Codex Local

Work Cloud não é armazenamento de longo prazo.

Fluxo preferencial:

1. Work/agent executa tarefa isolada e produz evidência.
2. Gate técnico é revisado.
3. Checkpoint aprovado vira branch/commit rastreável.
4. GitHub recebe o checkpoint sem force push.
5. VS Code/PC físico recebe exatamente o mesmo SHA.
6. Testes/runtime físicos são executados.
7. Somente depois o bloco pode seguir para homologação final.

Se o Work não puder autenticar Git, não contorne credenciais. Transfira por artefato verificável (bundle/patch/snapshot) e publique pelo ambiente físico autenticado.

## Branch canônica

- Deve existir uma única linha canônica de evolução da V1 após estabilização.
- Toda nova frente parte do SHA canônico explicitamente registrado.
- Não acumule vários gates aprovados somente em detached HEAD.
- Após gate aprovado, faça checkpoint antes de abrir grande bloco seguinte.
- Não misture feature pendente com infraestrutura aprovada no mesmo commit sem decisão explícita.

## PRs históricas

PR aberta não significa “mergear”. Antes, classifique:

- `INCORPORADA` — patrimônio já existe na linha canônica;
- `PARCIALMENTE INCORPORADA` — apenas diferenças únicas merecem seleção;
- `AINDA NECESSÁRIA` — precisa integração controlada;
- `SUPERSEDED/OBSOLETA` — não integrar;
- `REFERÊNCIA` — preservar para consulta futura.

Nunca faça merge sequencial cego de PRs divergentes. Compare por capacidade e diff.

## Push e remotes

- Confirme remote e repositório exatos antes do push.
- Nunca force push em fluxo normal.
- Não altere `main` por efeito colateral.
- Se um `origin` for bundle/forense, preserve-o e use remote operacional separado em vez de destruir a trilha forense.
- Após push, confirme SHA local = SHA remoto.

## Preservação

Antes de reorganização relevante, preserve proporcionalmente:

- patch `git diff --binary` para tracked dirty;
- manifesto/archive de untracked;
- bundle de histórico quando necessário;
- SHA-256 dos artefatos críticos;
- prova de restauração para snapshots de alto risco.

Backups não substituem Git, e Git bundle não contém alterações não commitadas por si só.

## Merge em main

Só considerar após:

- gate técnico aprovado;
- branch publicada e SHA conferido;
- reprodução/testes físicos quando exigidos;
- PR revisada;
- proprietário autorizar explicitamente.

Sem autorização, pare antes do merge.

## Relatório de operação Git

Registre sempre:

- branch/SHA inicial e final;
- arquivos staged/committed;
- commit(s) criado(s);
- remote usado;
- SHA remoto quando houver push;
- status final;
- worktrees preservados;
- operações proibidas que não foram realizadas.
