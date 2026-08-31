from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from application.catalogo_estoque_cutover import (
    ErroCatalogoEstoqueCutover,
    executar_checkout_com_ficha_estoque_v1,
)
from application.checkout import ComandoCheckoutV1
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
from core.estoque.erros import ConflitoIdempotenciaEstoque, SaldoInsuficiente
from core.estoque.modelos_orm import (
    MovimentoEstoqueORM,
    ReservaEstoqueORM,
    SaldoEstoqueORM,
)
from core.pagamentos.modelos import MetodoPagamento
from core.pagamentos.modelos_orm import PagamentoORM
from core.pedidos.modelos_orm import PedidoORM
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel
from migrations.runner import run_migrations

AGORA = datetime(2026, 8, 31, 18, 45, tzinfo=timezone.utc)


def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, factory


def _seed_catalogo(
    engine,
    *,
    saldo: str = "10",
    quantidade_ficha: str = "1.5",
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO lojas (id, nome_fantasia) "
                "VALUES (7, 'Loja A'), (8, 'Loja B')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO fm_unidade_loja_legacy_v1 "
                "(tenant_id, unidade_id, loja_id, ativo) VALUES "
                "('tenant-a', 'unidade-a', 7, TRUE), "
                "('tenant-b', 'unidade-b', 8, TRUE)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO produtos "
                "(id, loja_id, nome, preco_venda) VALUES "
                "(101, 7, 'Produto A', 25), "
                "(201, 8, 'Produto B', 30)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO insumos "
                "(id, loja_id, nome, unidade_medida, saldo_atual, "
                "custo_unitario, dias_alerta_vencimento) VALUES "
                "(11, 7, 'Carne A', 'kg', :saldo, 20, 15), "
                "(21, 8, 'Carne B', 'kg', 30, 25, 15)"
            ),
            {"saldo": float(Decimal(saldo))},
        )
        connection.execute(
            text(
                "INSERT INTO fichas_tecnicas "
                "(id, produto_id, insumo_id, quantidade_utilizada) VALUES "
                "(1, 101, 11, :quantidade), "
                "(2, 201, 21, 1)"
            ),
            {"quantidade": float(Decimal(quantidade_ficha))},
        )


def _contexto(
    tenant: str = "tenant-a",
    unidade: str = "unidade-a",
) -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=tenant,
        unidade_id=unidade,
        usuario_id="assistente-atendimento-v1",
        papeis=frozenset({Papel.ATENDIMENTO}),
        permissoes=MATRIZ_PADRAO[Papel.ATENDIMENTO],
        correlation_id=f"corr:{tenant}:{unidade}",
        solicitado_em=AGORA,
        origem="teste_f4_ficha_estoque",
        unidades_permitidas=frozenset({unidade}),
        identidade_sistema=True,
        motivo_sistema="teste do cutover governado do Assistente",
    )


def _pedido(
    *,
    pedido_id: str = "pedido-a",
    tenant: str = "tenant-a",
    unidade: str = "unidade-a",
    produto_id: str = "101",
    quantidade: int = 2,
) -> Pedido:
    tenant_id = TenantId(tenant)
    unidade_id = UnidadeId(unidade)
    item = ItemPedido(
        id=PedidoItemId(f"item:{pedido_id}"),
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        produto_id=ProdutoId(produto_id),
        nome_produto="Produto A",
        quantidade=QuantidadeItem(quantidade),
        preco_unitario=Dinheiro("25"),
        subtotal=Dinheiro(str(25 * quantidade)),
    )
    return Pedido(
        id=PedidoId(pedido_id),
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        origem=OrigemPedido.WHATSAPP,
        canal=CanalAtendimento.WHATSAPP,
        status=PedidoStatus.RASCUNHO,
        cliente_id=None,
        criado_em=AGORA,
        atualizado_em=AGORA,
        versao=1,
        correlation_id=CorrelationId(f"corr:{tenant}:{unidade}"),
        idempotency_key=IdempotencyKey(f"checkout:{pedido_id}"),
        subtotal=Dinheiro(str(25 * quantidade)),
        descontos=Dinheiro(0),
        taxas=Dinheiro(0),
        total=Dinheiro(str(25 * quantidade)),
        itens=(item,),
        observacoes=(),
    )


def _comando(pedido: Pedido) -> ComandoCheckoutV1:
    return ComandoCheckoutV1(
        pedido=pedido,
        timestamp=AGORA,
        pagamento_id=f"pay:{pedido.id}",
        metodo_pagamento=MetodoPagamento.DINHEIRO,
    )


def _contagem(session: Session, model) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_checkout_assistente_captura_ficha_e_reserva_ledger_canonico() -> None:
    engine, factory = _factory()
    _seed_catalogo(engine, saldo="10", quantidade_ficha="1.5")
    pedido = _pedido()

    resultado = executar_checkout_com_ficha_estoque_v1(
        comando=_comando(pedido),
        contexto=_contexto(),
        session_factory=factory,
    )

    assert resultado.reserva is not None
    assert resultado.reserva.reserva is not None
    snapshot = resultado.reserva.reserva.snapshot
    assert snapshot.pedido_id == str(pedido.id)
    assert snapshot.versao_ficha.startswith("legacy-ficha-sha256:")
    assert len(snapshot.itens) == 1
    item = snapshot.itens[0]
    assert item.produto_id == "101"
    assert item.item_pedido_id == "item:pedido-a"
    assert item.insumo_id == "legacy:insumo:11"
    assert item.quantidade_por_unidade == Decimal("1.5")
    assert item.quantidade_total == Decimal("3.0")
    assert item.unidade_medida == "kg"

    with Session(engine) as session:
        saldo = session.get(
            SaldoEstoqueORM,
            {
                "tenant_id": "tenant-a",
                "unidade_id": "unidade-a",
                "insumo_id": "legacy:insumo:11",
            },
        )
        assert saldo is not None
        assert Decimal(str(saldo.saldo_fisico)) == Decimal(10)
        assert Decimal(str(saldo.saldo_reservado)) == Decimal(3)
        assert _contagem(session, ReservaEstoqueORM) == 1


def test_replay_mesma_ficha_e_idempotente_sem_novo_bootstrap() -> None:
    engine, factory = _factory()
    _seed_catalogo(engine)
    pedido = _pedido()
    comando = _comando(pedido)

    executar_checkout_com_ficha_estoque_v1(
        comando=comando,
        contexto=_contexto(),
        session_factory=factory,
    )
    replay = executar_checkout_com_ficha_estoque_v1(
        comando=comando,
        contexto=_contexto(),
        session_factory=factory,
    )

    assert replay.pedido.idempotente is True
    assert replay.pagamento is not None and replay.pagamento.idempotente is True
    assert replay.reserva is not None and replay.reserva.idempotente is True
    with Session(engine) as session:
        assert _contagem(session, ReservaEstoqueORM) == 1
        assert _contagem(session, MovimentoEstoqueORM) == 2


def test_ficha_mudou_no_replay_falha_fechado_e_preserva_snapshot_original() -> None:
    engine, factory = _factory()
    _seed_catalogo(engine, saldo="10", quantidade_ficha="1")
    pedido = _pedido()
    comando = _comando(pedido)

    primeiro = executar_checkout_com_ficha_estoque_v1(
        comando=comando,
        contexto=_contexto(),
        session_factory=factory,
    )
    assert primeiro.reserva is not None and primeiro.reserva.reserva is not None
    versao_original = primeiro.reserva.reserva.snapshot.versao_ficha

    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE fichas_tecnicas SET quantidade_utilizada = 2 "
                "WHERE id = 1"
            )
        )

    with pytest.raises(ConflitoIdempotenciaEstoque):
        executar_checkout_com_ficha_estoque_v1(
            comando=comando,
            contexto=_contexto(),
            session_factory=factory,
        )

    with Session(engine) as session:
        reserva = session.scalar(select(ReservaEstoqueORM))
        assert reserva is not None
        assert reserva.snapshot["versao_ficha"] == versao_original
        assert _contagem(session, PedidoORM) == 1
        assert _contagem(session, PagamentoORM) == 1


def test_saldo_insuficiente_reverte_bootstrap_pedido_pagamento_e_reserva() -> None:
    engine, factory = _factory()
    _seed_catalogo(engine, saldo="2", quantidade_ficha="1.5")
    pedido = _pedido()

    with pytest.raises(SaldoInsuficiente):
        executar_checkout_com_ficha_estoque_v1(
            comando=_comando(pedido),
            contexto=_contexto(),
            session_factory=factory,
        )

    with Session(engine) as session:
        assert _contagem(session, PedidoORM) == 0
        assert _contagem(session, PagamentoORM) == 0
        assert _contagem(session, ReservaEstoqueORM) == 0
        assert _contagem(session, MovimentoEstoqueORM) == 0
        assert _contagem(session, SaldoEstoqueORM) == 0


def test_produto_de_outra_unidade_nao_pode_gerar_snapshot() -> None:
    engine, factory = _factory()
    _seed_catalogo(engine)
    pedido = _pedido(
        pedido_id="pedido-b",
        tenant="tenant-b",
        unidade="unidade-b",
        produto_id="101",
    )

    with pytest.raises(RuntimeError):
        executar_checkout_com_ficha_estoque_v1(
            comando=_comando(pedido),
            contexto=_contexto("tenant-b", "unidade-b"),
            session_factory=factory,
        )

    with Session(engine) as session:
        assert _contagem(session, PedidoORM) == 0
        assert _contagem(session, ReservaEstoqueORM) == 0


def test_divergencia_entre_legado_e_ledger_bloqueia_novo_checkout() -> None:
    engine, factory = _factory()
    _seed_catalogo(engine, saldo="10", quantidade_ficha="1")
    primeiro = _pedido(pedido_id="pedido-primeiro")
    executar_checkout_com_ficha_estoque_v1(
        comando=_comando(primeiro),
        contexto=_contexto(),
        session_factory=factory,
    )

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE insumos SET saldo_atual = 9 WHERE id = 11")
        )

    segundo = _pedido(pedido_id="pedido-segundo")
    with pytest.raises(
        ErroCatalogoEstoqueCutover,
        match="estoque_legado_divergente_do_ledger",
    ):
        executar_checkout_com_ficha_estoque_v1(
            comando=_comando(segundo),
            contexto=_contexto(),
            session_factory=factory,
        )

    with Session(engine) as session:
        assert _contagem(session, PedidoORM) == 1
        assert _contagem(session, ReservaEstoqueORM) == 1
