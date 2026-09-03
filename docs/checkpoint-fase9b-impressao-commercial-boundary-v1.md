# CHECKPOINT F9-B — IMPRESSÃO COMMERCIAL BOUNDARY V1

**Projeto:** Kordena / GERENTE AI V1.0  
**Issue:** #75  
**PR:** #76 (draft)  
**Branch:** `recovery/v1-fase9-impressao-operacional-cutover`  
**SHA técnico final:** `58032024c05284a6f7325a4b0e961709b98d0a48`  
**Status:** FECHADO / GREEN

## Escopo fechado

F9-B fecha apenas a fronteira comercial/transacional da impressão:
- Application dedicada;
- `UnitOfWorkV1` dona de commit/rollback;
- spool SQLAlchemy + auditoria na mesma Session;
- `PortaImpressora` injetada;
- anti-Fake/test-runtime no caminho comercial;
- prova do schema oficial.

Não fecha:
- KDS -> spool automático;
- driver físico;
- configuração comercial de destinos;
- UI operacional;
- Commercial Runtime E2E/hardware.

## Implementação

`application/impressao_transacoes.py` introduz `AplicacaoImpressaoV1`.

A Application:
1. abre `UnitOfWorkV1`;
2. obtém a Session ativa;
3. compõe `RepositorioSpoolSQLAlchemy` e `RepositorioAuditoriaSQLAlchemy`;
4. usa `ServicoSpoolImpressao`;
5. executa processamento/reimpressão;
6. executa `uow.commit()`.

Nenhum repository/service/UI recebeu `commit()` escondido.

## Segurança e governança

- `ImpressoraFake` existe somente em testes;
- caminhos comerciais não usam runtime_teste;
- `migrations/impressao_v1.py` não é usada como migration comercial;
- RBAC `impressao.reimprimir` permanece no domínio;
- tenant/unidade continuam obrigatórios;
- KDS não foi alterado e continua autoridade;
- nenhuma migration nova foi criada.

## Readiness fitness

O gate de readiness foi ampliado para modelar dois tipos de débito:
- blocker por **presença** de legado/Fake;
- blocker por **ausência** de capacidade comercial alvo.

Isso permitiu remover B9-01 somente quando a Application/UoW apareceu de fato,
mantendo B9-02..B9-05 ativos.

## Evidência

Gate dedicado:
- workflow: `Fase 9B Impressao Commercial Boundary Gate`;
- run: `33699707722`;
- compile: PASS;
- Ruff: PASS;
- mypy: PASS;
- fitness commercial boundary/readiness: PASS;
- regressões impressão: PASS;
- PostgreSQL 16 / migration 0012 / `impressao_jobs_v1`: PASS.

Matriz final:
- **20/20 workflows verdes** no SHA técnico final.

## Correção registrada

O candidato `9bf2c84d2cfa5b4481bc54896f99651e9233bf4e` falhou no Ruff por:
- import `Session` não usado no teste;
- `Decimal("1")` em forma considerada verbosa.

O SHA final `58032024...` corrigiu somente o teste e passou toda a matriz.

## Readiness pós-F9-B

`impressao_operacional = CUTOVER_PENDING`

Code blockers restantes:
- `kds_to_print_spool_not_composed`;
- `print_real_adapter_not_composed`;
- `print_destinations_not_commercially_configured`;
- `print_surface_not_exposed_in_app`.

External blocker:
- `physical_printer_hardware_gate_pending`.

Evidência:
- `sha = 58032024...`;
- Commercial Runtime E2E = null;
- physical_test = null.

## Próximo bloco

**F9-C — KDS/evento -> spool idempotente e não bloqueante**, somente após
revalidação verde deste checkpoint documental.

Sem merge/deploy.
