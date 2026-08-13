from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from application.pagbank_reconciliacao import reconciliar_order_pagbank_em_transacao
from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import PagamentoStatus
from core.pagamentos.adapters import CobrancaProvedor
from core.pagamentos.modelos import (
    MetodoPagamento,
    StatusTransacao,
    TipoTransacao,
    TransacaoPagamento,
)
from core.pagamentos.servicos import criar_obrigacao_pagamento
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
    with UnitOfWorkV1(factory) as uow:
        inicio = criar_obrigacao_pagamento(
            contexto=contexto,
            repositorio=uow.pagamentos,
            pagamento_id=PAGAMENTO,
            pedido_id="pedido-reconciliacao",
            valor_previsto=Dinheiro("38.90"),
            metodo=MetodoPagamento.PIX,
            idempotency_key="obrigacao-reconciliacao",
            timestamp=AGORA,
            provedor="pagbank",
        )
        uow.registrar_efeitos(eventos=inicio.eventos, auditorias=inicio.auditorias)
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
