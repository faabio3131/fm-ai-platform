# Kordena — Plano de homologação isolada no Render Hobby (rascunho)

**Situação:** PREPARAÇÃO — sem autorização para cutover comercial, merge ou criação de recursos pagos.
**Workspace:** My Workspace (`tea-dabhel5cqm1c73dkkn90`).
**Base Git:** `faabio3131/fm-ai-platform`, branch `main` na criação deste rascunho.

## 1. Intenção e isolamento

Criar homologação completa com **um único domínio público** de acesso, mantendo dois processos independentes: Next.js (UI) e FastAPI (API). Usar roteamento same-origin por proxy com caminhos explícitos; nunca substituir backend oficial por servidor do harness de testes.

- Não alterar serviços atuais `kordena-ops-demo-web` e `kordena-ops-demo-api`; estes são demonstrativos e usam SQLite em memória.
- Não reutilizar `fmcc-preview-postgres` (outro produto, banco gratuito com expiração).
- Não copiar credenciais, tenants, dados ou chaves da produção para homologação.
- Não modificar projeto Vercel, DNS comercial, `main`, secret store de produção ou permissões.
- Nenhum provisionamento de banco/serviço pago sem aprovação expressa do custo confirmado no Render.

## 2. Contratos já confirmados no código

- Frontend `web/`: Next.js; API client usa `NEXT_PUBLIC_API_URL`; valor `__SAME_ORIGIN__` é suporte de demonstração existente e **não configura sozinho** um backend comercial.
- API: `http_api/frontend_app.py:build_frontend_http_app` monta o runtime e a Central de Pedidos; CORS de staging/produção permanece restrito, portanto preferir same-origin.
- `core/runtime/config.py`: staging requer `DATABASE_URL`, `FM_AI_TENANT_ID` e `FM_AI_UNIDADE_ID`; SQLite não é permitido comercialmente por padrão.
- Cookie assinado, RBAC e isolamento por tenant/unidade não podem ser relaxados.
- `tests/api/serve_central_operacoes_e2e.py` é exclusivo do cenário E2E e **não pode** ser o servidor de homologação real.

## 3. Plano por gates (STOP em qualquer falha)

### H01 — Design executável

1. Confirmar pricing, duração/expiração, persistência, backup e limites de Postgres e serviços Hobby.
2. Definir serviços de homologação com nomes próprios, auto-deploy desligado e branch exclusiva de release.
3. Definir arquitetura proxy same-origin para `/v1/*`, health checks e tratamento explícito de cookies/HTTPS. Não expor FastAPI sem controle de acesso se o proxy permitir ingress interno.
4. Definir mapeamento seguro de segredos/credenciais por ambiente, sem gravar valores no Git.

### H02 — Banco isolado e migrations

1. Criar PostgreSQL exclusivo após custo autorizado; executar migrations fresh e upgrade.
2. Verificar versão, transações, constraints e isolamento do tenant/unidade em PostgreSQL.
3. Demonstrar backup e restauração (ou documentar limitação de plano e STOP).
4. Criar conta de homologação individual e conjunto de dados sintéticos mínimos; não reutilizar usuário de teste público.

### H03 — Backend real

1. Montar entrypoint FastAPI canônico de staging com settings validados.
2. Testar `/health/live`, login, `/v1/auth/me`, `/v1/auth/unidades`, logout e cookies assinados sob HTTPS.
3. Validar sessão inválida, spoofing de tenant/unidade, RBAC, erros e observabilidade.

### H04 — Frontend e experiência

1. Conectar Next.js exclusivamente à API de homologação via proxy e expor só a URL escolhida.
2. Verificar login real, seleção de unidade, PDV, Salão, KDS, Central de Pedidos e Central de Operações.
3. Testar desktop e celular, 1/30/40/100 pedidos, página longa, polling e limite de 100 consultas.
4. Registrar lacunas e comportamento de integrações externas ainda não homologadas.

### H05 — Certificação e decisão

1. CI frontend, backend, migrations, regressão, E2E navegador e smoke em ambiente Render; evidências e SHA fixados.
2. Revisar permissões, secrets, logs, quotas, cobrança, backup/restore e rollback.
3. PR revisada; merge somente após todos os gates verdes e aprovação explícita do proprietário.
4. Nenhum cutover de produção/DNS por implicação da certificação.

## 4. Registro de descobertas em 11/10/2026

- No Render, `My Workspace` contém os serviços demonstrativos `kordena-ops-demo-web` e `kordena-ops-demo-api`, ambos free.
- Existe somente `fmcc-preview-postgres` (free), pertencente ao FM Command, com `expiresAt` informado em 19/10/2026.
- O projeto Kordena usa Next.js, FastAPI e configuração de runtime que impede SQLite comercial sem exceção explícita.
- **Restrição oficial Render:** apenas **um PostgreSQL Free ativo por workspace**, já ocupado pelo FM Command. Banco PostgreSQL Free tem validade de 30 dias e não tem backups. Fonte: https://render.com/docs/free .
- **Hobby:** workspace gratuito; serviços e bancos pagos são cobrados separadamente. Fonte: https://render.com/docs/new-workspace-plans .
- **Pendente:** confirmação da cotação exata no painel e disponibilidade de recursos de backup de um banco pago exclusivo; não provisionar antes da aprovação.

## 5. Critério de segurança

Toda mudança deve ser feita em branch separada com testes e diffs pequenos. Segredos fora do repositório. Falhar fechado, sem fallback silencioso, sem tocar em produção e sem apagar demonstração atual.
