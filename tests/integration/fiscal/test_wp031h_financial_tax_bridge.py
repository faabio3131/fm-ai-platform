from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from threading import Barrier, Thread

import pytest
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session

from core.pagamentos.erros import (
    ConflitoIdempotenciaPagamento,
    EfeitoFinanceiroFiscalBloqueado,
    OperacaoPagamentoNaoAutorizada,
)
from core.pagamentos.fiscal_bridge import (
    RegraCreditoTributario,
    RepositorioBridgeFinanceiroFiscalEmMemoria,
    ResultadoCreditoTributario,
    ServicoBridgeFinanceiroFiscal,
    StatusObrigacaoCompra,
    StatusReconciliacaoCompra,
    TipoAjusteObrigacaoCompra,
)
from core.pagamentos.fiscal_bridge_sqlalchemy import (
    RepositorioBridgeFinanceiroFiscalSQLAlchemy,
)
from core.pagamentos.modelos_orm import (
    AjusteObrigacaoCompraORM,
    DecisaoCreditoTributarioORM,
    ObrigacaoCompraFiscalORM,
)
from core.procurement.modelos import (
    ItemPedidoCompra,
    ItemRecebido,
    PedidoCompra,
    RecebimentoCompra,
    StatusPedidoCompra,
    StatusRecebimento,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from kordena_fiscal.domain import ExecutionScope, FiscalEnvironment
from migrations.fiscal_financial_tax_bridge_v1 import (
    upgrade_fiscal_financial_tax_bridge_v1,
)

NOW = datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc)


def scope(
    environment: FiscalEnvironment = FiscalEnvironment.PRODUCTION,
    *,
    tenant: str = "tenant-a",
    unit: str = "unit-a",
) -> ExecutionScope:
    return ExecutionScope(tenant, unit, environment, f"corr-{tenant}-{unit}")


def contexto(
    *permissoes: Permissao,
    tenant: str = "tenant-a",
    unit: str = "unit-a",
) -> ContextoExecucao:
    return ContextoExecucao(
        usuario_id="financeiro-1",
        tenant_id=tenant,
        unidade_id=unit,
        papeis=frozenset({Papel.FINANCEIRO}),
        permissoes=frozenset(permissoes),
        correlation_id=f"corr-{tenant}-{unit}",
        solicitado_em=NOW,
        origem="test",
        unidades_permitidas=frozenset({unit}),
    )


def pedido(execution_scope: ExecutionScope, *, quantidade: str = "2") -> PedidoCompra:
    item = ItemPedidoCompra(
        1,
        "farinha",
        "FAR-1",
        "Farinha",
        "UN",
        Decimal(quantidade),
        Decimal(5),
    )
    return PedidoCompra(
        "pedido-1",
        execution_scope,
        "fornecedor-1",
        (item,),
        Decimal(0),
        Decimal(0),
        item.total,
        StatusPedidoCompra.CONCLUIDO,
        "comprador-1",
        NOW,
        NOW,
        2,
    )


def recebimento(
    execution_scope: ExecutionScope,
    *,
    identificador: str = "recebimento-1",
    quantidade: str = "2",
    status: StatusRecebimento = StatusRecebimento.CONCLUIDO,
) -> RecebimentoCompra:
    return RecebimentoCompra(
        identificador,
        execution_scope,
        "pedido-1",
        "inbound-1",
        "1" * 44,
        f"idem-{identificador}",
        (
            ItemRecebido(
                1,
                1,
                "farinha",
                Decimal(quantidade),
                "UN",
                Decimal(5),
                True,
            ),
        ),
        (),
        status,
        "recebedor-1",
        NOW,
    )


def test_wp031h_obrigacao_nasce_uma_vez_sem_pagamento_automatico() -> None:
    execution_scope = scope()
    repo = RepositorioBridgeFinanceiroFiscalEmMemoria()
    servico = ServicoBridgeFinanceiroFiscal(repo)
    operador = contexto(Permissao.FINANCEIRO_COMPRAS_REGISTRAR)

    primeiro = servico.criar_obrigacao(
        contexto=operador,
        scope=execution_scope,
        pedido=pedido(execution_scope),
        recebimento=recebimento(execution_scope),
        total_documental=Decimal(10),
        idempotency_key="financeiro-recebimento-1",
        obrigacao_id="obrigacao-1",
    )
    replay = servico.criar_obrigacao(
        contexto=operador,
        scope=execution_scope,
        pedido=pedido(execution_scope),
        recebimento=recebimento(execution_scope),
        total_documental=Decimal(10),
        idempotency_key="financeiro-recebimento-1",
        obrigacao_id="obrigacao-1",
    )

    assert primeiro.obrigacao.status is StatusObrigacaoCompra.ABERTA
    assert primeiro.obrigacao.reconciliacao is StatusReconciliacaoCompra.CONCILIADA
    assert primeiro.obrigacao.saldo == Decimal("10.00")
    assert not primeiro.idempotente and replay.idempotente
    assert primeiro.eventos[0].event_type == "financeiro.obrigacao_compra.criada"
    assert len(repo.listar_obrigacoes(execution_scope)) == 1


def test_wp031h_parcial_e_final_reconciliam_total_sem_duplicar() -> None:
    execution_scope = scope()
    repo = RepositorioBridgeFinanceiroFiscalEmMemoria()
    servico = ServicoBridgeFinanceiroFiscal(repo)
    operador = contexto(Permissao.FINANCEIRO_COMPRAS_REGISTRAR)
    ordem = pedido(execution_scope, quantidade="4")

    parcial = servico.criar_obrigacao(
        contexto=operador,
        scope=execution_scope,
        pedido=ordem,
        recebimento=recebimento(
            execution_scope,
            identificador="recebimento-parcial",
            quantidade="2",
            status=StatusRecebimento.PARCIAL,
        ),
        total_documental=Decimal(20),
        idempotency_key="financeiro-parcial",
    )
    final = servico.criar_obrigacao(
        contexto=operador,
        scope=execution_scope,
        pedido=ordem,
        recebimento=recebimento(
            execution_scope,
            identificador="recebimento-final",
            quantidade="2",
        ),
        total_documental=Decimal(20),
        idempotency_key="financeiro-final",
    )

    assert parcial.obrigacao.valor_original == Decimal("10.00")
    assert parcial.obrigacao.reconciliacao is StatusReconciliacaoCompra.PARCIAL
    assert final.obrigacao.valor_original == Decimal("10.00")
    assert final.obrigacao.reconciliacao is StatusReconciliacaoCompra.CONCILIADA
    assert servico.projetar(execution_scope).saldo_aberto == Decimal("20.00")


def test_wp031h_concorrencia_cria_uma_unica_obrigacao() -> None:
    execution_scope = scope()
    repo = RepositorioBridgeFinanceiroFiscalEmMemoria()
    servico = ServicoBridgeFinanceiroFiscal(repo)
    operador = contexto(Permissao.FINANCEIRO_COMPRAS_REGISTRAR)
    barreira = Barrier(8)
    resultados: list[object] = []

    def executar() -> None:
        barreira.wait()
        resultados.append(
            servico.criar_obrigacao(
                contexto=operador,
                scope=execution_scope,
                pedido=pedido(execution_scope),
                recebimento=recebimento(execution_scope),
                total_documental=Decimal(10),
                idempotency_key="concorrente-1",
                obrigacao_id="obrigacao-concorrente",
            )
        )

    threads = [Thread(target=executar) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert len(resultados) == 8
    assert sum(not resultado.idempotente for resultado in resultados) == 1
    assert len(repo.listar_obrigacoes(execution_scope)) == 1


def test_wp031h_homologacao_estado_invalido_rbac_e_escopo_falham_fechados() -> None:
    repo = RepositorioBridgeFinanceiroFiscalEmMemoria()
    servico = ServicoBridgeFinanceiroFiscal(repo)
    production = scope()
    homolog = scope(FiscalEnvironment.HOMOLOGATION)

    with pytest.raises(OperacaoPagamentoNaoAutorizada):
        servico.criar_obrigacao(
            contexto=contexto(),
            scope=production,
            pedido=pedido(production),
            recebimento=recebimento(production),
            total_documental=Decimal(10),
            idempotency_key="sem-permissao",
        )
    with pytest.raises(EfeitoFinanceiroFiscalBloqueado):
        servico.criar_obrigacao(
            contexto=contexto(Permissao.FINANCEIRO_COMPRAS_REGISTRAR),
            scope=homolog,
            pedido=pedido(homolog),
            recebimento=recebimento(homolog),
            total_documental=Decimal(10),
            idempotency_key="homolog",
        )
    with pytest.raises(EfeitoFinanceiroFiscalBloqueado):
        servico.criar_obrigacao(
            contexto=contexto(Permissao.FINANCEIRO_COMPRAS_REGISTRAR),
            scope=production,
            pedido=pedido(production),
            recebimento=recebimento(
                production, status=StatusRecebimento.REJEITADO
            ),
            total_documental=Decimal(10),
            idempotency_key="rejeitado",
        )
    with pytest.raises(EfeitoFinanceiroFiscalBloqueado):
        servico.criar_obrigacao(
            contexto=contexto(
                Permissao.FINANCEIRO_COMPRAS_REGISTRAR, tenant="tenant-b"
            ),
            scope=production,
            pedido=pedido(production),
            recebimento=recebimento(production),
            total_documental=Decimal(10),
            idempotency_key="cross-tenant",
        )


def test_wp031h_devolucao_ajusta_sem_apagar_historico_e_replay_e_seguro() -> None:
    execution_scope = scope()
    repo = RepositorioBridgeFinanceiroFiscalEmMemoria()
    servico = ServicoBridgeFinanceiroFiscal(repo)
    operador = contexto(Permissao.FINANCEIRO_COMPRAS_REGISTRAR)
    servico.criar_obrigacao(
        contexto=operador,
        scope=execution_scope,
        pedido=pedido(execution_scope),
        recebimento=recebimento(execution_scope),
        total_documental=Decimal(10),
        idempotency_key="criar-ajuste",
        obrigacao_id="obrigacao-ajuste",
    )

    ajustada = servico.ajustar_obrigacao(
        contexto=operador,
        scope=execution_scope,
        recebimento_id="recebimento-1",
        tipo=TipoAjusteObrigacaoCompra.DEVOLUCAO,
        origem_id="devolucao-1",
        motivo="mercadoria devolvida ao fornecedor",
        idempotency_key="ajuste-1",
    )
    replay = servico.ajustar_obrigacao(
        contexto=operador,
        scope=execution_scope,
        recebimento_id="recebimento-1",
        tipo=TipoAjusteObrigacaoCompra.DEVOLUCAO,
        origem_id="devolucao-1",
        motivo="mercadoria devolvida ao fornecedor",
        idempotency_key="ajuste-1",
    )

    assert ajustada.status is StatusObrigacaoCompra.CANCELADA
    assert ajustada.saldo == Decimal("0.00")
    assert replay == ajustada
    assert repo.listar_obrigacoes(execution_scope)[0].valor_original == Decimal(
        "10.00"
    )
    with pytest.raises(ConflitoIdempotenciaPagamento):
        servico.ajustar_obrigacao(
            contexto=operador,
            scope=execution_scope,
            recebimento_id="recebimento-1",
            tipo=TipoAjusteObrigacaoCompra.CANCELAMENTO,
            origem_id="cancelamento-diferente",
            motivo="payload divergente",
            idempotency_key="ajuste-1",
            valor=Decimal(1),
        )


def test_wp031h_credito_exige_regra_explicita_versionada() -> None:
    execution_scope = scope()
    repo = RepositorioBridgeFinanceiroFiscalEmMemoria()
    servico = ServicoBridgeFinanceiroFiscal(repo)
    operador = contexto(
        Permissao.FINANCEIRO_COMPRAS_REGISTRAR,
        Permissao.FINANCEIRO_TRIBUTOS_DECIDIR,
    )
    servico.criar_obrigacao(
        contexto=operador,
        scope=execution_scope,
        pedido=pedido(execution_scope),
        recebimento=recebimento(execution_scope),
        total_documental=Decimal(10),
        idempotency_key="credito-obrigacao",
    )

    bloqueada = servico.decidir_credito(
        contexto=operador,
        scope=execution_scope,
        recebimento_id="recebimento-1",
        tributo="ICMS",
        base_calculo=Decimal(10),
        valor_destacado=Decimal("1.80"),
        cfop="1102",
        cst="00",
        regra=None,
        idempotency_key="credito-sem-regra",
    )
    regra = RegraCreditoTributario(
        "icms-compra-insumo",
        3,
        "ICMS",
        frozenset({"1102"}),
        frozenset({"00"}),
        Decimal("0.18"),
        date(2026, 1, 1),
    )
    elegivel = servico.decidir_credito(
        contexto=operador,
        scope=execution_scope,
        recebimento_id="recebimento-1",
        tributo="ICMS",
        base_calculo=Decimal(10),
        valor_destacado=Decimal("1.80"),
        cfop="1102",
        cst="00",
        regra=regra,
        idempotency_key="credito-com-regra",
    )

    assert bloqueada.resultado is ResultadoCreditoTributario.BLOQUEADO
    assert bloqueada.valor_credito == Decimal("0.00")
    assert elegivel.resultado is ResultadoCreditoTributario.ELEGIVEL
    assert elegivel.regra_id == "icms-compra-insumo" and elegivel.regra_versao == 3
    assert elegivel.valor_credito == Decimal("1.80")
    assert servico.projetar(execution_scope).creditos_elegiveis == Decimal("1.80")

    servico.ajustar_obrigacao(
        contexto=operador,
        scope=execution_scope,
        recebimento_id="recebimento-1",
        tipo=TipoAjusteObrigacaoCompra.DEVOLUCAO,
        origem_id="devolucao-credito",
        motivo="devolucao exige nova decisao tributaria",
        idempotency_key="ajuste-credito",
        valor=Decimal(5),
    )
    assert servico.projetar(execution_scope).creditos_elegiveis == Decimal("0.00")


def test_wp031h_sql_e_migration_sao_duraveis_sem_criar_pagamento() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        upgrade_fiscal_financial_tax_bridge_v1(connection)
    assert {
        "obrigacoes_compra_fiscal_v1",
        "ajustes_obrigacao_compra_v1",
        "decisoes_credito_tributario_v1",
    }.issubset(set(inspect(engine).get_table_names()))
    assert "pagamentos_v1" not in set(inspect(engine).get_table_names())

    execution_scope = scope()
    with Session(engine) as session:
        repo = RepositorioBridgeFinanceiroFiscalSQLAlchemy(session)
        servico = ServicoBridgeFinanceiroFiscal(repo)
        operador = contexto(
            Permissao.FINANCEIRO_COMPRAS_REGISTRAR,
            Permissao.FINANCEIRO_TRIBUTOS_DECIDIR,
        )
        resultado = servico.criar_obrigacao(
            contexto=operador,
            scope=execution_scope,
            pedido=pedido(execution_scope),
            recebimento=recebimento(execution_scope),
            total_documental=Decimal(10),
            idempotency_key="sql-obrigacao",
            obrigacao_id="sql-obrigacao-1",
        )
        servico.decidir_credito(
            contexto=operador,
            scope=execution_scope,
            recebimento_id="recebimento-1",
            tributo="ICMS",
            base_calculo=Decimal(10),
            valor_destacado=Decimal("1.80"),
            cfop="1102",
            cst="00",
            regra=None,
            idempotency_key="sql-credito-bloqueado",
        )
        servico.ajustar_obrigacao(
            contexto=operador,
            scope=execution_scope,
            recebimento_id="recebimento-1",
            tipo=TipoAjusteObrigacaoCompra.DEVOLUCAO,
            origem_id="sql-devolucao",
            motivo="devolucao parcial persistida",
            idempotency_key="sql-ajuste",
            valor=Decimal(2),
        )
        session.commit()
        assert resultado.obrigacao.saldo == Decimal("10.00")
        assert session.scalar(select(func.count()).select_from(ObrigacaoCompraFiscalORM)) == 1
        assert session.scalar(select(func.count()).select_from(AjusteObrigacaoCompraORM)) == 1
        assert session.scalar(select(func.count()).select_from(DecisaoCreditoTributarioORM)) == 1
        resumo = servico.projetar(execution_scope)
        assert resumo.valor_original == Decimal("10.00")
        assert resumo.valor_ajustado == Decimal("2.00")
        assert resumo.saldo_aberto == Decimal("8.00")
        assert resumo.fontes == ("recebimento-1",)
