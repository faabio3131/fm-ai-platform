# KORDENA V1 VISUAL PREMIUM — KF-08 FINAL QA AUDIT

Data: 2026-09-30

## Escopo

Este registro executa a camada verificável do KF-08 sem alterar auth, RBAC, APIs, billing, tenant isolation, fiscal ou authority map.

## Evidência disponível

O frontend canônico é a aplicação Next.js em `web/`.

O contrato `web/tests/visual-premium-v1.test.mjs` cobre estruturalmente:

- shell e navegação canônicos;
- identidade Kordena e logo/cérebro aprovado;
- design system dark premium;
- reduced motion;
- eliminação de ilhas claras prioritárias;
- autenticação e step-up preservados;
- Gerente IA e Atendimento IA;
- operação versus autoridade administrativa;
- marketplaces com homologação pendente explicitada;
- Catálogo/Estoque com mutações protegidas;
- densidade de cards e hero executivo compacto.

O workflow `Kordena V1 Visual Premium Gate` executa:

- ESLint;
- TypeScript;
- Web tests;
- Visual Premium structural contract;
- Next production build;
- diff whitespace.

## Preview

O Vercel informa o preview do PR de regressão como `Ready`.

Porém, a inspeção HTTP do preview é redirecionada para `Protected Deployment – Vercel`. O conteúdo real do Kordena não fica publicamente acessível sem uma sessão autorizada da Vercel.

Uma tentativa de browser interativo para click-audit não chegou a iniciar porque a carteira do provedor de browser está sem saldo. Nenhum resultado visual foi inventado a partir disso.

## Status do click-audit físico

Ainda não certificado fisicamente no preview protegido:

- button;
- link;
- menu;
- tab;
- card action;
- dropdown;
- modal action;
- CTA;
- teclado/focus em todas as telas;
- responsividade visual completa por viewport.

Os testes automatizados existentes continuam válidos como evidência estrutural/funcional, mas não substituem a inspeção física integral exigida pelo gate.

## Gate KF-G08

Estado antes do workflow deste PR:

- `PREMIUM_UI_FINAL_QA_PASS`: **PENDING CI + PHYSICAL BROWSER EVIDENCE**
- `ZERO_DEAD_CONTROLS`: **NOT FULLY PROVEN PHYSICALLY**
- `ZERO_FUNCTIONAL_REGRESSION`: **PASS no KF-07; a revalidar pelo gate visual**
- agregado KF-G08: **BLOCKED_EXTERNAL / PARTIAL_EVIDENCE**

Não promover KF-G08 a PASS total até que o click-audit físico do preview real seja executado com acesso autorizado.
