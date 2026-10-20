# WP-021 — Step-up administrativo — Revalidação

## Estado

**REVALIDAÇÃO EM CERTIFICAÇÃO.**

O WP-021 não cria nem reimplementa um segundo mecanismo de step-up. O mecanismo canônico já existente é preservado e este checkpoint somente revalida sua integração com a Área Proprietário / Backoffice após a certificação verde do WP-020.

## Pré-condição cumprida

O WP-020 foi certificado no SHA `761bb01f9e6d5d9453d8f355da6849f28015402b` com todos os workflows associados ao SHA concluídos em `success`, incluindo o gate dedicado `Web Parity WP020 Certification`.

## Autoridade canônica preservada

A revalidação mantém como autoridade:

- sessão assinada canônica;
- `AuthSessionRuntime` e endpoints canônicos de autenticação;
- `admin.acessar` como permissão de entrada administrativa;
- senha da própria conta para elevação;
- revogação da elevação na troca de unidade e no logout;
- contexto de tenant e unidade exclusivamente derivado da sessão autenticada;
- `AdminStepUpGuard` na superfície Web administrativa.

Nenhuma senha administrativa compartilhada, bypass, fallback de identidade, segundo login administrativo ou autoridade paralela foi introduzido.

## Evidências já presentes e revalidadas

Os contratos existentes cobrem:

1. acesso administrativo sem sessão é recusado;
2. sessão sem step-up não entra no Backoffice;
3. step-up válido libera a operação administrativa;
4. troca operacional de unidade revoga a elevação;
5. nova elevação é necessária após troca de unidade;
6. logout revoga sessão/elevação;
7. Gerente padrão e outros papéis sem `admin.acessar` não recebem acesso automático;
8. spoofing por query/header não substitui tenant/unidade da sessão;
9. auditoria administrativa continua delegada à autoridade original.

A implementação WP-020 usa `contexto_backoffice()` para exigir identidade, `admin.acessar` e `admin_status()` elevado antes de delegar para `AplicacaoAdministracaoProprietarioV1.registrar_acesso()`.

## Decisão arquitetural

**Nenhuma alteração funcional é necessária no WP-021.** Reimplementar o step-up violaria a migração conservativa e criaria arquitetura paralela. O trabalho deste bloco é, portanto, exclusivamente a revalidação/checkpoint do mecanismo existente contra o Backoffice certificado.

## Governança

- PR oficial: #118;
- branch: `feat/web-parity-v1-total-original-migration`;
- PR deve permanecer OPEN/DRAFT;
- sem merge;
- sem deploy;
- sem force push/rebase destrutivo;
- sem alteração da `main`;
- sem enfraquecimento de testes.

## Pendências históricas preservadas

Este checkpoint não declara resolvidas pendências fora do seu escopo, incluindo WP-005/settlement, WP-007/KDS, WP-009/mensagens e a cadeia Pedido → Produção/KDS.

## Gate de saída

O WP-021 só será considerado fechado quando o SHA que contém este checkpoint concluir os gates obrigatórios aplicáveis em 100% verde. Somente então o fluxo poderá avançar para **WP-022 — Empresa / Matriz / Filiais / Unidades**.
