from dataclasses import replace
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.orm import Session

from core.dominio.dinheiro import Dinheiro
from core.dominio.erros import ConflitoIdempotencia
from core.dominio.eventos import PedidoCriado
from core.dominio.ids import EventoId, IdempotencyKey, PedidoId, TenantId, UnidadeId
from core.pedidos.adaptador_sqlalchemy import RepositorioPedidosSQLAlchemy
from core.pedidos.erros import EscopoPedidoInvalido, PedidoConcorrente
from core.pedidos.modelos_orm import EventoPedidoPersistidoORM
from migrations.orders_v1 import downgrade, upgrade
from tests.unit.orders.factories import pedido


@pytest.fixture
def engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def fk(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    upgrade(engine)
    yield engine
    engine.dispose()


def test_upgrade_indices_constraints_roundtrip_e_downgrade(engine):
    insp = inspect(engine)
    assert set(insp.get_table_names()) == {
        "pedidos_v1",
        "itens_pedido_v1",
        "adicionais_item_pedido_v1",
        "observacoes_pedido_v1",
        "eventos_pedido_v1",
    }
    indices = {i["name"] for i in insp.get_indexes("pedidos_v1")}
    assert {
        "ix_pedido_escopo_id",
        "ix_pedido_escopo_status",
        "ix_pedido_escopo_criado",
        "ix_pedido_escopo_idempotencia",
    } <= indices
    with Session(engine) as session:
        repo = RepositorioPedidosSQLAlchemy(session)
        salvo = repo.salvar(pedido())
        session.commit()
        lido = repo.buscar(salvo.tenant_id, salvo.unidade_id, salvo.id)
        assert lido == salvo
        assert lido.total.valor == Dinheiro("24.00").valor
    downgrade(engine)
    assert inspect(engine).get_table_names() == []


def test_idempotencia_exata_conflito_e_isolamento(engine):
    with Session(engine) as session:
        repo = RepositorioPedidosSQLAlchemy(session)
        original = pedido()
        assert repo.salvar(original) == repo.salvar(original)
        with pytest.raises(ConflitoIdempotencia):
            repo.salvar(
                replace(
                    original,
                    id=PedidoId("pedido-2"),
                    total=Dinheiro("25.00"),
                    taxas=Dinheiro("4.00"),
                )
            )
        session.commit()
        assert repo.buscar(TenantId("outro"), original.unidade_id, original.id) is None
        assert repo.buscar(original.tenant_id, UnidadeId("outra"), original.id) is None
        assert repo.listar(TenantId("outro"), UnidadeId("outra")) == ()


def test_optimistic_locking_e_rollback(engine):
    with Session(engine) as session:
        repo = RepositorioPedidosSQLAlchemy(session)
        original = repo.salvar(pedido())
        session.commit()
        atualizado = replace(
            original, versao=2, atualizado_em=datetime(2026, 8, 9, tzinfo=timezone.utc)
        )
        repo.salvar(atualizado, versao_esperada=1)
        session.commit()
        assert (
            repo.obter_versao(original.tenant_id, original.unidade_id, original.id) == 2
        )
        with pytest.raises(PedidoConcorrente) as erro:
            repo.salvar(replace(atualizado, versao=3), versao_esperada=1)
        assert erro.value.codigo == "pedido_concorrente"
        session.rollback()
        assert (
            repo.obter_versao(original.tenant_id, original.unidade_id, original.id) == 2
        )


def test_evento_persistido_escopado(engine):
    with Session(engine) as session:
        repo = RepositorioPedidosSQLAlchemy(session)
        original = repo.salvar(pedido())
        evento = PedidoCriado(
            event_id=EventoId("evento-1"),
            aggregate_id=str(original.id),
            aggregate_type="Pedido",
            tenant_id=original.tenant_id,
            unidade_id=original.unidade_id,
            correlation_id=original.correlation_id,
            causation_id=None,
            idempotency_key=IdempotencyKey("evt-idem-1"),
            occurred_at=original.criado_em,
            payload={"total": "24.00"},
            version=1,
        )
        repo.salvar_eventos(
            original.tenant_id, original.unidade_id, original.id, (evento,)
        )
        assert session.scalar(select(EventoPedidoPersistidoORM)).payload == {
            "total": "24.00"
        }
        with pytest.raises(EscopoPedidoInvalido):
            repo.salvar_eventos(
                TenantId("outro"), original.unidade_id, original.id, (evento,)
            )


def test_transaction_rollback_nao_persiste(engine):
    with Session(engine) as session:
        repo = RepositorioPedidosSQLAlchemy(session)
        repo.salvar(pedido())
        session.rollback()
    with Session(engine) as session:
        assert (
            RepositorioPedidosSQLAlchemy(session).listar(
                TenantId("tenant-a"), UnidadeId("unidade-a")
            )
            == ()
        )
