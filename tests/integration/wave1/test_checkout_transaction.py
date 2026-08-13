from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from application.checkout import ComandoCheckoutV1, executar_checkout_v1
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
from core.estoque.erros import SaldoInsuficiente
from core.estoque.modelos import ItemSnapshotFicha, SnapshotFichaEstoque, TipoMovimento
from core.estoque.modelos_orm import ReservaEstoqueORM
from core.estoque.servicos import registrar_movimento
from core.pagamentos.modelos import MetodoPagamento
from core.pagamentos.modelos_orm import PagamentoORM
from core.pedidos.modelos_orm import PedidoORM
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
        correlation_id="corr-checkout",
        solicitado_em=AGORA,
        origem="integration-test",
        unidades_permitidas=frozenset({"loja-1"}),
    )


def _pedido(pedido_id: str = "pedido-checkout") -> Pedido:
    tenant = TenantId("tenant-1")
    unidade = UnidadeId("loja-1")
    item = ItemPedido(
        id=PedidoItemId(f"item-{pedido_id}"),
        tenant_id=tenant,
        unidade_id=unidade,
        produto_id=ProdutoId("x-bacon"),
        nome_produto="X-Bacon",
        quantidade=QuantidadeItem(1),
        preco_unitario=Dinheiro("30"),
        subtotal=Dinheiro("30"),
    )
    return Pedido(
        id=PedidoId(pedido_id),
        tenant_id=tenant,
        unidade_id=unidade,
        origem=OrigemPedido.PDV,
        canal=CanalAtendimento.PDV,
        status=PedidoStatus.RASCUNHO,
        cliente_id=None,
        criado_em=AGORA,
        atualizado_em=AGORA,
        versao=1,
        correlation_id=CorrelationId("corr-checkout"),
        idempotency_key=IdempotencyKey(f"checkout:{pedido_id}"),
        subtotal=Dinheiro("30"),
        descontos=Dinheiro(0),
        taxas=Dinheiro(0),
        total=Dinheiro("30"),
        itens=(item,),
        observacoes=(),
    )


def _snapshot(pedido_id: str, quantidade: str) -> SnapshotFichaEstoque:
    return SnapshotFichaEstoque(
        pedido_id=pedido_id,
        versao_ficha="ficha-x-bacon-v1",
        capturado_em=AGORA,
        itens=(
            ItemSnapshotFicha(
                produto_id="x-bacon",
                item_pedido_id=f"item-{pedido_id}",
                insumo_id="carne",
                quantidade_por_unidade=Decimal(quantidade),
                quantidade_total=Decimal(quantidade),
                unidade_medida="un",
            ),
        ),
    )


def _seed_estoque(factory, quantidade: str) -> None:
    with UnitOfWorkV1(factory) as uow:
        entrada = registrar_movimento(
            contexto=_contexto(),
            repositorio=uow.estoque,
            insumo_id="carne",
            tipo=TipoMovimento.ENTRADA,
            quantidade_movimento=quantidade,
            unidade_medida="un",
            origem_tipo="compra",
            origem_id="seed",
            origem_versao=1,
            idempotency_key="seed:carne",
            motivo="seed de integração",
        )
        uow.registrar_efeitos(eventos=entrada.eventos, auditorias=entrada.auditorias)
        uow.commit()


def _contagem(session: Session, model) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_checkout_commita_pedido_pagamento_reserva_eventos_e_auditoria_uma_vez() -> None:
    engine, factory = _factory()
    _seed_estoque(factory, "10")
    pedido = _pedido()
    comando = ComandoCheckoutV1(
        pedido=pedido,
        timestamp=AGORA,
        pagamento_id="pay-checkout",
        metodo_pagamento=MetodoPagamento.DINHEIRO,
        snapshot_estoque=_snapshot(str(pedido.id), "2"),
    )

    primeiro = executar_checkout_v1(
        comando=comando, contexto=_contexto(), session_factory=factory
    )
    assert (
        primeiro.aguardando_confirmacao.pedido.status
        is PedidoStatus.AGUARDANDO_CONFIRMACAO
    )
    assert primeiro.pagamento and primeiro.pagamento.pagamento.pedido_id == str(pedido.id)
    assert primeiro.reserva and primeiro.reserva.reserva is not None

    replay = executar_checkout_v1(
        comando=comando, contexto=_contexto(), session_factory=factory
    )
    assert replay.pedido.idempotente is True
    assert replay.pagamento and replay.pagamento.idempotente is True
    assert replay.reserva and replay.reserva.idempotente is True
    assert replay.aguardando_confirmacao.idempotente is True

    with Session(engine) as session:
        assert _contagem(session, PedidoORM) == 1
        assert _contagem(session, PagamentoORM) == 1
        assert _contagem(session, ReservaEstoqueORM) == 1
        # Seed + pedido + pagamento + reserva + transição do pedido.
        assert _contagem(session, OutboxEventoORM) == 5
        assert _contagem(session, EventoAuditoriaORM) == 5


def test_checkout_com_saldo_insuficiente_faz_rollback_de_pedido_e_pagamento() -> None:
    engine, factory = _factory()
    _seed_estoque(factory, "1")
    pedido = _pedido("pedido-sem-saldo")
    comando = ComandoCheckoutV1(
        pedido=pedido,
        timestamp=AGORA,
        pagamento_id="pay-sem-saldo",
        metodo_pagamento=MetodoPagamento.PIX,
        snapshot_estoque=_snapshot(str(pedido.id), "3"),
        provedor_pagamento="sandbox",
    )

    with pytest.raises(SaldoInsuficiente):
        executar_checkout_v1(
            comando=comando, contexto=_contexto(), session_factory=factory
        )

    with Session(engine) as session:
        assert _contagem(session, PedidoORM) == 0
        assert _contagem(session, PagamentoORM) == 0
        assert _contagem(session, ReservaEstoqueORM) == 0
        # Somente o seed, que foi transação anterior independente, pode existir.
        assert _contagem(session, OutboxEventoORM) == 1
        assert _contagem(session, EventoAuditoriaORM) == 1
