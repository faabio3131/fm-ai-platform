# Kordena V1 — Legal Versioning & Acceptance Trail

**Estado:** IMPLEMENTADO — aguardando certificação da PR  
**Data:** 02/10/2026

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

## Gates

A promoção final exige CI/E2E real:

- LEGAL_TERMS_READY
- LEGAL_VERSIONING_PASS
- LEGAL_ACCEPTANCE_TRAIL_PASS
- PRIVACY_DISCLOSURE_PASS
- OPTIONAL_CONSENT_SEPARATION_PASS

Nenhum gate será marcado PASS sem evidência da PR e do pós-merge.
