# Coordena — Migração Controlada de Identidade V1

## Decisão canônica

A partir deste checkpoint, **Coordena** é o nome comercial canônico do produto.

Nomes históricos encontrados no patrimônio do projeto:

- `Kordena`;
- `GERENTE AI` / `Gerente AI`;
- `F&M AI FOOD`;
- `AI Food`.

Esses nomes não devem ser introduzidos novamente em superfícies comerciais novas.

## Princípio de segurança

A troca de marca não autoriza renomear indiscriminadamente identificadores técnicos. A migração é separada em três classes:

1. **Superfície comercial/ativa** — deve usar `Coordena`.
2. **Identificador técnico legado de compatibilidade** — permanece temporariamente quando a alteração puder quebrar imports, paths, automações, migrations, tabelas, variáveis de ambiente, testes, agentes ou integrações.
3. **Histórico/proveniência** — documentos, commits, ADRs e evidências históricas não são reescritos retroativamente apenas para apagar o nome antigo.

## Repositório

O slug `fm-ai-platform` permanece inalterado nesta etapa. Ele é neutro e renomeá-lo implicaria migração própria de remotes, GitHub Actions, integrações, documentação externa e ambientes físicos.

## Identificadores preservados por compatibilidade

Nesta primeira etapa são preservados, entre outros:

- variáveis e chaves `FM_AI_*`;
- módulos/nomes internos já estabilizados (`gerente_ia`, etc.);
- migrations, tabelas, IDs de sessão e contratos persistidos;
- identificadores históricos de documentos mestres;
- diretórios de skills:
  - `.agents/skills/kordena-system-design-guardian`;
  - `.agents/skills/kordena-validation-release-gate`;
  - `.agents/skills/kordena-git-repository-governance`.

As skills continuam descobertas pelos paths legados, mas seu conteúdo declara **Coordena** como identidade atual.

## Passagem 1 — identidade ativa segura

Escopo desta PR:

- criar `core/branding.py` como fonte canônica da identidade visual;
- migrar autenticação comercial para `Coordena`;
- migrar títulos das páginas Administração, Integrações, Garçom e Expedição/Entrega;
- atualizar `AGENTS.md` para a identidade canônica e para os paths reais das skills;
- atualizar o conteúdo humano das três skills;
- adicionar fitness gate de identidade para impedir regressão de marca nas superfícies já migradas.

## Passagem 2 — raiz legada `app.py`

`app.py` ainda contém textos históricos `F&M AI FOOD` em título, cabeçalhos e alertas. Como é um arquivo monolítico grande e o mecanismo conectado de edição substitui o arquivo inteiro, ele fica **explicitamente bloqueado para edição fragmentária insegura** nesta primeira passagem.

Critério para a Passagem 2:

- editar `app.py` preservando integralmente o arquivo e substituindo somente as ocorrências comerciais conhecidas pela fonte `core.branding`;
- provar compile/Ruff/regressão/E2E sobre o mesmo SHA;
- remover a exceção correspondente do fitness gate.

Não considerar a migração visual de marca integralmente fechada antes da Passagem 2.

## Proibido nesta migração

- renomear banco, tabelas ou migrations por estética;
- renomear variáveis `FM_AI_*` sem plano de compatibilidade;
- alterar source of truth de Pedido/Pagamento/Entrega;
- alterar tenant/unidade/RBAC;
- reescrever histórico Git;
- renomear o repositório automaticamente;
- executar deploy.

## Rollback

Rollback é o revert da PR desta migração. Não há migration de banco nem alteração destrutiva de dados.
