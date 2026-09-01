from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from application import entrega_transacoes
from application.entrega_transacoes import AplicacaoEntregaV1
from core.entrega import (
    DeliveryBase,
    Entrega,
    ModalidadeEntrega,
    RepositorioEntregaSQLAlchemy,
    ServicoEntrega,
    StatusEntrega,
)
from core.entrega.modelos_orm import EntregaORM, EventoEntregaORM
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel

TENANT = "tenant-sd1e-entrega"
UNIDADE = "unidade-sd1e-entrega"
AGORA = datetime(2026, 8, 27, 20, 0, tzinfo=UTC)


def _contexto() -> ContextoExecucao:
    papel = Papel.EXPEDICAO

    return ContextoExecucao(
        TENANT,
        UNIDADE,
        "expedicao-sd1e",
        frozenset({papel}),
        MATRIZ_PADRAO[papel],
        "corr-sd1e-entrega",
        AGORA,
        "tests.sd1e.entrega",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _nova_entrega(
    entrega_id: str,
    pedido_id: str,
) -> Entrega:
    return Entrega(
        entrega_id=entrega_id,
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        pedido_id=pedido_id,
        endereco_id=f"endereco-{pedido_id}",
        modalidade=ModalidadeEntrega.PROPRIA,
        status=StatusEntrega.AGUARDANDO_PRODUCAO,
        versao=1,
    )


def _infra():
    engine = create_engine(
        "sqlite://",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    DeliveryBase.metadata.create_all(engine)

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    with factory() as session:
        servico = ServicoEntrega(
            RepositorioEntregaSQLAlchemy(session),
            financeiro_resolvido=lambda *_: True,
            pedido_cancelado=lambda *_: False,
            agora=lambda: AGORA,
        )

        servico.criar(
            _nova_entrega(
                "entrega-1",
                "pedido-1",
            ),
            contexto=_contexto(),
            idempotency_key="seed-entrega-1",
        )

        session.commit()

    return engine, factory


def _app(factory) -> AplicacaoEntregaV1:
    return AplicacaoEntregaV1(
        factory,
        agora=lambda: AGORA,
    )


def test_application_entrega_atribuir_commita_agregado_e_evento() -> None:
    engine, factory = _infra()

    resultado = _app(factory).atribuir(
        "entrega-1",
        "driver-1",
        versao_esperada=1,
        contexto=_contexto(),
        idempotency_key="atribuir-driver-1",
    )

    assert resultado.status is StatusEntrega.ATRIBUIDA
    assert resultado.entregador_id == "driver-1"
    assert resultado.versao == 2

    with Session(engine) as session:
        row = session.scalar(
            select(EntregaORM).where(
                EntregaORM.id == "entrega-1",
                EntregaORM.tenant_id == TENANT,
                EntregaORM.unidade_id == UNIDADE,
            )
        )

        assert row is not None
        assert row.status == StatusEntrega.ATRIBUIDA.value
        assert row.entregador_id == "driver-1"
        assert row.versao == 2

        eventos = tuple(
            session.scalars(
                select(EventoEntregaORM).where(
                    EventoEntregaORM.tenant_id == TENANT,
                    EventoEntregaORM.unidade_id == UNIDADE,
                    EventoEntregaORM.entrega_id == "entrega-1",
                )
            )
        )

        assert len(eventos) == 2


def test_application_entrega_rollback_remove_write_parcial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, factory = _infra()

    real = entrega_transacoes.ServicoEntrega.atribuir

    def falhar_depois_do_write(
        self,
        *args,
        **kwargs,
    ):
        real(
            self,
            *args,
            **kwargs,
        )

        raise RuntimeError(
            "falha_depois_do_write_entrega"
        )

    monkeypatch.setattr(
        entrega_transacoes.ServicoEntrega,
        "atribuir",
        falhar_depois_do_write,
    )

    with pytest.raises(
        RuntimeError,
        match="falha_depois_do_write_entrega",
    ):
        _app(factory).atribuir(
            "entrega-1",
            "driver-rollback",
            versao_esperada=1,
            contexto=_contexto(),
            idempotency_key="atribuir-rollback",
        )

    with Session(engine) as session:
        row = session.scalar(
            select(EntregaORM).where(
                EntregaORM.id == "entrega-1",
                EntregaORM.tenant_id == TENANT,
                EntregaORM.unidade_id == UNIDADE,
            )
        )

        assert row is not None
        assert row.status == StatusEntrega.AGUARDANDO_PRODUCAO.value
        assert row.entregador_id is None
        assert row.versao == 1

        eventos = tuple(
            session.scalars(
                select(EventoEntregaORM).where(
                    EventoEntregaORM.tenant_id == TENANT,
                    EventoEntregaORM.unidade_id == UNIDADE,
                    EventoEntregaORM.entrega_id == "entrega-1",
                )
            )
        )

        assert len(eventos) == 1
        assert eventos[0].idempotency_key == "seed-entrega-1"


def test_application_entrega_replay_idempotente_nao_duplica_evento() -> None:
    engine, factory = _infra()
    app = _app(factory)

    primeira = app.atribuir(
        "entrega-1",
        "driver-idem",
        versao_esperada=1,
        contexto=_contexto(),
        idempotency_key="atribuir-idem",
    )

    repetida = app.atribuir(
        "entrega-1",
        "driver-idem",
        versao_esperada=1,
        contexto=_contexto(),
        idempotency_key="atribuir-idem",
    )

    assert repetida == primeira

    with Session(engine) as session:
        eventos = tuple(
            session.scalars(
                select(EventoEntregaORM).where(
                    EventoEntregaORM.tenant_id == TENANT,
                    EventoEntregaORM.unidade_id == UNIDADE,
                    EventoEntregaORM.entrega_id == "entrega-1",
                    EventoEntregaORM.idempotency_key == "atribuir-idem",
                )
            )
        )

        assert len(eventos) == 1
