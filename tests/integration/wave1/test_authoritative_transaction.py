from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import CanalAtendimento, OrigemPedido, PedidoStatus
from core.dominio.ids import (
    CorrelationId,
    IdempotencyKey,
    PedidoId,
    PedidoItemId,
    ProdutoId,
    TenantId,
    UnidadeId,
)
from core.dominio.pedidos import ItemPedido, Pedido
from core.dominio.tipos import QuantidadeItem
from core.pedidos.modelos_orm import EventoPedidoPersistidoORM, PedidoORM
from core.pedidos.servicos import registrar_novo_pedido, transicionar_pedido
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel
from infra.eventos.modelos_orm import OutboxEventoORM
from infra.seguranca.modelos_orm import EventoAuditoriaORM
from infra.transacoes.uow import UnitOfWorkV1
from migrations.runner import run_migrations


def _factory():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def _context() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="tenant-1",
        unidade_id="loja-1",
        usuario_id="admin-1",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=MATRIZ_PADRAO[Papel.ADMINISTRADOR],
        correlation_id="corr-pedido-1",
        solicitado_em=datetime.now(timezone.utc),
        origem="tests",
        unidades_permitidas=frozenset({"loja-1"}),
    )


def _order() -> Pedido:
    now = datetime.now(timezone.utc)
    item = ItemPedido(
        id=PedidoItemId("item-1"),
        produto_id=ProdutoId("produto-1"),
        nome_snapshot="X-Bacon",
        quantidade=QuantidadeItem(1),
        preco_unitario=Dinheiro(Decimal("30.00")),
        subtotal=Dinheiro(Decimal("30.00")),
    )
    return Pedido.novo(
        id=PedidoId("pedido-1"),
        tenant_id=TenantId("tenant-1"),
        unidade_id=UnidadeId("loja-1"),
        origem=OrigemPedido.BALCAO,
        canal=CanalAtendimento.PRESENCIAL,
        itens=(item,),
        subtotal=Dinheiro(Decimal("30.00")),
        desconto=Dinheiro.zero(),
        taxa_entrega=Dinheiro.zero(),
        total=Dinheiro(Decimal("30.00")),
        criado_em=now,
        atualizado_em=now,
        correlation_id=CorrelationId("corr-pedido-1"),
        idempotency_key=IdempotencyKey("pedido-create-1"),
    )


def _counts(engine) -> tuple[int, int, int, int]:
    with Session(engine) as session:
        return (
            session.scalar(select(func.count()).select_from(PedidoORM)) or 0,
            session.scalar(select(func.count()).select_from(EventoPedidoPersistidoORM))
            or 0,
            session.scalar(select(func.count()).select_from(OutboxEventoORM)) or 0,
            session.scalar(select(func.count()).select_from(EventoAuditoriaORM)) or 0,
        )


def test_creation_commits_order_history_outbox_and_audit_together() -> None:
    engine, factory = _factory()
    pedido = _order()
    contexto = _context()

    with UnitOfWorkV1(factory) as uow:
        result = registrar_novo_pedido(
            pedido=pedido,
            contexto=contexto,
            repositorio=uow.pedidos,
            outbox=uow.outbox,
            auditoria=uow.auditoria,
        )
        assert result.idempotente is False
        assert result.pedido.status is PedidoStatus.RASCUNHO
        assert result.evento.event_type == "pedidocriado.v1"
        uow.commit()

    assert _counts(engine) == (1, 1, 1, 1)


def test_creation_replay_is_persistently_idempotent_after_new_session() -> None:
    engine, factory = _factory()
    pedido = _order()
    contexto = _context()
    with UnitOfWorkV1(factory) as uow:
        registrar_novo_pedido(
            pedido=pedido,
            contexto=contexto,
            repositorio=uow.pedidos,
            outbox=uow.outbox,
            auditoria=uow.auditoria,
        )
        uow.commit()

    with UnitOfWorkV1(factory) as uow:
        replay = registrar_novo_pedido(
            pedido=pedido,
            contexto=contexto,
            repositorio=uow.pedidos,
            outbox=uow.outbox,
            auditoria=uow.auditoria,
        )
        assert replay.idempotente is True
        uow.commit()

    assert _counts(engine) == (1, 1, 1, 1)


def test_state_transition_is_persistently_idempotent() -> None:
    engine, factory = _factory()
    contexto = _context()
    with UnitOfWorkV1(factory) as uow:
        registrar_novo_pedido(
            pedido=_order(),
            contexto=contexto,
            repositorio=uow.pedidos,
            outbox=uow.outbox,
            auditoria=uow.auditoria,
        )
        uow.commit()

    transition_key = IdempotencyKey("pedido-to-confirmacao-1")
    timestamp = datetime.now(timezone.utc)
    with UnitOfWorkV1(factory) as uow:
        result = transicionar_pedido(
            tenant_id=TenantId("tenant-1"),
            unidade_id=UnidadeId("loja-1"),
            pedido_id=PedidoId("pedido-1"),
            destino=PedidoStatus.AGUARDANDO_CONFIRMACAO,
            versao_esperada=1,
            idempotency_key=transition_key,
            contexto=contexto,
            repositorio=uow.pedidos,
            outbox=uow.outbox,
            auditoria=uow.auditoria,
            timestamp=timestamp,
            precondicoes={"itens_validos": True, "precos_calculados": True},
        )
        assert result.pedido.status is PedidoStatus.AGUARDANDO_CONFIRMACAO
        assert result.pedido.versao == 2
        uow.commit()

    with UnitOfWorkV1(factory) as uow:
        replay = transicionar_pedido(
            tenant_id=TenantId("tenant-1"),
            unidade_id=UnidadeId("loja-1"),
            pedido_id=PedidoId("pedido-1"),
            destino=PedidoStatus.AGUARDANDO_CONFIRMACAO,
            versao_esperada=1,
            idempotency_key=transition_key,
            contexto=contexto,
            repositorio=uow.pedidos,
            outbox=uow.outbox,
            auditoria=uow.auditoria,
            timestamp=timestamp,
            precondicoes={"itens_validos": True, "precos_calculados": True},
        )
        assert replay.idempotente is True
        assert replay.pedido.versao == 2
        uow.commit()

    assert _counts(engine) == (1, 2, 2, 2)


def test_uow_rolls_back_everything_when_operation_fails() -> None:
    engine, factory = _factory()
    contexto = _context()

    with pytest.raises(RuntimeError, match="falha depois dos efeitos"):
        with UnitOfWorkV1(factory) as uow:
            registrar_novo_pedido(
                pedido=_order(),
                contexto=contexto,
                repositorio=uow.pedidos,
                outbox=uow.outbox,
                auditoria=uow.auditoria,
            )
            raise RuntimeError("falha depois dos efeitos")

    assert _counts(engine) == (0, 0, 0, 0)
