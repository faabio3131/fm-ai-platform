from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from application.checkout import ComandoCheckoutV1, executar_checkout_v1
from application.order_result_orchestrator import (
    orquestrar_resultado_pagamento_em_transacao,
)
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
from core.estoque.modelos import ItemSnapshotFicha, SnapshotFichaEstoque, StatusReserva, TipoMovimento
from core.estoque.modelos_orm import MovimentoEstoqueORM, ReservaEstoqueORM
from core.estoque.servicos import registrar_movimento
from core.pagamentos.modelos import MetodoPagamento
from core.pagamentos.modelos_orm import VendaFinanceiraORM
from core.pagamentos.servicos import confirmar_pagamento
from core.pedidos.modelos_orm import PedidoORM
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel
from infra.transacoes.uow import UnitOfWorkV1
from migrations.runner import run_migrations

AGORA = datetime(2026, 8, 31, 23, 0, tzinfo=timezone.utc)
TENANT = "tenant-f4d"
UNIDADE = "unidade-f4d"
PEDIDO = "pedido-f4d"
PAGAMENTO = "pagamento-f4d"


def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    run_migrations(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id="atendente-f4d",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=MATRIZ_PADRAO[Papel.ADMINISTRADOR],
        correlation_id="corr-f4d",
        solicitado_em=AGORA,
        origem="test.f4d",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _pedido() -> Pedido:
    tenant = TenantId(TENANT)
    unidade = UnidadeId(UNIDADE)
    item = ItemPedido(
        id=PedidoItemId("item-f4d"),
        tenant_id=tenant,
        unidade_id=unidade,
        produto_id=ProdutoId("produto-f4d"),
        nome_produto="Produto F4-D",
        quantidade=QuantidadeItem(1),
        preco_unitario=Dinheiro("30"),
        subtotal=Dinheiro("30"),
    )
    return Pedido(
        id=PedidoId(PEDIDO),
        tenant_id=tenant,
        unidade_id=unidade,
        origem=OrigemPedido.WHATSAPP,
        canal=CanalAtendimento.WHATSAPP,
        status=PedidoStatus.RASCUNHO,
        cliente_id=None,
        criado_em=AGORA,
        atualizado_em=AGORA,
        versao=1,
        correlation_id=CorrelationId("corr-f4d"),
        idempotency_key=IdempotencyKey("checkout:f4d"),
        subtotal=Dinheiro("30"),
        descontos=Dinheiro(0),
        taxas=Dinheiro(0),
        total=Dinheiro("30"),
        itens=(item,),
        observacoes=(),
    )


def _snapshot() -> SnapshotFichaEstoque:
    return SnapshotFichaEstoque(
        pedido_id=PEDIDO,
        versao_ficha="ficha-f4d-v1",
        capturado_em=AGORA,
        itens=(
            ItemSnapshotFicha(
                produto_id="produto-f4d",
                item_pedido_id="item-f4d",
                insumo_id="insumo-f4d",
                quantidade_por_unidade=Decimal(2),
                quantidade_total=Decimal(2),
                unidade_medida="un",
            ),
        ),
    )


def _seed_checkout(factory) -> None:
    with UnitOfWorkV1(factory) as uow:
        entrada = registrar_movimento(
            contexto=_contexto(),
            repositorio=uow.estoque,
            insumo_id="insumo-f4d",
            tipo=TipoMovimento.ENTRADA,
            quantidade_movimento=10,
            unidade_medida="un",
            origem_tipo="compra",
            origem_id="seed-f4d",
            origem_versao=1,
            idempotency_key="seed:f4d",
            motivo="seed f4d",
        )
        uow.registrar_efeitos(eventos=entrada.eventos, auditorias=entrada.auditorias)
        uow.commit()
    executar_checkout_v1(
        comando=ComandoCheckoutV1(
            pedido=_pedido(),
            timestamp=AGORA,
            pagamento_id=PAGAMENTO,
            metodo_pagamento=MetodoPagamento.DINHEIRO,
            snapshot_estoque=_snapshot(),
        ),
        contexto=_contexto(),
        session_factory=factory,
    )


def _pagamento(factory):
    with UnitOfWorkV1(factory) as uow:
        pagamento = uow.pagamentos.buscar_pagamento(TENANT, UNIDADE, PAGAMENTO)
        assert pagamento is not None
        return pagamento


def test_pagamento_pendente_nao_confirma_pedido_nem_consume_reserva() -> None:
    engine, factory = _factory()
    _seed_checkout(factory)
    pagamento = _pagamento(factory)

    with UnitOfWorkV1(factory) as uow:
        resultado = orquestrar_resultado_pagamento_em_transacao(
            recursos=uow.recursos,
            pagamento=pagamento,
            timestamp=AGORA,
        )
        uow.commit()

    assert resultado.finalizado is False
    assert resultado.pedido_status is PedidoStatus.AGUARDANDO_CONFIRMACAO
    assert resultado.reserva_status is StatusReserva.ATIVA
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(VendaFinanceiraORM)) == 0
        assert session.scalar(select(PedidoORM.status).where(PedidoORM.id == PEDIDO)) == "aguardando_confirmacao"
        tipos = tuple(session.scalars(select(MovimentoEstoqueORM.tipo_movimento)))
        assert "consumo" not in tipos


def test_pagamento_liquidado_confirma_pedido_reconhece_venda_sem_consumir_estoque() -> None:
    engine, factory = _factory()
    _seed_checkout(factory)

    with UnitOfWorkV1(factory) as uow:
        pagamento = uow.pagamentos.buscar_pagamento(TENANT, UNIDADE, PAGAMENTO)
        assert pagamento is not None
        confirmado = confirmar_pagamento(
            contexto=_contexto(),
            repositorio=uow.pagamentos,
            pagamento_id=PAGAMENTO,
            valor=Dinheiro("30"),
            valor_recebido=Dinheiro("30"),
            metodo=MetodoPagamento.DINHEIRO,
            idempotency_key="confirmacao:f4d",
            expected_version=pagamento.versao,
            timestamp=AGORA,
            referencia_externa="operacional:caixa-f4d",
        )
        uow.registrar_efeitos(
            eventos=confirmado.eventos,
            auditorias=confirmado.auditorias,
        )
        resultado = orquestrar_resultado_pagamento_em_transacao(
            recursos=uow.recursos,
            pagamento=confirmado.pagamento,
            timestamp=AGORA,
        )
        uow.commit()

    assert resultado.finalizado is True
    assert resultado.pedido_status is PedidoStatus.CONFIRMADO
    assert resultado.venda_financeira_id is not None
    assert resultado.reserva_status is StatusReserva.ATIVA
    assert resultado.producao_status == ()
    assert resultado.producao_iniciada is False

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(VendaFinanceiraORM)) == 1
        reserva = session.scalar(select(ReservaEstoqueORM))
        assert reserva is not None and reserva.status == StatusReserva.ATIVA.value
        tipos = tuple(session.scalars(select(MovimentoEstoqueORM.tipo_movimento)))
        assert "consumo" not in tipos


def test_replay_do_resultado_financeiro_nao_duplica_venda_ou_efeitos() -> None:
    engine, factory = _factory()
    _seed_checkout(factory)

    with UnitOfWorkV1(factory) as uow:
        pagamento = uow.pagamentos.buscar_pagamento(TENANT, UNIDADE, PAGAMENTO)
        assert pagamento is not None
        confirmado = confirmar_pagamento(
            contexto=_contexto(),
            repositorio=uow.pagamentos,
            pagamento_id=PAGAMENTO,
            valor=Dinheiro("30"),
            valor_recebido=Dinheiro("30"),
            metodo=MetodoPagamento.DINHEIRO,
            idempotency_key="confirmacao:f4d",
            expected_version=pagamento.versao,
            timestamp=AGORA,
        )
        uow.registrar_efeitos(eventos=confirmado.eventos, auditorias=confirmado.auditorias)
        primeiro = orquestrar_resultado_pagamento_em_transacao(
            recursos=uow.recursos,
            pagamento=confirmado.pagamento,
            timestamp=AGORA,
        )
        uow.commit()

    with UnitOfWorkV1(factory) as uow:
        pago = uow.pagamentos.buscar_pagamento(TENANT, UNIDADE, PAGAMENTO)
        assert pago is not None
        replay = orquestrar_resultado_pagamento_em_transacao(
            recursos=uow.recursos,
            pagamento=pago,
            timestamp=AGORA,
        )
        uow.commit()

    assert primeiro.finalizado is True
    assert replay.finalizado is True
    assert replay.idempotente is True
    assert replay.venda_financeira_id == primeiro.venda_financeira_id
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(VendaFinanceiraORM)) == 1
        assert session.scalar(select(func.count()).select_from(ReservaEstoqueORM)) == 1
        tipos = tuple(session.scalars(select(MovimentoEstoqueORM.tipo_movimento)))
        assert "consumo" not in tipos
