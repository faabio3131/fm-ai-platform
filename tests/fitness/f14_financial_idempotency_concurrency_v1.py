"""Fitness F14-B: idempotência, concorrência e integridade financeira em PostgreSQL.

Este arquivo é deliberadamente fora do padrão ``test_*.py`` para não adicionar SKIP
à regressão Python genérica. O workflow F14-B o invoca explicitamente em staging
com PostgreSQL real e FM_AI_TEST_MODE ausente.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier

import pytest
from sqlalchemy import MetaData, Table, create_engine, func, insert, select
from sqlalchemy.orm import Session, sessionmaker

from application.finalizacao_pagamento import finalizar_pagamento_liquidado_em_transacao
from core.crm.cashback import ServicoCashback
from core.crm.erros import ErroCRM
from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import PagamentoStatus
from core.pagamentos.adaptador_sqlalchemy import RepositorioPagamentosSQLAlchemy
from core.pagamentos.erros import ConcorrenciaPagamento, ConflitoIdempotenciaPagamento
from core.pagamentos.modelos import MetodoPagamento
from core.pagamentos.modelos_orm import (
    PagamentoORM,
    TransacaoPagamentoORM,
    VendaFinanceiraORM,
)
from core.pagamentos.servicos import (
    confirmar_pagamento,
    criar_obrigacao_pagamento,
    registrar_estorno,
)
from core.pdv.modelos import EntradaPDV
from core.pdv.modelos_orm import ReconciliacaoPDVORM, VendaLegadaLinkORM
from core.pdv.roteamento import ModoPDV
from core.runtime.config import RuntimeEnvironment, load_runtime_settings
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel
from infra.crm.cashback_sqlalchemy import RepositorioCashbackSQLAlchemy
from infra.transacoes.uow import RecursosTransacionaisV1, UnitOfWorkV1
from tests.integration.pdv.conftest import ClienteTeste
from tests.integration.pdv.helpers import executar

TENANT = "tenant-f6d"
UNIDADE = "unidade-f6d"
AGORA = datetime(2026, 9, 6, 5, 0, tzinfo=timezone.utc)


def _factory() -> sessionmaker[Session]:
    assert os.getenv("FM_AI_TEST_MODE") != "1"
    settings = load_runtime_settings()
    assert settings.environment is RuntimeEnvironment.STAGING
    assert settings.commercial
    assert settings.database_url.startswith("postgresql")
    engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _contexto(correlation_id: str) -> ContextoExecucao:
    return ContextoExecucao(
        TENANT,
        UNIDADE,
        "caixa-f14b",
        frozenset({Papel.CAIXA}),
        MATRIZ_PADRAO[Papel.CAIXA],
        correlation_id,
        AGORA,
        "commercial-runtime-f14b",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _seed_cliente(
    factory: sessionmaker[Session],
    *,
    legacy_cliente_id: int,
    cliente_crm_id: str,
    saldo_inicial: Decimal = Decimal("10.00"),
) -> None:
    with factory.begin() as session:
        connection = session.connection()
        clientes = Table("clientes", MetaData(), autoload_with=connection)
        crm_clientes = Table("crm_clientes_v1", MetaData(), autoload_with=connection)
        mapping = Table("crm_cliente_legado_v1", MetaData(), autoload_with=connection)

        if session.execute(
            select(clientes.c.id).where(clientes.c.id == legacy_cliente_id)
        ).scalar_one_or_none() is None:
            session.execute(
                insert(clientes).values(
                    id=legacy_cliente_id,
                    nome=f"Cliente F14-B {legacy_cliente_id}",
                    whatsapp=f"5511999{legacy_cliente_id}",
                    total_gasto=0.0,
                    saldo_cashback=float(saldo_inicial),
                    status="Ativo",
                )
            )

        if session.execute(
            select(crm_clientes.c.cliente_id)
            .where(crm_clientes.c.tenant_id == TENANT)
            .where(crm_clientes.c.unidade_id == UNIDADE)
            .where(crm_clientes.c.cliente_id == cliente_crm_id)
        ).scalar_one_or_none() is None:
            session.execute(
                insert(crm_clientes).values(
                    tenant_id=TENANT,
                    unidade_id=UNIDADE,
                    cliente_id=cliente_crm_id,
                    origem="legado_regularizado",
                    marketplace_origem=None,
                    criado_em=AGORA,
                    versao=1,
                )
            )

        if session.execute(
            select(mapping.c.cliente_id)
            .where(mapping.c.tenant_id == TENANT)
            .where(mapping.c.unidade_id == UNIDADE)
            .where(mapping.c.legacy_cliente_id == legacy_cliente_id)
        ).scalar_one_or_none() is None:
            session.execute(
                insert(mapping).values(
                    tenant_id=TENANT,
                    unidade_id=UNIDADE,
                    legacy_cliente_id=legacy_cliente_id,
                    cliente_id=cliente_crm_id,
                    criado_por="gate-f14b",
                    correlation_id=f"corr-seed-{legacy_cliente_id}",
                    criado_em=AGORA,
                )
            )

        ServicoCashback(RepositorioCashbackSQLAlchemy(session)).creditar(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_id=cliente_crm_id,
            valor=saldo_inicial,
            origem="regularizacao_governada",
            referencia=f"gate://f14b/regularizacao/{legacy_cliente_id}",
            idempotency_key=f"f14b:regularizacao:{legacy_cliente_id}",
            ocorrido_em=AGORA,
        )


def _entrada_pdv(
    factory: sessionmaker[Session],
    *,
    checkout_id: str,
    legacy_cliente_id: int,
) -> EntradaPDV:
    with factory() as session:
        produtos = Table("produtos", MetaData(), autoload_with=session.connection())
        produto = session.execute(
            select(
                produtos.c.id,
                produtos.c.nome,
                produtos.c.preco_venda,
                produtos.c.custo_total_cmv,
            )
            .where(produtos.c.nome == "Produto F6-D")
            .where(produtos.c.loja_id == "6001")
        ).one()

    return EntradaPDV(
        produto_id=int(produto.id),
        produto_nome=str(produto.nome),
        quantidade=1,
        preco_unitario=Dinheiro(Decimal(str(produto.preco_venda))),
        custo_total=Dinheiro(Decimal(str(produto.custo_total_cmv))),
        forma_pagamento="Dinheiro Em Espécie",
        terminal_id="caixa-f14b",
        checkout_id=checkout_id,
        cliente_id=legacy_cliente_id,
        valor_recebido=Dinheiro(Decimal("50.00")),
        usar_cashback=True,
        desconto_cashback=Dinheiro(Decimal("5.00")),
        confirmacao_presencial=True,
    )


def _criar_pagamento(
    factory: sessionmaker[Session],
    *,
    pagamento_id: str,
    pedido_id: str,
    chave: str,
    valor: Decimal = Decimal("100.00"),
) -> None:
    with UnitOfWorkV1(factory) as uow:
        criar_obrigacao_pagamento(
            contexto=_contexto(f"corr-{pagamento_id}"),
            repositorio=uow.pagamentos,
            pagamento_id=pagamento_id,
            pedido_id=pedido_id,
            valor_previsto=Dinheiro(valor),
            metodo=MetodoPagamento.DINHEIRO,
            idempotency_key=chave,
            timestamp=AGORA,
        )
        uow.commit()


def test_replay_identico_pdv_nao_duplica_financeiro_ou_cashback() -> None:
    factory = _factory()
    legacy_cliente_id = 14001
    cliente_crm_id = "cliente-crm-f14b-replay"
    _seed_cliente(
        factory,
        legacy_cliente_id=legacy_cliente_id,
        cliente_crm_id=cliente_crm_id,
    )
    entrada = _entrada_pdv(
        factory,
        checkout_id="checkout-f14b-replay-identico",
        legacy_cliente_id=legacy_cliente_id,
    )
    contexto = _contexto("corr-f14b-replay")

    primeiro = executar(factory, contexto, entrada, ModoPDV.AUTHORITATIVE_CANARY)
    repetido = executar(factory, contexto, entrada, ModoPDV.AUTHORITATIVE_CANARY)

    assert primeiro.sucesso
    assert repetido.sucesso
    assert repetido.idempotente
    assert repetido.pedido_id == primeiro.pedido_id
    assert repetido.pagamento_id == primeiro.pagamento_id
    assert repetido.venda_financeira_id == primeiro.venda_financeira_id
    assert repetido.venda_legada_id == primeiro.venda_legada_id

    with factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(TransacaoPagamentoORM)
                .where(
                    TransacaoPagamentoORM.pagamento_id == primeiro.pagamento_id,
                    TransacaoPagamentoORM.tipo == "confirmacao",
                )
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(VendaLegadaLinkORM)
                .where(VendaLegadaLinkORM.pedido_id == primeiro.pedido_id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ReconciliacaoPDVORM)
                .where(ReconciliacaoPDVORM.pedido_id == primeiro.pedido_id)
            )
            == 1
        )
        cashback = RepositorioCashbackSQLAlchemy(session)
        saldo = cashback.saldo(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_id=cliente_crm_id,
        )
        historico = cashback.historico(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_id=cliente_crm_id,
        )
        cliente_legado = session.get(ClienteTeste, legacy_cliente_id)
        assert saldo == Decimal("5.75")
        assert len(historico) == 3
        assert cliente_legado is not None
        assert Decimal(str(cliente_legado.saldo_cashback)) == saldo


def test_replay_financeiro_identico_retorna_idempotente_e_divergente_conflita() -> None:
    factory = _factory()
    pagamento_id = "pag-f14b-replay"
    _criar_pagamento(
        factory,
        pagamento_id=pagamento_id,
        pedido_id="pedido-f14b-replay",
        chave="f14b:obrigacao:replay",
    )

    with UnitOfWorkV1(factory) as uow:
        primeiro = confirmar_pagamento(
            contexto=_contexto("corr-f14b-confirm-1"),
            repositorio=uow.pagamentos,
            pagamento_id=pagamento_id,
            valor=Dinheiro(Decimal("40.00")),
            metodo=MetodoPagamento.DINHEIRO,
            idempotency_key="f14b:confirmacao:replay",
            expected_version=1,
            timestamp=AGORA + timedelta(seconds=1),
        )
        uow.commit()

    with UnitOfWorkV1(factory) as uow:
        repetido = confirmar_pagamento(
            contexto=_contexto("corr-f14b-confirm-replay"),
            repositorio=uow.pagamentos,
            pagamento_id=pagamento_id,
            valor=Dinheiro(Decimal("40.00")),
            metodo=MetodoPagamento.DINHEIRO,
            idempotency_key="f14b:confirmacao:replay",
            expected_version=1,
            timestamp=AGORA + timedelta(seconds=2),
        )
        assert repetido.idempotente
        assert repetido.transacao.transacao_id == primeiro.transacao.transacao_id
        uow.commit()

    with UnitOfWorkV1(factory) as uow, pytest.raises(
        ConflitoIdempotenciaPagamento,
        match="conflito_idempotencia",
    ):
        confirmar_pagamento(
            contexto=_contexto("corr-f14b-confirm-conflict"),
            repositorio=uow.pagamentos,
            pagamento_id=pagamento_id,
            valor=Dinheiro(Decimal("30.00")),
            metodo=MetodoPagamento.DINHEIRO,
            idempotency_key="f14b:confirmacao:replay",
            expected_version=2,
            timestamp=AGORA + timedelta(seconds=3),
        )

    with factory() as session:
        pagamento = session.scalar(
            select(PagamentoORM).where(PagamentoORM.id == pagamento_id)
        )
        assert pagamento is not None
        assert Decimal(str(pagamento.valor_pago)) == Decimal("40.00")
        assert Decimal(str(pagamento.saldo)) == Decimal("60.00")
        assert pagamento.versao == 2
        assert (
            session.scalar(
                select(func.count())
                .select_from(TransacaoPagamentoORM)
                .where(
                    TransacaoPagamentoORM.pagamento_id == pagamento_id,
                    TransacaoPagamentoORM.tipo == "confirmacao",
                )
            )
            == 1
        )


def test_concorrencia_postgresql_serializa_pagamento_e_cashback_sem_saldo_negativo() -> None:
    factory = _factory()
    pagamento_id = "pag-f14b-concorrencia"
    _criar_pagamento(
        factory,
        pagamento_id=pagamento_id,
        pedido_id="pedido-f14b-concorrencia",
        chave="f14b:obrigacao:concorrencia",
    )
    barreira_pagamento = Barrier(2)

    def confirmar_worker(indice: int) -> tuple[str, str]:
        with UnitOfWorkV1(factory) as uow:
            barreira_pagamento.wait(timeout=10)
            try:
                resultado = confirmar_pagamento(
                    contexto=_contexto(f"corr-f14b-race-pay-{indice}"),
                    repositorio=uow.pagamentos,
                    pagamento_id=pagamento_id,
                    valor=Dinheiro(Decimal("70.00")),
                    metodo=MetodoPagamento.DINHEIRO,
                    idempotency_key=f"f14b:confirmacao:race:{indice}",
                    expected_version=1,
                    timestamp=AGORA + timedelta(seconds=10 + indice),
                )
                uow.commit()
                return "ok", str(resultado.pagamento.versao)
            except ConcorrenciaPagamento as exc:
                return "conflito", str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados_pagamento = list(pool.map(confirmar_worker, (1, 2)))

    assert sorted(status for status, _ in resultados_pagamento) == ["conflito", "ok"]
    conflito_pagamento = next(
        detalhe for status, detalhe in resultados_pagamento if status == "conflito"
    )
    assert conflito_pagamento in {
        "versao_pagamento_divergente",
        "compare_and_swap_falhou",
    }

    with factory() as session:
        pagamento = RepositorioPagamentosSQLAlchemy(session).buscar_pagamento(
            TENANT,
            UNIDADE,
            pagamento_id,
        )
        assert pagamento is not None
        assert pagamento.versao == 2
        assert pagamento.valor_pago.valor == Decimal("70.00")
        assert pagamento.saldo.valor == Decimal("30.00")
        assert (
            session.scalar(
                select(func.count())
                .select_from(TransacaoPagamentoORM)
                .where(
                    TransacaoPagamentoORM.pagamento_id == pagamento_id,
                    TransacaoPagamentoORM.tipo == "confirmacao",
                )
            )
            == 1
        )

    legacy_cliente_id = 14002
    cliente_crm_id = "cliente-crm-f14b-race"
    _seed_cliente(
        factory,
        legacy_cliente_id=legacy_cliente_id,
        cliente_crm_id=cliente_crm_id,
    )
    barreira_cashback = Barrier(2)

    def cashback_worker(indice: int) -> tuple[str, str]:
        try:
            with factory.begin() as session:
                barreira_cashback.wait(timeout=10)
                resultado = ServicoCashback(
                    RepositorioCashbackSQLAlchemy(session)
                ).debitar(
                    tenant_id=TENANT,
                    unidade_id=UNIDADE,
                    cliente_id=cliente_crm_id,
                    valor=Decimal("7.00"),
                    origem="f14b_concorrencia",
                    referencia=f"race://cashback/{indice}",
                    idempotency_key=f"f14b:cashback:race:{indice}",
                    ocorrido_em=AGORA + timedelta(seconds=20 + indice),
                )
                return "ok", str(resultado.saldo)
        except ErroCRM as exc:
            return "rejeitado", exc.codigo

    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados_cashback = list(pool.map(cashback_worker, (1, 2)))

    assert sorted(status for status, _ in resultados_cashback) == ["ok", "rejeitado"]
    assert next(
        detalhe for status, detalhe in resultados_cashback if status == "rejeitado"
    ) == "cashback_saldo_insuficiente"

    with factory() as session:
        cashback = RepositorioCashbackSQLAlchemy(session)
        assert (
            cashback.saldo(
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                cliente_id=cliente_crm_id,
            )
            == Decimal("3.00")
        )
        historico = cashback.historico(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_id=cliente_crm_id,
        )
        assert len(historico) == 2
        assert sum(
            (mov.valor_assinado for mov in historico), Decimal("0.00")
        ) == Decimal("3.00")


def test_estorno_e_reconfirmacao_preservam_pdv_e_projecao_cashback() -> None:
    factory = _factory()
    legacy_cliente_id = 14003
    cliente_crm_id = "cliente-crm-f14b-estorno"
    _seed_cliente(
        factory,
        legacy_cliente_id=legacy_cliente_id,
        cliente_crm_id=cliente_crm_id,
    )
    entrada = _entrada_pdv(
        factory,
        checkout_id="checkout-f14b-estorno",
        legacy_cliente_id=legacy_cliente_id,
    )
    contexto = _contexto("corr-f14b-estorno-pdv")
    venda = executar(factory, contexto, entrada, ModoPDV.AUTHORITATIVE_CANARY)
    assert venda.sucesso
    assert venda.pagamento_id is not None
    assert venda.pedido_id is not None

    with factory() as session:
        pagamento_inicial = RepositorioPagamentosSQLAlchemy(session).buscar_pagamento(
            TENANT,
            UNIDADE,
            venda.pagamento_id,
        )
        assert pagamento_inicial is not None
        assert pagamento_inicial.status is PagamentoStatus.PAGO
        valor_liquido = pagamento_inicial.valor_previsto

    with UnitOfWorkV1(factory) as uow:
        estorno = registrar_estorno(
            contexto=_contexto("corr-f14b-estorno"),
            repositorio=uow.pagamentos,
            pagamento_id=venda.pagamento_id,
            valor=valor_liquido,
            motivo="homologacao reversibilidade F14-B",
            idempotency_key="f14b:estorno:ciclo",
            expected_version=pagamento_inicial.versao,
            timestamp=AGORA + timedelta(seconds=30),
        )
        uow.commit()

    assert estorno.pagamento.status is PagamentoStatus.ESTORNADO
    assert estorno.pagamento.saldo == valor_liquido

    with UnitOfWorkV1(factory) as uow:
        reconfirmado = confirmar_pagamento(
            contexto=_contexto("corr-f14b-reconfirmacao"),
            repositorio=uow.pagamentos,
            pagamento_id=venda.pagamento_id,
            valor=valor_liquido,
            metodo=MetodoPagamento.DINHEIRO,
            idempotency_key="f14b:reconfirmacao:ciclo",
            expected_version=estorno.pagamento.versao,
            timestamp=AGORA + timedelta(seconds=31),
        )
        finalizacao = finalizar_pagamento_liquidado_em_transacao(
            recursos=uow.recursos,
            pagamento=reconfirmado.pagamento,
            timestamp=AGORA + timedelta(seconds=31),
        )
        uow.commit()

    assert reconfirmado.pagamento.status is PagamentoStatus.PAGO
    assert reconfirmado.pagamento.saldo.valor == Decimal("0.00")
    assert (
        reconfirmado.pagamento.valor_pago - reconfirmado.pagamento.valor_estornado
        == valor_liquido
    )
    assert finalizacao.finalizada
    assert finalizacao.idempotente

    with factory() as session:
        transacoes = RepositorioPagamentosSQLAlchemy(session).listar_transacoes(
            TENANT,
            UNIDADE,
            venda.pagamento_id,
        )
        assert [trans.tipo.value for trans in transacoes].count("confirmacao") == 2
        assert [trans.tipo.value for trans in transacoes].count("estorno") == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(VendaFinanceiraORM)
                .where(VendaFinanceiraORM.pagamento_id == venda.pagamento_id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(VendaLegadaLinkORM)
                .where(VendaLegadaLinkORM.pedido_id == venda.pedido_id)
            )
            == 1
        )
        reconciliacao = session.scalar(
            select(ReconciliacaoPDVORM).where(
                ReconciliacaoPDVORM.pedido_id == venda.pedido_id
            )
        )
        assert reconciliacao is not None
        assert reconciliacao.status == "conciliado"

        cashback = RecursosTransacionaisV1(session).cashback
        saldo = cashback.saldo(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_id=cliente_crm_id,
        )
        historico = cashback.historico(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_id=cliente_crm_id,
        )
        cliente_legado = session.get(ClienteTeste, legacy_cliente_id)
        assert saldo == Decimal("5.75")
        assert len(historico) == 3
        assert cliente_legado is not None
        assert Decimal(str(cliente_legado.saldo_cashback)) == saldo
