# Kordena V1 — Legal Versioning & Acceptance Trail

**Estado:** CERTIFICADO — PASS
**Data:** 02/10/2026
**PR de implementação/certificação:** #177
**Merge SHA:** `eac2292cd6699e00552af2a867daaab0f66911e1`

## Autoridade

A PR #171 continua sendo a fonte única do texto jurídico:

- Terms 1.0: docs/legal/01_TERMOS_DE_USO_KORDENA_V1.md
- Privacy 1.0: docs/legal/02_POLITICA_PRIVACIDADE_LGPD_KORDENA_V1.md
- DPA 1.0: docs/legal/03_DPA_TRATAMENTO_DADOS_KORDENA_V1.md

core/comercial/legal.py define versão, vigência, rota pública e natureza da manifestação. O SHA-256 é calculado sobre o conteúdo real desses arquivos.

## Superfícies públicas

- GET /v1/public/legal/documents
- GET /v1/public/legal/documents/{terms|privacy|dpa}
- /legal/termos
- /legal/privacidade
- /legal/dpa

As páginas jurídicas são públicas e não passam pelo Auth Guard, Commercial Access Guard ou shell autenticado.

## Jornada

/signup consulta as versões ACTIVE e mostra links e versões reais. No envio, o frontend manda versão e SHA-256 dos três documentos. O backend recalcula a autoridade vigente e falha fechado se faltar documento, versão ou hash divergir.

A criação do signup grava eventos append-only no ledger comercial:

- commercial.legal.accepted — Termos;
- commercial.legal.acknowledged — Privacidade;
- commercial.legal.incorporated — DPA;
- commercial.signup.optional_consent.recorded — marketing opcional.

Cada evento jurídico preserva signup_id, correlation_id, tipo, versão, SHA-256, rota pública, natureza da manifestação e timestamp.

## Separação de consentimentos

Marketing permanece opcional e independente. O backend rejeita chaves desconhecidas em consents para impedir que aceite jurídico seja misturado com consentimento comercial.

## Evidência de certificação

A PR #177 foi certificada no HEAD `58fefed17a3025d72b8355113f6325442c00b8ee` com a matriz aplicável integralmente verde antes do merge:

- 15/15 workflows concluídos com `SUCCESS`;
- 0 workflows com falha;
- Kordena Legal Acceptance V1: `SUCCESS`;
- Kordena KCA16 Full Commercial E2E: `SUCCESS`;
- Kordena KCA17 Final Readiness: `SUCCESS`;
- Vercel da PR: `SUCCESS`.

A PR #177 foi mergeada em `staging/kordena-premium` no SHA `eac2292cd6699e00552af2a867daaab0f66911e1`.

No pós-merge do mesmo SHA:

- Vercel: `SUCCESS`;
- Railway deployment `acc5cbb9-b61f-4966-8c22-d6135a659af7`: `SUCCESS`;
- branch implantada: `staging/kordena-premium`.

A certificação acima é evidência técnica e operacional do pacote jurídico/versionamento/aceite. Ela não declara parecer jurídico externo por profissional habilitado.

## Gates

```text
LEGAL_TERMS_READY = PASS
LEGAL_VERSIONING_PASS = PASS
LEGAL_ACCEPTANCE_TRAIL_PASS = PASS
PRIVACY_DISCLOSURE_PASS = PASS
OPTIONAL_CONSENT_SEPARATION_PASS = PASS
```

Esses gates estão encerrados com evidência da PR #177, do merge e do pós-merge.
