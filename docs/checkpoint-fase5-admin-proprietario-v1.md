# Checkpoint — Fase 5 — Administração / Proprietário V1

**Data:** 01/09/2026  
**Branch:** `recovery/v1-fase5-admin-proprietario`  
**SHA técnico validado:** `b97c1681feecfbce8823a6ac414729e048ac6fba`  
**Gate:** `Administracao Fase 5 Gate V1` — run 25 (`33466768101`) — **PASS**  
**Classificação:** **APROVADA INTERNAMENTE / COMMERCIAL_CANDIDATE**  
**Merge:** não executado  
**Deploy:** não executado

## Escopo fechado

A Fase 5 implementa o Painel Proprietário / Administrador reutilizando as autoridades canônicas do GERENTE AI / Kordena. O patrimônio específico novo limita-se a cadastro administrativo de empresa/unidades e configurações não secretas; identidade, PIN, pagamentos, estoque, entrega, integrações, credenciais e auditoria continuam nas autoridades já existentes.

Foram fechados:
- empresa, matriz e filiais;
- configurações financeiras/operacionais não secretas;
- usuários, papéis e escopo de unidades;
- dashboard executivo sobre Pedido/VendaFinanceira/Pagamento/Estoque/Entrega;
- integrações e saúde por unidade sobre Control Plane + Vault;
- auditoria administrativa;
- PIN individual em escritas sensíveis;
- migration 0036 com backfill/bootstrap determinísticos;
- isolamento tenant/unidade e concorrência otimista;
- gate de PostgreSQL, regressões e browser.

## Incidente residual do run 22 e correção

O run 22 falhou somente no passo browser. Após o PIN, o Streamlit executava `render_identity_sidebar` dentro da própria página administrativa e chamava `st.page_link("pages/6_Administracao_Proprietario.py")`. No modo em que o E2E inicia diretamente essa página, Streamlit 1.62 lançou `KeyError: 'url_pathname'`. O heading nunca era renderizado e o Playwright expirava.

A correção adotada não usa fallback silencioso:
- `render_identity_sidebar(..., show_admin_link=True)` mantém o comportamento padrão nas demais telas;
- `pages/6_Administracao_Proprietario.py` usa `show_admin_link=False`, pois não deve linkar para si mesma;
- o workflow passou a compilar e executar Ruff também em `auth_ui.py`.

O run 25 comprovou a correção no mesmo fluxo físico automatizado.

## Evidência do run 25

| Gate | Resultado |
|---|---|
| PostgreSQL 16 / migration 0036 | PASS — 1 teste |
| Domínio e integração administrativa | PASS — 9 testes |
| Auth / RBAC / PIN | PASS — 19 testes |
| Isolamento do Control Plane | PASS — 2 testes |
| Compile | PASS |
| Ruff | PASS |
| Chromium / Playwright sem `FM_AI_TEST_MODE` | PASS — 1 jornada |
| Publicação de evidência do browser | PASS |

A jornada autentica o proprietário, exige o PIN administrativo individual, altera o nome da empresa pela interface e confirma a persistência. Depois faz logout, autentica um usuário Caixa e comprova bloqueio fail-closed na mesma URL administrativa, sem `stException` e sem traceback.

## Readiness e pendências

`administracao_proprietario` passa a `COMMERCIAL_CANDIDATE`, com blockers internos conhecidos = 0.

PagBank, Meta/WhatsApp e Mercado Pago continuam externos e separados. A Fase 5 não os marca como prontos, não cria credenciais alternativas e não usa sua ausência para bloquear artificialmente a Administração.

## Rollback e continuidade

Antes de merge/deploy, rollback é reverter os commits da branch. Depois de uma implantação futura, dados administrativos criados pela migration 0036 devem ser preservados; rollback não autoriza apagar autoridades canônicas ou histórico de auditoria.

Nenhum merge e nenhum deploy foram executados. A próxima fase depende de autorização expressa e deve começar somente a partir deste checkpoint validado.
