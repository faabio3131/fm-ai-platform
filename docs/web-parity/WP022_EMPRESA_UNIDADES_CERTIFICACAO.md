# WP-022 — Empresa / Matriz / Filiais / Unidades — Certificação

## Estado

**CERTIFICAÇÃO DO CANDIDATO EM EXECUÇÃO.**

A implementação canônica do WP-022 já estava presente na branch oficial e havia sido tecnicamente validada no ciclo conservativo anterior. Este checkpoint não reconstrói domínio, aplicação, persistência, sessão ou RBAC: ele promove o bloco à certificação formal por SHA exato após o fechamento verde do WP-021.

## Escopo preservado

- leitura e atualização dos dados da empresa;
- listagem, criação e atualização de unidades;
- tipos matriz/filial/unidade conforme autoridade administrativa existente;
- versão/concorrência otimista preservada;
- sessão assinada como autoridade de tenant e unidade ativa;
- `admin.acessar` + `configuracao.alterar` e step-up administrativo canônicos;
- gerente padrão sem acesso administrativo automático;
- gerente explicitamente autorizado limitado às unidades permitidas;
- nenhum header, query ou body pode ampliar tenant/escopo autenticado.

## Autoridades reutilizadas

- `AplicacaoAdministracaoProprietarioV1`;
- `core/administracao`;
- repositórios administrativos existentes;
- `AuthSessionRuntime` e step-up já revalidado no WP-021;
- Shell/registry Web canônicos.

Não há novo domínio, facade paralela, migration, provider, política de sessão ou matriz RBAC.

## Provas existentes e gate dedicado

A prova focal inclui `tests/api/test_admin_empresa_http_contract.py`, contratos do Backoffice e do step-up, além da regressão Python completa, Ruff, mypy, lint, TypeScript e build Next.js. O gate dedicado é `.github/workflows/web-parity-wp022-certification.yml`.

O ciclo técnico anterior registrou cobertura para dois tenants, unidade homônima entre tenants, administrador, gerente padrão, gerente explicitamente limitado, spoofing de escopo, criação/edição, replay de versão, auditoria e revogação do step-up na troca operacional.

## Governança

- PR #118 permanece OPEN/DRAFT;
- nenhum merge ou deploy;
- nenhuma alteração da `main`;
- nenhum force push ou rebase destrutivo;
- nenhum teste enfraquecido;
- nenhuma arquitetura paralela.

## Pendências históricas preservadas

Este WP não declara resolvidos, sem evidência específica:

- WP-005 — Caixa/PDV;
- WP-005/WP-029 — settlement end-to-end;
- WP-007 — roteamento KDS;
- WP-009 — mensagens;
- WP-007/WP-009 — cadeia Pedido → Produção/KDS.

## Gate de saída

WP-022 só será declarado certificado quando o SHA exato que contém este documento e o gate dedicado concluir todos os workflows obrigatórios com 0 FAIL. Depois disso, a próxima etapa permitida pelo Prompt Mestre é a auditoria consolidada WP-019 → WP-022, sem iniciar V2, merge, deploy ou Visual Premium.
