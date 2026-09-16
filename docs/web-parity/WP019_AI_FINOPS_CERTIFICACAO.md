# WP-019 — AI FinOps — Certificação

## Estado

**CERTIFICAÇÃO DOCUMENTAL EM FECHAMENTO.**

Implementação funcional de referência validada no SHA:

`b041bbdaa40742867aa513cb966719119af44bba`

A certificação formal deste documento só deve ser considerada concluída quando o SHA que contém este arquivo também estiver com os gates obrigatórios do CI verdes na PR #118.

## Escopo canônico

O WP-019 consolida a superfície Web/read-only de **AI FinOps de consumo e custo de IA**. Ele não cria um segundo financeiro comercial, não calcula faturamento do comércio e não substitui o financeiro canônico do Kordena.

Autoridades reutilizadas:

- `core.ai_finops`;
- `application.ai_finops_dashboard`;
- `infra.ai_finops_read_model`;
- sessão assinada e identidade operacional canônicas;
- RBAC canônico;
- tenant e unidade ativa provenientes da sessão.

## Implementação certificada

No endpoint `GET /v1/ai-finops/resumo`:

- `admin.acessar` é obrigatório;
- `financeiro.visualizar` é obrigatório;
- tenant e unidade são derivados da identidade autenticada;
- headers externos não possuem autoridade para ampliar escopo;
- o read model recebe tenant, unidade e período explicitamente;
- erros de segurança permanecem fail-closed;
- custos desconhecidos permanecem desconhecidos, sem fabricação de valor.

A correção adicional em `http_api/admin_integracoes.py` foi restrita a dívida de qualidade descoberta pelos gates amplos: remoção de bindings não usados e separação dos tipos de resultado dos healthchecks. Nenhum `ignore`, `skip`, `xfail` ou relaxamento de regra foi introduzido.

## Provas automatizadas adicionadas

Arquivo de certificação:

`tests/api/test_wp019_ai_finops_certification.py`

Ele prova, no escopo do WP-019:

1. bloqueio de usuário sem `financeiro.visualizar` mesmo quando possui acesso administrativo sensível;
2. troca de unidade pela sessão como autoridade efetiva do read model;
3. incapacidade de `X-Tenant-ID` e `X-Unit-ID` expandirem o escopo autenticado;
4. isolamento de tenant, unidade e período no read model;
5. custo desconhecido sem valor inventado;
6. exclusão de dados de outro tenant, outra unidade e fora do período;
7. agregação determinística de tentativas, sucesso, falha, fallback, tokens, latência, cobertura de custo, moedas e mix provider/model;
8. período sem eventos retornando resumo neutro;
9. bucket sem preço incapaz de produzir custo artificial.

## Evidência de CI da implementação

No SHA funcional `b041bbdaa40742867aa513cb966719119af44bba`, os workflows consultados da PR #118 concluíram com sucesso, incluindo:

- Commercial Runtime Readiness V1;
- Web Parity Phase 1 WP010-WP011 Certification;
- Web Parity Phase 1 WP013-WP014 Certification;
- Web Parity Phase 1 WP015 Certification;
- Web Parity Phase 1 WP016 Certification;
- Web Parity Phase 1 WP017 Certification;
- Web Parity WP028-WP030 Gate;
- Assistente Fase 4 Gate V1.

Na rodada candidata do mesmo estado funcional também ficaram verdes os gates amplos que haviam exposto e depois validado as correções de Ruff e mypy, incluindo `V1 Wave1 Authoritative Transactions` e `V1 Frontend Next.js Setup Gate`.

A suíte Python observada nessa rodada ampla concluiu com `1512 passed, 5 skipped`.

## Governança preservada

- PR oficial: `#118`;
- branch oficial: `feat/web-parity-v1-total-original-migration`;
- PR mantida OPEN/DRAFT;
- nenhum merge executado;
- nenhum deploy executado;
- `main` permaneceu em `5a17b0c8a1cb6dad576ce5b089166748b138900c` durante o fechamento deste bloco;
- promoção da candidata para a branch oficial foi fast-forward, sem force push;
- PR temporária #120 foi fechada sem merge.

## Limitações e dívida técnica preservada

### AF04 / fingerprint de schema no Windows

Permanece registrada a divergência de reflexão/fingerprint de schema observada no Windows no gate AF04. A evidência Linux/CI validou o baseline canônico. Portanto:

- não alterar o hash de baseline às cegas;
- não remover o AF04;
- não transformar o AF04 em `skip`/`xfail`;
- tratar a diferença Windows/Linux como dívida de determinismo cross-platform até correção específica futura.

### Escopo das consultas de workflow

A consulta automatizada usada para conferir os workflows associados ao SHA retorna os runs de evento pull request expostos pela integração utilizada. A certificação não transforma ausência de um run não listado em evidência positiva.

## Pendências históricas que continuam abertas

O WP-019 **não declara resolvidas** as pendências históricas fora de seu escopo, incluindo:

- WP-005 — caixa/PDV;
- WP-005/WP-029 — settlement end-to-end;
- WP-007 — roteamento KDS;
- WP-009 — mensagens;
- WP-007/WP-009 — cadeia Pedido → Produção/KDS.

Esses itens devem permanecer visíveis até evidência específica de resolução.

## Próxima etapa permitida

Somente depois que o SHA contendo esta certificação estiver com os gates obrigatórios verdes e a PR #118 continuar OPEN/DRAFT, sem merge/deploy, o fluxo pode avançar para:

**WP-020 — Área Proprietário / Backoffice.**

Após WP-020 ainda serão obrigatórios WP-021 (revalidação do step-up), WP-022, auditoria consolidada e WP-031 Fiscal antes do Visual Premium.