from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from core.assistente_atendimento.atendimento_modelos import (
    CarrinhoAtendimento,
    CotacaoEntregaAtendimento,
    ItemCarrinhoAtendimento,
    ModalidadePedidoAtendimento,
    PreferenciaPagamentoAtendimento,
)
from core.assistente_atendimento.checkout_adapter import CheckoutAssistenteV1
from core.entrega.modelos_orm import EntregaORM, EventoEntregaORM
from core.estoque.modelos_orm import ReservaEstoqueORM
from core.pagamentos.modelos import MetodoPagamento
from core.pagamentos.modelos_orm import PagamentoORM
from core.pedidos.modelos_orm import PedidoORM
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel
from migrations.runner import run_migrations

AGORA = datetime(2026, 8, 31, 23, 40, tzinfo=timezone.utc)
TENANT = "tenant-f4e"
UNIDADE = "unidade-f4e"
ENDERECO_REF = "address://endereco-validado-f4e"


def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    run_migrations(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def _seed_catalogo(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO lojas (id, nome_fantasia) "
                "VALUES (7, 'Loja F4E')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO fm_unidade_loja_legacy_v1 "
                "(tenant_id, unidade_id, loja_id, ativo) "
                "VALUES (:tenant, :unidade, 7, TRUE)"
            ),
            {"tenant": TENANT, "unidade": UNIDADE},
        )
        connection.execute(
            text(
                "INSERT INTO produtos "
                "(id, loja_id, nome, preco_venda) "
                "VALUES (101, 7, 'Produto F4E', 25)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO insumos "
                "(id, loja_id, nome, unidade_medida, saldo_atual, "
                "custo_unitario, dias_alerta_vencimento) "
                "VALUES (11, 7, 'Insumo F4E', 'un', 10, 5, 15)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO fichas_tecnicas "
                "(id, produto_id, insumo_id, quantidade_utilizada) "
                "VALUES (1, 101, 11, 1)"
            )
        )


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id="assistente-atendimento-v1",
        papeis=frozenset({Papel.ATENDIMENTO}),
        permissoes=MATRIZ_PADRAO[Papel.ATENDIMENTO],
        correlation_id="corr-f4e",
        solicitado_em=AGORA,
        origem="test.f4e",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _cotacao() -> CotacaoEntregaAtendimento:
    return CotacaoEntregaAtendimento(
        endereco_formatado="Rua A, 10 - Centro, Cidade - SP, 01000-000",
        cep="01000000",
        place_id="place-f4e",
        latitude=-23.5,
        longitude=-46.6,
        distancia_metros=4200,
        eta_rota_minutos=15,
        area_id="centro",
        nome_area="Centro",
        taxa=Decimal(8),
        sla_minutos=35,
        sla_maxutos=55,
        versao_area=3,
    )


def _carrinho(
    modalidade: ModalidadePedidoAtendimento = ModalidadePedidoAtendimento.ENTREGA,
) -> CarrinhoAtendimento:
    entrega = _cotacao() if modalidade is ModalidadePedidoAtendimento.ENTREGA else None
    return CarrinhoAtendimento(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        conversa_id="conv-f4e",
        mensagem_id="msg-f4e",
        itens=(
            ItemCarrinhoAtendimento(
                produto_id="101",
                nome_produto="Produto F4E",
                quantidade=1,
                preco_unitario=Decimal(25),
            ),
        ),
        fingerprint="fp-f4e",
        modalidade=modalidade,
        endereco_solicitado=(
            "Rua A, 10, CEP 01000-000"
            if modalidade is ModalidadePedidoAtendimento.ENTREGA
            else None
        ),
        entrega=entrega,
        pagamento=PreferenciaPagamentoAtendimento(
            metodo=MetodoPagamento.PIX,
        ),
    )


def test_entrega_do_assistente_usa_mesmo_pedido_checkout_canonico() -> None:
    engine, factory = _factory()
    _seed_catalogo(engine)
    adapter = CheckoutAssistenteV1(
        session_factory=factory,
        agora=lambda: AGORA,
    )

    resultado = adapter.executar(
        contexto=_contexto(),
        carrinho=_carrinho(),
        cliente_ref="cliente-f4e",
        canal="whatsapp",
        metodo=MetodoPagamento.PIX,
        idempotency_key="confirmacao-f4e",
        endereco_ref=ENDERECO_REF,
    )

    assert resultado.pedido_status == "aguardando_confirmacao"
    assert resultado.pagamento_id is not None
    assert resultado.estoque_reservado is True
    assert resultado.entrega_id is not None
    assert resultado.entrega_status == "aguardando_producao"

    with Session(engine) as session:
        pedido = session.scalar(select(PedidoORM))
        pagamento = session.scalar(select(PagamentoORM))
        reserva = session.scalar(select(ReservaEstoqueORM))
        entrega = session.scalar(select(EntregaORM))

        assert pedido is not None and pedido.id == resultado.pedido_id
        assert pagamento is not None and pagamento.pedido_id == pedido.id
        assert reserva is not None and reserva.pedido_id == pedido.id
        assert entrega is not None and entrega.pedido_id == pedido.id
        assert entrega.id == resultado.entrega_id
        assert entrega.endereco_id == ENDERECO_REF
        assert entrega.modalidade == "propria"
        assert entrega.status == "aguardando_producao"


def test_replay_delivery_nao_duplica_pedido_pagamento_reserva_ou_entrega() -> None:
    engine, factory = _factory()
    _seed_catalogo(engine)
    adapter = CheckoutAssistenteV1(
        session_factory=factory,
        agora=lambda: AGORA,
    )

    kwargs = {
        "contexto": _contexto(),
        "carrinho": _carrinho(),
        "cliente_ref": "cliente-f4e",
        "canal": "whatsapp",
        "metodo": MetodoPagamento.PIX,
        "idempotency_key": "confirmacao-f4e-replay",
        "endereco_ref": ENDERECO_REF,
    }
    primeiro = adapter.executar(**kwargs)
    replay = adapter.executar(**kwargs)

    assert replay.pedido_id == primeiro.pedido_id
    assert replay.entrega_id == primeiro.entrega_id
    assert replay.idempotente is True

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(PedidoORM)) == 1
        assert session.scalar(select(func.count()).select_from(PagamentoORM)) == 1
        assert session.scalar(select(func.count()).select_from(ReservaEstoqueORM)) == 1
        assert session.scalar(select(func.count()).select_from(EntregaORM)) == 1
        assert session.scalar(select(func.count()).select_from(EventoEntregaORM)) == 1


def test_retirada_nao_cria_agregado_logistico_delivery() -> None:
    engine, factory = _factory()
    _seed_catalogo(engine)
    adapter = CheckoutAssistenteV1(
        session_factory=factory,
        agora=lambda: AGORA,
    )

    resultado = adapter.executar(
        contexto=_contexto(),
        carrinho=_carrinho(ModalidadePedidoAtendimento.RETIRADA),
        cliente_ref="cliente-f4e",
        canal="whatsapp",
        metodo=MetodoPagamento.PIX,
        idempotency_key="confirmacao-retirada-f4e",
    )

    assert resultado.entrega_id is None
    assert resultado.entrega_status is None
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(PedidoORM)) == 1
        assert session.scalar(select(func.count()).select_from(EntregaORM)) == 0
