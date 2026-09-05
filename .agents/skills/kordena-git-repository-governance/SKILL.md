---
name: kordena-git-repository-governance
description: Governa Git, branches, worktrees, commits, PRs, preservação e sincronização do Coordena. O nome da skill é um identificador técnico legado preservado por compatibilidade. Use ao criar ou trocar branch, stagear, commitar, fazer push, reconciliar PRs, trabalhar com Work Cloud, GitHub ou VS Code físico, e sempre que houver worktree dirty.
metadata:
  version: "1.0.2"
  project: "kordena-gerente-ai"
  canonical_product: "coordena"
---

# Coordena Git & Repository Governance

> Compatibilidade: o diretório e o campo `name` ainda usam `kordena-git-repository-governance` como identificador técnico legado. A marca comercial canônica é **Coordena**.

## Objetivo

Evitar perda de patrimônio, branches divergentes, merges cegos e código crítico preso em ambiente efêmero.

## Autoridades

- O GitHub remoto é a autoridade factual para branches remotas, PRs, merges, `main` remoto e SHAs efetivamente publicados.
- O repositório local verificado é a autoridade factual para branches locais, commits não publicados, worktrees, staged/untracked e estado dirty.
- Quando local e remoto divergirem, reconcilie por SHA, ancestralidade e proveniência; não descarte checkpoint local legítimo apenas porque ainda não existe no remoto.
- A instrução/gate explicitamente autorizado pelo proprietário e os documentos vigentes governam **se** uma integração pode acontecer; conflito ambíguo exige STOP e reconciliação.
- O proprietário mantém decisão final sobre integração na linha canônica, merge em `main`, deploy e migração produtiva.

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
- Commit deve representar um checkpoint/gate coerente e testado na extensão aplicável ao ambiente atual.
- Um commit necessário para CI ou reprodução física não prova sozinho a aprovação do gate; registre as validações ainda pendentes.
- Antes do commit, rode os testes mínimos localmente disponíveis definidos pela Skill de validação.

## Worktrees

- Use worktree separado quando houver branches dirty ou frentes independentes.
- Não repurpose terminal/worktree reservado para outra frente.
- Não execute `reset`, `clean`, `restore` ou checkout destrutivo sobre worktree dirty sem backup + autorização explícita.
- Se um comando foi executado no terminal errado, primeiro audite branch/pasta/status; não tente “desfazer” no impulso.

## Work Cloud e Codex Local

Work Cloud não é armazenamento de longo prazo.

Fluxo preferencial quando o ambiente possui autenticação Git:

1. Work/agent executa tarefa isolada e produz evidência.
2. Gate técnico é revisado.
3. Checkpoint aprovado vira branch/commit rastreável.
4. GitHub recebe o checkpoint sem force push.
5. VS Code/PC físico recebe exatamente o mesmo SHA.
6. Testes/runtime físicos são executados.
7. Somente depois o bloco pode seguir para homologação final.

Se o Work não puder autenticar Git, não contorne credenciais. Transfira por artefato verificável (bundle/patch/snapshot) ao ambiente físico autenticado, confira SHA/proveniência e publique a partir dele. A ausência temporária do checkpoint no GitHub não invalida a linha local comprovada.

## Branch canônica

- Deve existir uma única linha canônica de evolução da V1 quando ela tiver sido explicitamente estabelecida.
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

- Criar branch, commit ou push não autoriza integração na linha canônica nem merge em `main`.
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
- autorização vigente do proprietário conforme `AGENTS.md`.

A autorização permanente registrada em `AGENTS.md` permite merge normal da PR canônica quando 100% dos gates aplicáveis estiverem verdes e reconciliados. Ela não autoriza deploy nem atos destrutivos/sensíveis.

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
