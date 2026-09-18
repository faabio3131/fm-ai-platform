from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.dominio.enums import PedidoStatus
from core.dominio.ids import PedidoId, TenantId, UnidadeId
from core.integracoes.catalogo import CATALOGO_V1
from core.marketplaces.modelos import (
    ItemMarketplace,
    PedidoExterno,
    PedidoMarketplaceSnapshot,
    PlataformaMarketplace,
    StatusPedidoExterno,
)
from core.pedidos.adaptador_sqlalchemy import RepositorioPedidosSQLAlchemy
from core.pedidos.modelos_orm import OrdersBase
from infra.eventos.modelos_orm import EventBusBase
from infra.gerente_ia.modelos_orm import CoreRuntimeBase
from infra.marketplaces.modelos_orm import MarketplaceBase
from infra.marketplaces.repositorio_sqlalchemy import (
    PedidosInternosMarketplaceSQLAlchemy,
    RepositorioPedidosExternosSQLAlchemy,
)
from infra.seguranca.modelos_orm import SecurityBase

TENANT = "tenant-wp012"
UNIDADE = "unidade-wp012"
OUTRA = "unidade-wp012-b"
AGORA = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


def _factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SecurityBase.metadata.create_all(engine)
    OrdersBase.metadata.create_all(engine)
    EventBusBase.metadata.create_all(engine)
    CoreRuntimeBase.metadata.create_all(engine)
    MarketplaceBase.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _snapshot(
    status: StatusPedidoExterno = StatusPedidoExterno.RECEBIDO,
) -> PedidoMarketplaceSnapshot:
    return PedidoMarketplaceSnapshot(
        id_externo="ifood-order-1",
        merchant_id="merchant-1",
        status=status,
        total=Decimal("42.00"),
        itens=(
            ItemMarketplace(
                item_id_externo="item-1",
                sku="SKU-EXTERNO-NAO-MAPEADO",
                nome="Combo marketplace",
                quantidade=Decimal(2),
                preco_unitario=Decimal("20.00"),
            ),
        ),
        atualizado_em=AGORA,
        versao_externa="1",
    )


def test_catalogo_expoe_ifood_e_keeta_sem_inventar_99food() -> None:
    specs = {
        (item.servico, item.provedor): item for item in CATALOGO_V1.listar()
    }
    assert ("marketplace.pedidos", "ifood") in specs
    assert ("marketplace.pedidos", "keeta") in specs
    assert ("marketplace.pedidos", "99food") not in specs
    assert specs[("marketplace.pedidos", "ifood")].credenciais_obrigatorias == {
        "client_id",
        "client_secret",
    }


def test_marketplace_cria_pedido_canonico_e_preserva_snapshot() -> None:
    factory = _factory()
    with factory() as session:
        adapter = PedidosInternosMarketplaceSQLAlchemy(
            session,
            plataforma=PlataformaMarketplace.IFOOD,
        )
        pedido_id, repetido = adapter.criar_ou_obter(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            integracao_id="marketplace.pedidos--ifood",
            snapshot=_snapshot(),
            idempotency_key="marketplace:pedido:ifood:1",
        )
        assert repetido is False

        pedido = RepositorioPedidosSQLAlchemy(session).buscar(
            TenantId(TENANT),
            UnidadeId(UNIDADE),
            PedidoId(pedido_id),
        )
        assert pedido is not None
        assert pedido.status is PedidoStatus.RASCUNHO
        assert pedido.origem.value == "ifood"
        assert pedido.canal.value == "ifood"
        assert pedido.total.valor == Decimal("42.00")
        assert pedido.subtotal.valor == Decimal("40.00")
        assert pedido.taxas.valor == Decimal("2.00")
        assert pedido.itens[0].produto_id is None
        assert pedido.itens[0].nome_produto == "Combo marketplace"

        mesmo_id, idempotente = adapter.criar_ou_obter(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            integracao_id="marketplace.pedidos--ifood",
            snapshot=_snapshot(),
            idempotency_key="marketplace:pedido:ifood:1",
        )
        assert idempotente is True
        assert mesmo_id == pedido_id


def test_status_marketplace_somente_avanca_estados_comerciais_seguros() -> None:
    factory = _factory()
    with factory() as session:
        adapter = PedidosInternosMarketplaceSQLAlchemy(
            session,
            plataforma=PlataformaMarketplace.IFOOD,
        )
        pedido_id, _ = adapter.criar_ou_obter(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            integracao_id="marketplace.pedidos--ifood",
            snapshot=_snapshot(),
            idempotency_key="marketplace:pedido:ifood:2",
        )
        status = adapter.atualizar_status_marketplace(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            pedido_id=pedido_id,
            status=StatusPedidoExterno.RECEBIDO,
            idempotency_key="evt-recebido",
        )
        assert status == "aguardando_confirmacao"

        status = adapter.atualizar_status_marketplace(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            pedido_id=pedido_id,
            status=StatusPedidoExterno.CONFIRMADO,
            idempotency_key="evt-confirmado",
        )
        assert status == "confirmado"

        status = adapter.atualizar_status_marketplace(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            pedido_id=pedido_id,
            status=StatusPedidoExterno.PRONTO,
            idempotency_key="evt-pronto",
        )
        assert status == "confirmado"


def test_vinculo_externo_e_isolado_por_unidade() -> None:
    factory = _factory()
    pedido = PedidoExterno(
        integracao_id="marketplace.pedidos--ifood",
        id_externo="ifood-order-1",
        pedido_id="pedido-1",
        status_externo=StatusPedidoExterno.RECEBIDO,
        status_interno="aguardando_confirmacao",
        payload_hash="abc123",
        recebido_em=AGORA,
        ultima_ocorrencia_em=AGORA,
        ultimo_evento_id="evt-1",
        versao_externa="1",
    )
    with factory() as session:
        repo = RepositorioPedidosExternosSQLAlchemy(
            session,
            tenant_id=TENANT,
            unidade_id=UNIDADE,
        )
        repo.salvar(pedido)
        session.commit()

        outra_unidade = RepositorioPedidosExternosSQLAlchemy(
            session,
            tenant_id=TENANT,
            unidade_id=OUTRA,
        )
        assert (
            outra_unidade.obter(
                integracao_id=pedido.integracao_id,
                id_externo=pedido.id_externo,
            )
            is None
        )
        assert repo.obter(
            integracao_id=pedido.integracao_id,
            id_externo=pedido.id_externo,
        ) == pedido
