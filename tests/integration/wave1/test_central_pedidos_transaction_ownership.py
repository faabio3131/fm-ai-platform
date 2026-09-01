from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from application import central_pedidos_transacoes
from application.central_pedidos_transacoes import (
    AplicacaoCentralPedidosTransacoesV1,
)
from core.dominio.enums import PedidoStatus
from core.estados.maquinas import ErroTransicao
from core.pagamentos.modelos_orm import PaymentsBase
from core.pdv.modelos_orm import PDVBase
from core.pedidos.adaptador_sqlalchemy import (
    RepositorioPedidosSQLAlchemy,
)
from core.pedidos.modelos_orm import OrdersBase
from core.seguranca import (
    ContextoExecucao,
    Papel,
    Permissao,
)
from infra.eventos.modelos_orm import EventBusBase
from infra.gerente_ia.modelos_orm import CoreRuntimeBase
from infra.seguranca.modelos_orm import SecurityBase
from tests.unit.orders.factories import pedido

AGORA = datetime(
    2026,
    8,
    28,
    13,
    30,
    tzinfo=UTC,
)


def _contexto(
    *,
    pode_alterar: bool = True,
) -> ContextoExecucao:
    permissoes = {
        Permissao.PEDIDO_VISUALIZAR,
    }

    if pode_alterar:
        permissoes.add(
            Permissao.PEDIDO_ALTERAR
        )

    return ContextoExecucao(
        "tenant-a",
        "unidade-a",
        "operador-central",
        frozenset(
            {
                Papel.CAIXA,
            }
        ),
        frozenset(
            permissoes
        ),
        "corr-central-sd1e14",
        AGORA,
        "tests.sd1e.central_pedidos",
        unidades_permitidas=frozenset(
            {
                "unidade-a",
            }
        ),
    )


def _infra():
    engine = create_engine(
        "sqlite://",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    OrdersBase.metadata.create_all(
        engine
    )
    PaymentsBase.metadata.create_all(
        engine
    )
    PDVBase.metadata.create_all(
        engine
    )
    EventBusBase.metadata.create_all(
        engine
    )
    CoreRuntimeBase.metadata.create_all(
        engine
    )
    SecurityBase.metadata.create_all(
        engine
    )

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    with factory() as session:
        RepositorioPedidosSQLAlchemy(
            session
        ).salvar(
            pedido()
        )
        session.commit()

    application = (
        AplicacaoCentralPedidosTransacoesV1(
            factory
        )
    )

    return (
        engine,
        application,
    )


def _estado_pedido(
    engine,
) -> tuple[str, int]:
    with Session(engine) as session:
        row = session.execute(
            text(
                """
                SELECT status, versao
                FROM pedidos_v1
                WHERE id = 'pedido-1'
                  AND tenant_id = 'tenant-a'
                  AND unidade_id = 'unidade-a'
                """
            )
        ).one()

        return (
            str(row.status),
            int(row.versao),
        )


def _count(
    engine,
    table: str,
) -> int:
    with Session(engine) as session:
        return int(
            session.execute(
                text(
                    f"SELECT COUNT(*) FROM {table}"
                )
            ).scalar_one()
        )


def test_transicao_central_commita_pedido_outbox_e_auditoria() -> None:
    engine, application = _infra()

    resultado = application.transicionar(
        contexto=_contexto(),
        pedido_id="pedido-1",
        destino="aguardando_confirmacao",
        versao_esperada=1,
        idempotency_key=(
            "central-sd1e14-sucesso"
        ),
        precondicoes={
            "itens_validos": True,
            "precos_calculados": True,
        },
        metadata={
            "origem_ui":
                "central_pedidos"
        },
    )

    assert (
        resultado.status
        is PedidoStatus.AGUARDANDO_CONFIRMACAO
    )

    assert _estado_pedido(
        engine
    ) == (
        "aguardando_confirmacao",
        2,
    )

    assert _count(
        engine,
        "event_outbox_v1",
    ) >= 1

    assert _count(
        engine,
        "fm_auditoria_v1",
    ) >= 1


def test_transicao_negada_commita_trilha_sem_alterar_pedido() -> None:
    engine, application = _infra()

    with pytest.raises(
        ErroTransicao
    ) as erro:
        application.transicionar(
            contexto=_contexto(
                pode_alterar=False
            ),
            pedido_id="pedido-1",
            destino=(
                "aguardando_confirmacao"
            ),
            versao_esperada=1,
            idempotency_key=(
                "central-sd1e14-negado"
            ),
            precondicoes={
                "itens_validos": True,
                "precos_calculados": True,
            },
        )

    assert (
        erro.value.codigo
        == "permissao_insuficiente"
    )

    assert _estado_pedido(
        engine
    ) == (
        "rascunho",
        1,
    )

    with Session(engine) as session:
        resultados = session.execute(
            text(
                """
                SELECT resultado
                FROM fm_auditoria_v1
                ORDER BY timestamp
                """
            )
        ).scalars().all()

    assert "negado" in resultados


def test_falha_no_commit_faz_rollback_integral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, application = _infra()

    def commit_com_falha(
        uow,
    ) -> None:
        uow.flush()

        raise RuntimeError(
            "falha_commit_central"
        )

    monkeypatch.setattr(
        central_pedidos_transacoes.UnitOfWorkV1,
        "commit",
        commit_com_falha,
    )

    with pytest.raises(
        RuntimeError,
        match="falha_commit_central",
    ):
        application.transicionar(
            contexto=_contexto(),
            pedido_id="pedido-1",
            destino=(
                "aguardando_confirmacao"
            ),
            versao_esperada=1,
            idempotency_key=(
                "central-sd1e14-rollback"
            ),
            precondicoes={
                "itens_validos": True,
                "precos_calculados": True,
            },
        )

    assert _estado_pedido(
        engine
    ) == (
        "rascunho",
        1,
    )

    assert _count(
        engine,
        "event_outbox_v1",
    ) == 0

    assert _count(
        engine,
        "fm_auditoria_v1",
    ) == 0
