from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.central_pedidos.servicos import ServicoComandosCentral
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
from core.estados.maquinas import ErroTransicao
from core.pedidos.adaptador_sqlalchemy import RepositorioPedidosSQLAlchemy
from core.pedidos.modelos_orm import EventoPedidoPersistidoORM, OrdersBase, PedidoORM
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel
from infra.eventos.modelos_orm import EventBusBase, OutboxEventoORM
from infra.seguranca.modelos_orm import EventoAuditoriaORM, SecurityBase

TENANT = "tenant-central-runtime"
UNIDADE = "unidade-central-runtime"
PEDIDO_ID = "pedido-central-runtime"
AGORA = datetime(2026, 8, 13, 16, tzinfo=timezone.utc)


def _infra():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    OrdersBase.metadata.create_all(engine)
    EventBusBase.metadata.create_all(engine)
    SecurityBase.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _contexto(papel: Papel = Papel.ADMINISTRADOR) -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id=f"usuario-{papel.value}",
        papeis=frozenset({papel}),
        permissoes=MATRIZ_PADRAO[papel],
        correlation_id=f"corr-{papel.value}",
        solicitado_em=AGORA,
        origem="central-integration-test",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _pedido() -> Pedido:
    tenant = TenantId(TENANT)
    unidade = UnidadeId(UNIDADE)
    item = ItemPedido(
        id=PedidoItemId("item-central-runtime"),
        tenant_id=tenant,
        unidade_id=unidade,
        produto_id=ProdutoId("produto-central-runtime"),
        nome_produto="Burger Central",
        quantidade=QuantidadeItem(1),
        preco_unitario=Dinheiro("25.00"),
        subtotal=Dinheiro("25.00"),
    )
    return Pedido.novo(
        id=PedidoId(PEDIDO_ID),
        tenant_id=tenant,
        unidade_id=unidade,
        origem=OrigemPedido.PDV,
        canal=CanalAtendimento.PDV,
        status=PedidoStatus.RASCUNHO,
        cliente_id=None,
        criado_em=AGORA,
        atualizado_em=AGORA,
        versao=1,
        correlation_id=CorrelationId("corr-pedido-central"),
        idempotency_key=IdempotencyKey("pedido-central-create"),
        subtotal=Dinheiro("25.00"),
        descontos=Dinheiro("0.00"),
        taxas=Dinheiro("0.00"),
        total=Dinheiro("25.00"),
        itens=(item,),
    )


def _seed(factory) -> None:
    with factory() as session:
        RepositorioPedidosSQLAlchemy(session).salvar(_pedido())
        session.commit()


def test_central_transiciona_no_pedido_canonico_com_outbox_auditoria_e_replay() -> None:
    factory = _infra()
    _seed(factory)
    chave = "central:pedido-central-runtime:1:aguardando_confirmacao"

    with factory() as session:
        resultado = ServicoComandosCentral(session).transicionar(
            contexto=_contexto(),
            pedido_id=PEDIDO_ID,
            destino="aguardando_confirmacao",
            versao_esperada=1,
            idempotency_key=chave,
            precondicoes={"itens_validos": True, "precos_calculados": True},
        )
        assert resultado.pedido.status is PedidoStatus.AGUARDANDO_CONFIRMACAO
        assert not resultado.idempotente
        session.commit()

    with factory() as session:
        pedido = session.scalar(select(PedidoORM).where(PedidoORM.id == PEDIDO_ID))
        assert pedido is not None
        assert pedido.status == "aguardando_confirmacao"
        assert pedido.versao == 2
        assert session.scalar(
            select(func.count()).select_from(EventoPedidoPersistidoORM)
        ) == 1
        assert session.scalar(select(func.count()).select_from(OutboxEventoORM)) == 1
        assert session.scalar(select(func.count()).select_from(EventoAuditoriaORM)) == 1

    with factory() as session:
        replay = ServicoComandosCentral(session).transicionar(
            contexto=_contexto(),
            pedido_id=PEDIDO_ID,
            destino="aguardando_confirmacao",
            versao_esperada=1,
            idempotency_key=chave,
            precondicoes={"itens_validos": True, "precos_calculados": True},
        )
        assert replay.idempotente
        assert replay.pedido.versao == 2
        session.commit()

    with factory() as session:
        assert session.scalar(
            select(func.count()).select_from(EventoPedidoPersistidoORM)
        ) == 1
        assert session.scalar(select(func.count()).select_from(OutboxEventoORM)) == 1
        assert session.scalar(select(func.count()).select_from(EventoAuditoriaORM)) == 1


def test_central_respeita_rbac_e_persiste_apenas_auditoria_da_negativa() -> None:
    factory = _infra()
    _seed(factory)

    with factory() as session:
        with pytest.raises(ErroTransicao) as erro:
            ServicoComandosCentral(session).transicionar(
                contexto=_contexto(Papel.ATENDIMENTO),
                pedido_id=PEDIDO_ID,
                destino="aguardando_confirmacao",
                versao_esperada=1,
                idempotency_key="central-negada",
                precondicoes={"itens_validos": True, "precos_calculados": True},
            )
        assert erro.value.codigo == "permissao_insuficiente"
        session.commit()

    with factory() as session:
        pedido = session.scalar(select(PedidoORM).where(PedidoORM.id == PEDIDO_ID))
        assert pedido is not None
        assert pedido.status == "rascunho"
        assert pedido.versao == 1
        assert session.scalar(select(func.count()).select_from(OutboxEventoORM)) == 0
        auditorias = session.scalars(select(EventoAuditoriaORM)).all()
        assert len(auditorias) == 1
        assert auditorias[0].resultado == "negado"
        assert auditorias[0].motivo == "permissao_insuficiente"
