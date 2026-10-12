# Kordena — Render / homologação (NÃO produzir/cutover)

Este diretório contém apenas o entrypoint de FastAPI da homologação independente.
**Não é o harness E2E** e **não cria usuários ou pedidos**. O deploy depende dos
gates da PR #202 e de PostgreSQL próprio com custo previamente autorizado.

## Backend proposto

- Runtime: Python 3.12.
- Build (a partir da raiz): `pip install -r requirements.txt`.
- Start: `uvicorn ops.render.kordena_staging_asgi:app --host 0.0.0.0 --port \$PORT`.
- Health: `/healthz`.
- Variáveis obrigatórias (valores no secret manager Render, NUNCA neste repo):
  `FM_AI_ENV=staging`, `DATABASE_URL` PostgreSQL exclusiva,
  `FM_AI_TENANT_ID`, `FM_AI_UNIDADE_ID`; demais segredos do login
  precisam ser verificados contra o runtime canônico antes de ativar.
- O processo deliberadamente rejeita SQLite e ambientes development/test/production.

## Frontend proposto

- Build no diretório `web`; Next.js.
- `NEXT_PUBLIC_API_URL=__SAME_ORIGIN__` **somente** com o proxy de homologação
  `KORDENA_PREVIEW_PROXY=1` e `KORDENA_PREVIEW_BACKEND_URL=https://<API-ISOLADA>`.
- Essas flags permitem os caminhos `/v1/*`; antes do deploy devem ser avaliados
  também todos os outros endpoints, cookies assinados, redirects e healthchecks.
- Exposição pública da URL só após autenticação, RBAC e teste de HTTPS.

## Gates

1. Validar compatibilidade PostgreSQL e executar migrations fresh/upgrade.
2. Semear conta de homologação com credenciais individuais e protegidas.
3. Validar login, sessão, unidade, logout, central, KDS, Salão, PDV, saúde.
4. Testes funcionais de regressão no browser e prova no ambiente Render.
5. Não alterar Vercel, DNS, domínio comercial nem serviços demo.
