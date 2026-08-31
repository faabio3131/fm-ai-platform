from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from application.checkout import ComandoCheckoutV1, executar_checkout_em_transacao
from application.pagbank_reconciliacao import reconciliar_order_pagbank_em_transacao
from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import (
    CanalAtendimento,
    OrigemPedido,
    PagamentoStatus,
    PedidoStatus,
)
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
from core.pagamentos.adapters import CobrancaProvedor
from core.pagamentos.modelos import (
    MetodoPagamento,
    StatusTransacao,
    TipoTransacao,
    TransacaoPagamento,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel
from infra.transacoes.uow import UnitOfWorkV1
from migrations.runner import run_migrations

AGORA = datetime(2026, 8, 12, 23, 20, tzinfo=timezone.utc)
TENANT = "tenant-reconciliacao"
UNIDADE = "unidade-reconciliacao"
PAGAMENTO = "pay-reconciliacao"
ORDER = "ORDE_RECONCILIACAO_1"


class PagBankConsultaFake:
    def __init__(self, status: str) -> None:
        self.status = status
        self.consultas: list[str] = []

    def consultar_transacao(self, order_id: str):
        self.consultas.append(order_id)
        return CobrancaProvedor(order_id, self.status, Dinheiro("38.90"))


def _factory():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id="admin-reconciliacao",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=MATRIZ_PADRAO[Papel.ADMINISTRADOR],
        correlation_id="corr-reconciliacao",
        solicitado_em=AGORA,
        origem="integration-test",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _seed(factory) -> None:
    contexto = _contexto()
    tenant = TenantId(TENANT)
    unidade = UnidadeId(UNIDADE)
    pedido = Pedido(
        id=PedidoId("pedido-reconciliacao"),
        tenant_id=tenant,
        unidade_id=unidade,
        origem=OrigemPedido.WHATSAPP,
        canal=CanalAtendimento.WHATSAPP,
        status=PedidoStatus.RASCUNHO,
        cliente_id=None,
        criado_em=AGORA,
        atualizado_em=AGORA,
        versao=1,
        correlation_id=CorrelationId(contexto.correlation_id),
        idempotency_key=IdempotencyKey("checkout-reconciliacao"),
        subtotal=Dinheiro("38.90"),
        descontos=Dinheiro(0),
        taxas=Dinheiro(0),
        total=Dinheiro("38.90"),
        itens=(
            ItemPedido(
                id=PedidoItemId("item-reconciliacao"),
                tenant_id=tenant,
                unidade_id=unidade,
                produto_id=ProdutoId("produto-reconciliacao"),
                nome_produto="Produto reconciliação",
                quantidade=QuantidadeItem(1),
                preco_unitario=Dinheiro("38.90"),
                subtotal=Dinheiro("38.90"),
            ),
        ),
        observacoes=(),
    )
    with UnitOfWorkV1(factory) as uow:
        checkout = executar_checkout_em_transacao(
            comando=ComandoCheckoutV1(
                pedido=pedido,
                timestamp=AGORA,
                pagamento_id=PAGAMENTO,
                metodo_pagamento=MetodoPagamento.PIX,
                provedor_pagamento="pagbank",
            ),
            contexto=contexto,
            recursos=uow.recursos,
        )
        assert checkout.pagamento is not None
        uow.pagamentos.append_transacao(
            TransacaoPagamento(
                str(uuid4()),
                PAGAMENTO,
                TENANT,
                UNIDADE,
                TipoTransacao.INICIACAO,
                StatusTransacao.PENDENTE,
                Dinheiro(0),
                MetodoPagamento.PIX,
                "pagbank",
                ORDER,
                "pagbank:order:reconciliacao",
                AGORA,
                AGORA,
                contexto.correlation_id,
                None,
                (("order_status", "pendente"),),
            ),
            "fp-order-reconciliacao",
        )
        uow.commit()


def _status(factory) -> PagamentoStatus:
    with UnitOfWorkV1(factory) as uow:
        pagamento = uow.pagamentos.buscar_pagamento(TENANT, UNIDADE, PAGAMENTO)
        assert pagamento is not None
        return pagamento.status


def test_consulta_pagbank_paga_confirma_pix_sem_webhook() -> None:
    factory = _factory()
    _seed(factory)
    adapter = PagBankConsultaFake("pago")

    with UnitOfWorkV1(factory) as uow:
        resultado = reconciliar_order_pagbank_em_transacao(
            recursos=uow.recursos,
            adapter=adapter,  # type: ignore[arg-type]
            order_id=ORDER,
            timestamp=AGORA,
        )
        assert resultado is not None
        assert resultado.pagamento.status is PagamentoStatus.PAGO
        uow.commit()

    assert adapter.consultas == [ORDER]
    assert _status(factory) is PagamentoStatus.PAGO


def test_consulta_pagbank_pendente_nao_promove_pagamento() -> None:
    factory = _factory()
    _seed(factory)
    adapter = PagBankConsultaFake("pendente")

    with UnitOfWorkV1(factory) as uow:
        assert (
            reconciliar_order_pagbank_em_transacao(
                recursos=uow.recursos,
                adapter=adapter,  # type: ignore[arg-type]
                order_id=ORDER,
                timestamp=AGORA,
            )
            is None
        )
        uow.commit()

    assert _status(factory) is PagamentoStatus.PENDENTE


def test_reconciliacao_paga_e_idempotente_no_replay() -> None:
    factory = _factory()
    _seed(factory)
    adapter = PagBankConsultaFake("paid")

    with UnitOfWorkV1(factory) as uow:
        primeiro = reconciliar_order_pagbank_em_transacao(
            recursos=uow.recursos,
            adapter=adapter,  # type: ignore[arg-type]
            order_id=ORDER,
            timestamp=AGORA,
        )
        assert primeiro is not None and not primeiro.idempotente
        uow.commit()

    with UnitOfWorkV1(factory) as uow:
        replay = reconciliar_order_pagbank_em_transacao(
            recursos=uow.recursos,
            adapter=adapter,  # type: ignore[arg-type]
            order_id=ORDER,
            timestamp=AGORA,
        )
        assert replay is not None and replay.idempotente
        uow.commit()

    assert _status(factory) is PagamentoStatus.PAGO
