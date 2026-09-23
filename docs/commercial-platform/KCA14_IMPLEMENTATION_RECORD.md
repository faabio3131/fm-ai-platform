# KCA-14 — Security Hardening + Tenant Isolation Audit — Implementation & Certification Record

## Base e escopo

- Base: `staging/kordena-premium@c8374e187bbcf782274e2c4e07f76283a1ad34cd`.
- Branch: `feat/kordena-kca14-security-hardening-tenant-isolation`.
- PR: #133.
- Visual Premium: fora do escopo.
- Objetivo: elevar o hardening de auth/session/RBAC/tenant/unit/commercial/webhook/FMCC a gate explícito da linha canônica de staging.

## Delta

1. `tests/api/test_operational_session_sso_http_contract.py`
   - impede Basic Auth legado com tenant forjado;
   - impede Basic Auth legado com unidade forjada;
   - impede replay de token antigo depois de rotação de sessão por troca de unidade.
2. `tests/fitness/test_kca14_security_hardening.py`
   - fitness contract das fronteiras de sessão, CORS comercial, FMCC, webhook e matriz de segurança KCA.
3. `.github/workflows/kordena-kca-commercial-gate.yml`
   - matriz adversarial passa a ser parte explícita do KCA targeted gate.
4. `.github/workflows/auth-rbac-commercial-gate-v1.yml`
   - passa a certificar PRs contra `staging/kordena-premium`;
   - inclui matriz KCA-14, HTTP session/RBAC, webhook e FMCC.

Nenhuma migration nova.

## Evidência do candidate

Candidate: `c9435f5af7f205457787a592d4a2e885f0f3ec0d`.

- Auth/RBAC targeted: 104 passed, 1 warning.
- Full Python: 1819 passed, 5 skipped, 101 warnings.
- KCA targeted: 254 passed, 1 warning.
- Web Node: 16 passed, 0 skipped.
- Ruff/mypy: PASS.
- Migration manifest/schema baseline: PASS.
- Next production build: PASS.
- Auth/RBAC Gate #29: SUCCESS.
- KCA Commercial Gate #299: SUCCESS.
- WP-031 Master #307: SUCCESS.
- WP-031L #317: SUCCESS.
- Cleanup #845: SUCCESS.
- Vercel: SUCCESS.

## Findings

- CRITICAL OPEN: 0.
- HIGH OPEN: 0.
- O primeiro Auth/RBAC run #28 falhou somente no fitness contract de cobertura: o contrato exigia nomes individuais de arquivos que já eram executados pelo diretório canônico `tests/integration/comercial`. A asserção foi corrigida para refletir a cobertura real; nenhum teste de segurança foi removido ou enfraquecido.
- O workflow histórico Auth/RBAC só observava PRs contra `main`; foi corrigido para também observar `staging/kordena-premium`, eliminando lacuna de certificação da linha KCA.

## Gate

KCA-G14 = PASS no candidate funcional. O HEAD documental criado por este registro deve ser recertificado 100% antes do merge, e o staging deve ser verificado pós-merge antes de iniciar KCA-15.
