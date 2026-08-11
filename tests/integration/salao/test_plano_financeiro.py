from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.dominio.enums import PagamentoStatus
from core.pagamentos.modelos_orm import (
    ObrigacaoPagamentoORM,
    PagamentoORM,
    PaymentsBase,
    VendaFinanceiraORM,
)
from core.pedidos.modelos_orm import OrdersBase, PedidoORM
from core.salao import (
    ErroSalao,
    MetodoFechamento,
    RepositorioSalaoSQLAlchemy,
    SalaoBase,
    ServicoSalao,
)
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel

AGORA = datetime(2026, 8, 11, 14, 30, tzinfo=UTC)
TENANT = "tenant-1"
UNIDADE = "unidade-1"


def contexto() -> ContextoExecucao:
    papel = Papel.GERENTE
    return ContextoExecucao(
        TENANT,
        UNIDADE,
        "gerente-1",
        frozenset({papel}),
        MATRIZ_PADRAO[papel],
        "corr-plano",
        AGORA,
        "pytest",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def ambiente() -> tuple[Session, ServicoSalao, ContextoExecucao]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    OrdersBase.metadata.create_all(engine)
    PaymentsBase.metadata.create_all(engine)
    SalaoBase.metadata.create_all(engine)
    session = Session(engine)
    return session, ServicoSalao(RepositorioSalaoSQLAlchemy(session), agora=lambda: AGORA), contexto()


def adicionar_pedido(session: Session, pedido_id: str = "pedido-1") -> None:
    session.add(
        PedidoORM(
            id=pedido_id,
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            origem="salao",
            canal="mesa",
            status="confirmado",
            cliente_id=None,
            criado_em=AGORA,
            atualizado_em=AGORA,
            versao=1,
            correlation_id=f"corr-{pedido_id}",
            idempotency_key=f"idem-{pedido_id}",
            request_hash=f"hash-{pedido_id}",
            subtotal=Decimal("10.00"),
            descontos=Decimal("0.00"),
            taxas=Decimal("0.00"),
            total=Decimal("10.00"),
        )
    )
    session.flush()


def abrir_com_consumo(session: Session, servico: ServicoSalao, ctx: ContextoExecucao):
    mesa = servico.cadastrar_mesa(
        ctx,
        mesa_id="mesa-1",
        codigo="01",
        capacidade=4,
        idempotency_key="mesa:1",
    )
    adicionar_pedido(session)
    comanda = servico.abrir_comanda(
        ctx,
        comanda_id="cmd-1",
        numero="C1",
        mesa_id=mesa.mesa_id,
        expected_mesa_version=mesa.versao,
        idempotency_key="abrir:1",
    )
    return servico.vincular_pedido(
        ctx,
        comanda_id=comanda.comanda_id,
        pedido_id="pedido-1",
        expected_version=comanda.versao,
        idempotency_key="vincular:1",
    )


def adicionar_pagamento_pago(session: Session, comanda_id: str) -> None:
    session.add(
        ObrigacaoPagamentoORM(
            id="pay-1",
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            pedido_id="pedido-1",
            comanda_id=comanda_id,
            valor_previsto=Decimal("10.00"),
            moeda="BRL",
            criado_em=AGORA,
            versao=1,
            correlation_id="corr-pay",
            idempotency_key="obrigacao-pay",
            request_hash="hash-obrigacao-pay",
        )
    )
    session.flush()
    session.add(
        PagamentoORM(
            id="pay-1",
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            pedido_id="pedido-1",
            comanda_id=comanda_id,
            status=PagamentoStatus.PAGO.value,
            metodo="dinheiro",
            valor_previsto=Decimal("10.00"),
            valor_pago=Decimal("10.00"),
            valor_estornado=Decimal("0.00"),
            saldo=Decimal("0.00"),
            moeda="BRL",
            recebimento_posterior=False,
            provedor="pytest",
            criado_em=AGORA,
            atualizado_em=AGORA,
            versao=1,
            correlation_id="corr-pay",
            idempotency_key="pagamento-pay",
            request_hash="hash-pagamento-pay",
        )
    )
    session.flush()


def test_pagamento_confirmado_deve_corresponder_a_parcela_planejada() -> None:
    session, servico, ctx = ambiente()
    with session.begin():
        comanda = abrir_com_consumo(session, servico, ctx)
        comanda = servico.solicitar_conta(
            ctx,
            comanda_id=comanda.comanda_id,
            expected_version=comanda.versao,
            idempotency_key="conta:1",
        )
        comanda, _ = servico.definir_divisao_pagamento(
            ctx,
            comanda_id=comanda.comanda_id,
            expected_version=comanda.versao,
            idempotency_key="dividir:1",
            divisoes=((MetodoFechamento.PIX, Decimal("10.00"), None),),
        )
        adicionar_pagamento_pago(session, comanda.comanda_id)
        with pytest.raises(ErroSalao) as erro:
            servico.registrar_pagamento_confirmado(
                ctx,
                comanda_id=comanda.comanda_id,
                pagamento_id="pay-1",
                metodo=MetodoFechamento.DINHEIRO,
                valor=Decimal("10.00"),
                expected_version=comanda.versao,
                idempotency_key="projetar:fora-plano",
            )
        assert erro.value.codigo == "pagamento_fora_plano"


def test_cancelamento_rejeita_venda_financeira_ja_reconhecida() -> None:
    session, servico, ctx = ambiente()
    with session.begin():
        comanda = abrir_com_consumo(session, servico, ctx)
        session.add(
            VendaFinanceiraORM(
                id="venda-1",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id="pedido-1",
                pagamento_id=None,
                comanda_id=comanda.comanda_id,
                criterio_codigo="teste",
                criterio_versao=1,
                valor=Decimal("10.00"),
                moeda="BRL",
                metodo="pix",
                reconhecida_em=AGORA,
                correlation_id="corr-venda",
                idempotency_key="venda-1",
                request_hash="hash-venda-1",
            )
        )
        session.flush()
        with pytest.raises(ErroSalao) as erro:
            servico.cancelar_comanda(
                ctx,
                comanda_id=comanda.comanda_id,
                expected_version=comanda.versao,
                idempotency_key="cancelar:venda",
                pedidos_resolvidos=True,
            )
        assert erro.value.codigo == "comanda_com_venda_reconhecida_nao_pode_cancelar"
