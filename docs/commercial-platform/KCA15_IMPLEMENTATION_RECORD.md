# KCA-15 — Homologação Interna Nova FM — Implementation & Certification Record

## Base

- Base canônica: `staging/kordena-premium@16975a52202ec6602499bb4981d85461977d9952`.
- Branch: `feat/kordena-kca15-internal-homologation`.
- PR: #134.
- Visual Premium: fora do escopo.
- Nenhum cliente externo real, cobrança real ou segredo persistido foi utilizado.

## Homologação real executada

A homologação foi executada em PostgreSQL 16 efêmero, com runtime `FM_AI_ENV=staging` e `FM_AI_TEST_MODE` explicitamente ausente.

A identidade de homologação foi persistida com:

- `account_class=internal_test`;
- Product Account KORDENA ativo;
- tenant dedicado de homologação;
- unidade dedicada de homologação;
- entitlement `commercial_state=internal_test`;
- `access_mode=full`;
- credenciais geradas apenas no runner e descartadas ao final.

## Jornada homologada

PASS:

- login;
- logout;
- tenant/unidade;
- admin step-up;
- PDV;
- Salão;
- KDS;
- Gerente IA;
- FMCC snapshot;
- FMCC Commercial Control Plane;
- administração governada de plano;
- criação governada de promoção;
- exclusão de INTERNAL_TEST dos KPIs comerciais.

## Evidência do candidate

Candidate técnico final: `ed79e7ca7f5f5b156e247f37d1c8143e6cc8fd37`.

### Kordena KCA15 Internal Homologation #7

- PostgreSQL staging runtime: PASS.
- Evidence contract KCA-G15: PASS.
- KCA-15 targeted regression: **49 passed, 1 warning**.
- Migration manifest: PASS.
- Schema baseline: PASS — 132 tabelas.
- Full Python regression: **1819 passed, 5 skipped, 101 warnings**.
- Billing real utilizado: **não**.
- Cliente externo real utilizado: **não**.

### WP-031 Master Gate #315

- Fiscal vendored baseline: PASS.
- WP-031 matrix: **114 passed, 4 warnings**.
- Canonical channels/payments/stock matrix: **182 passed, 69 warnings**.
- Security tenancy/RBAC/fail-closed matrix: **108 passed**.
- Full Python regression: **1819 passed, 5 skipped, 101 warnings**.
- Web Node: **16 passed, 0 skipped**.
- Next production build: PASS.

### Outros checks do HEAD

- PR Superseded Runs Cleanup #853: SUCCESS.
- Vercel: SUCCESS.
- Mergeable: true.

## Falhas encontradas e corrigidas durante o bloco

1. Ruff detectou import formatting no runner novo.
   - Corrigido sem redução de cobertura.
2. Uma correção intermediária gravou `\n` literal no import.
   - Corrigido e py_compile/Ruff/mypy passaram.
3. Runner não encontrava módulos do repositório via execução direta em `scripts/`.
   - Workflow passou a exportar `PYTHONPATH=.`.
4. O runner exigia `commercial_state` em `/v1/commercial/access`, campo que não pertence ao contrato HTTP.
   - Asserção alinhada ao contrato canônico: entitlement, access_mode e product_account.
5. A regressão global herdava o ambiente de homologação staging/PostgreSQL.
   - O step de full regression foi isolado do ambiente KCA-15, preservando a homologação real e restaurando o ambiente canônico da suíte global.

Nenhuma falha foi mascarada por skip/xfail ou remoção de teste.

## Gate

KCA-G15 = PASS no candidate técnico `ed79e7ca7f5f5b156e247f37d1c8143e6cc8fd37`.

Este registro documental gera novo HEAD e, portanto, deve ser recertificado antes do merge. Após merge, `staging/kordena-premium` deve receber verificação pós-merge antes da abertura do KCA-16.


### Recertificação documental

Após o candidate técnico `ed79e7ca7f5f5b156e247f37d1c8143e6cc8fd37` ficar 100% verde, este registro e o tracker foram atualizados para refletir o estado real. O commit documental resultante deve receber nova rodada completa de CI antes do merge, conforme a regra de certificação por SHA exato.
