from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from core.estoque.modelos import (
    ItemSnapshotFicha,
    SnapshotFichaEstoque,
    StatusReserva,
    TipoMovimento,
)
from core.estoque.servicos import (
    consumir_reserva,
    liberar_reserva,
    registrar_movimento,
    reservar_estoque,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel
from infra.eventos.modelos_orm import OutboxEventoORM
from infra.seguranca.modelos_orm import EventoAuditoriaORM
from infra.transacoes.uow import UnitOfWorkV1
from migrations.runner import run_migrations

AGORA = datetime(2026, 8, 12, 22, tzinfo=timezone.utc)


def _factory():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="tenant-1",
        unidade_id="loja-1",
        usuario_id="admin-1",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=MATRIZ_PADRAO[Papel.ADMINISTRADOR],
        correlation_id="corr-stock",
        solicitado_em=AGORA,
        origem="integration-test",
        unidades_permitidas=frozenset({"loja-1"}),
    )


def _snapshot(pedido_id: str, quantidade: str = "3") -> SnapshotFichaEstoque:
    return SnapshotFichaEstoque(
        pedido_id=pedido_id,
        versao_ficha="ficha-1",
        capturado_em=AGORA,
        itens=(
            ItemSnapshotFicha(
                produto_id="produto-1",
                item_pedido_id=f"item-{pedido_id}",
                insumo_id="carne",
                quantidade_por_unidade=Decimal(quantidade),
                quantidade_total=Decimal(quantidade),
                unidade_medida="un",
            ),
        ),
    )


def _entrada(uow: UnitOfWorkV1) -> None:
    resultado = registrar_movimento(
        contexto=_contexto(),
        repositorio=uow.estoque,
        insumo_id="carne",
        tipo=TipoMovimento.ENTRADA,
        quantidade_movimento="10",
        unidade_medida="un",
        origem_tipo="compra",
        origem_id="compra-1",
        origem_versao=1,
        idempotency_key="entrada-carne-1",
        motivo="estoque inicial de teste",
    )
    uow.registrar_efeitos(eventos=resultado.eventos, auditorias=resultado.auditorias)


def test_reserva_e_consumo_sql_persistem_saldo_eventos_e_auditoria() -> None:
    engine, factory = _factory()
    with UnitOfWorkV1(factory) as uow:
        _entrada(uow)
        reserva = reservar_estoque(
            contexto=_contexto(),
            repositorio=uow.estoque,
            pedido_id="pedido-1",
            pedido_version=1,
            snapshot_ficha=_snapshot("pedido-1"),
            idempotency_key="reserva-pedido-1",
        )
        uow.registrar_efeitos(eventos=reserva.eventos, auditorias=reserva.auditorias)
        assert reserva.reserva and reserva.reserva.status is StatusReserva.ATIVA
        saldo = uow.estoque.consultar_saldo("tenant-1", "loja-1", "carne")
        assert saldo.saldo_fisico == Decimal("10")
        assert saldo.saldo_reservado == Decimal("3")
        uow.commit()

    with UnitOfWorkV1(factory) as uow:
        consumo = consumir_reserva(
            contexto=_contexto(),
            repositorio=uow.estoque,
            pedido_id="pedido-1",
            pedido_version=2,
            idempotency_key="consumo-pedido-1",
        )
        uow.registrar_efeitos(eventos=consumo.eventos, auditorias=consumo.auditorias)
        saldo = uow.estoque.consultar_saldo("tenant-1", "loja-1", "carne")
        assert saldo.saldo_fisico == Decimal("7")
        assert saldo.saldo_reservado == Decimal("0")
        reserva = uow.estoque.buscar_reserva("tenant-1", "loja-1", "pedido-1")
        assert reserva and reserva.status is StatusReserva.CONSUMIDA
        uow.commit()

    with UnitOfWorkV1(factory) as uow:
        replay = consumir_reserva(
            contexto=_contexto(),
            repositorio=uow.estoque,
            pedido_id="pedido-1",
            pedido_version=2,
            idempotency_key="consumo-pedido-1",
        )
        assert replay.idempotente is True
        assert replay.eventos == ()
        assert replay.auditorias == ()
        saldo = uow.estoque.consultar_saldo("tenant-1", "loja-1", "carne")
        assert saldo.saldo_fisico == Decimal("7")
        assert saldo.saldo_reservado == Decimal("0")
        uow.commit()

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(OutboxEventoORM)) == 3
        assert session.scalar(select(func.count()).select_from(EventoAuditoriaORM)) == 3


def test_liberacao_sql_devolve_disponibilidade_sem_baixar_fisico() -> None:
    _, factory = _factory()
    with UnitOfWorkV1(factory) as uow:
        _entrada(uow)
        reserva = reservar_estoque(
            contexto=_contexto(),
            repositorio=uow.estoque,
            pedido_id="pedido-cancelado",
            pedido_version=1,
            snapshot_ficha=_snapshot("pedido-cancelado", "4"),
            idempotency_key="reserva-cancelada",
        )
        uow.registrar_efeitos(eventos=reserva.eventos, auditorias=reserva.auditorias)
        uow.commit()

    with UnitOfWorkV1(factory) as uow:
        liberacao = liberar_reserva(
            contexto=_contexto(),
            repositorio=uow.estoque,
            pedido_id="pedido-cancelado",
            pedido_version=2,
            idempotency_key="libera-cancelada",
            motivo="pedido cancelado",
        )
        uow.registrar_efeitos(eventos=liberacao.eventos, auditorias=liberacao.auditorias)
        saldo = uow.estoque.consultar_saldo("tenant-1", "loja-1", "carne")
        assert saldo.saldo_fisico == Decimal("10")
        assert saldo.saldo_reservado == Decimal("0")
        reserva = uow.estoque.buscar_reserva(
            "tenant-1", "loja-1", "pedido-cancelado"
        )
        assert reserva and reserva.status is StatusReserva.LIBERADA
        uow.commit()
