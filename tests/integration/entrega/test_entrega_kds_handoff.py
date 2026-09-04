from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from application.entrega_kds_handoff import HandoffEntregaKDSV1
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

TENANT = "tenant-f10c"
UNIDADE = "unidade-f10c"
AGORA = datetime(2026, 9, 4, 18, 0, tzinfo=UTC)


def _contexto_kds() -> ContextoExecucao:
    papel = Papel.COZINHA
    return ContextoExecucao(
        TENANT,
        UNIDADE,
        "cozinha-f10c",
        frozenset({papel}),
        MATRIZ_PADRAO[papel],
        "corr-f10c",
        AGORA,
        "tests.f10c.kds",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _contexto_sistema() -> ContextoExecucao:
    return ContextoExecucao.sistema(
        identidade="seed-f10c",
        motivo="seed entrega para handoff KDS",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        correlation_id="corr-seed-f10c",
        solicitado_em=AGORA,
    )


def _infra():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    DeliveryBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as session:
        servico = ServicoEntrega(
            RepositorioEntregaSQLAlchemy(session),
            financeiro_resolvido=lambda *_: True,
            pedido_cancelado=lambda *_: False,
            agora=lambda: AGORA,
        )
        servico.criar(
            Entrega(
                entrega_id="entrega-f10c",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id="pedido-f10c",
                endereco_id="address://f10c",
                modalidade=ModalidadeEntrega.PROPRIA,
                status=StatusEntrega.AGUARDANDO_PRODUCAO,
                versao=1,
            ),
            contexto=_contexto_sistema(),
            idempotency_key="seed-entrega-f10c",
        )
        session.commit()

    return engine, factory


def test_handoff_promove_entrega_e_persiste_evento() -> None:
    engine, factory = _infra()

    resultado = HandoffEntregaKDSV1(factory).notificar_pedido_pronto(
        contexto=_contexto_kds(),
        pedido_id="pedido-f10c",
    )

    assert resultado is not None
    assert resultado.status is StatusEntrega.AGUARDANDO_EXPEDICAO
    assert resultado.producao_pronta_em is not None
    assert resultado.versao == 2

    with Session(engine) as session:
        row = session.scalar(select(EntregaORM).where(EntregaORM.id == "entrega-f10c"))
        assert row is not None
        assert row.status == StatusEntrega.AGUARDANDO_EXPEDICAO.value
        assert row.versao == 2
        eventos = tuple(
            session.scalars(
                select(EventoEntregaORM).where(
                    EventoEntregaORM.entrega_id == "entrega-f10c"
                )
            )
        )
        assert len(eventos) == 2
        assert eventos[-1].tipo == "entrega.aguardando_expedicao"
        assert eventos[-1].idempotency_key == "kds:entrega:pedido-pronto:pedido-f10c"


def test_handoff_replay_nao_duplica_evento_nem_versao() -> None:
    engine, factory = _infra()
    handoff = HandoffEntregaKDSV1(factory)

    primeira = handoff.notificar_pedido_pronto(
        contexto=_contexto_kds(),
        pedido_id="pedido-f10c",
    )
    repetida = handoff.notificar_pedido_pronto(
        contexto=_contexto_kds(),
        pedido_id="pedido-f10c",
    )

    assert primeira is not None
    assert repetida is not None
    assert repetida.versao == primeira.versao == 2

    with Session(engine) as session:
        eventos_pronto = tuple(
            session.scalars(
                select(EventoEntregaORM).where(
                    EventoEntregaORM.entrega_id == "entrega-f10c",
                    EventoEntregaORM.tipo == "entrega.aguardando_expedicao",
                )
            )
        )
        assert len(eventos_pronto) == 1


def test_handoff_ignora_pedido_sem_entrega_canonica() -> None:
    _, factory = _infra()

    resultado = HandoffEntregaKDSV1(factory).notificar_pedido_pronto(
        contexto=_contexto_kds(),
        pedido_id="pedido-retirada-sem-entrega",
    )

    assert resultado is None
