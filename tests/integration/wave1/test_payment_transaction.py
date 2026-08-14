from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import PagamentoStatus
from core.pagamentos.adapters import ProvedorPagamentoFake
from core.pagamentos.erros import FonteFinanceiraNaoConfiavel
from core.pagamentos.modelos import MetodoPagamento
from core.pagamentos.modelos_orm import PagamentoORM, TransacaoPagamentoORM
from core.pagamentos.servicos import (
    confirmar_pagamento,
    criar_obrigacao_pagamento,
    processar_webhook,
)
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
        usuario_id="financeiro-1",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=MATRIZ_PADRAO[Papel.ADMINISTRADOR],
        correlation_id="corr-payment",
        solicitado_em=AGORA,
        origem="integration-test",
        unidades_permitidas=frozenset({"loja-1"}),
    )


def test_pix_manual_falha_fechado_e_webhook_assinado_liquida_em_sql() -> None:
    engine, factory = _factory()
    with UnitOfWorkV1(factory) as uow:
        inicio = criar_obrigacao_pagamento(
            contexto=_contexto(),
            repositorio=uow.pagamentos,
            pagamento_id="pay-1",
            pedido_id="pedido-1",
            valor_previsto=Dinheiro("40"),
            metodo=MetodoPagamento.PIX,
            idempotency_key="obrigacao-pay-1",
            timestamp=AGORA,
            provedor="sandbox",
        )
        uow.registrar_efeitos(eventos=inicio.eventos, auditorias=inicio.auditorias)
        assert inicio.pagamento.status is PagamentoStatus.PENDENTE
        uow.commit()

    with pytest.raises(FonteFinanceiraNaoConfiavel), UnitOfWorkV1(factory) as uow:
        confirmar_pagamento(
            contexto=_contexto(),
            repositorio=uow.pagamentos,
            pagamento_id="pay-1",
            valor=Dinheiro("40"),
            metodo=MetodoPagamento.PIX,
            idempotency_key="manual-pix-proibido",
            expected_version=1,
            timestamp=AGORA,
        )

    with UnitOfWorkV1(factory) as uow:
        pendente = uow.pagamentos.buscar_pagamento("tenant-1", "loja-1", "pay-1")
        assert pendente and pendente.status is PagamentoStatus.PENDENTE

        webhook = ProvedorPagamentoFake().normalizar_webhook(
            {
                "evento_externo": "evt-1",
                "id_externo": "pix-externo-1",
                "tipo": "confirmado",
                "valor": "40",
                "timestamp": AGORA,
                "assinatura_validada": True,
                "idempotency_key": "wh-1",
            }
        )
        pago = processar_webhook(
            contexto=_contexto(),
            repositorio=uow.pagamentos,
            pagamento_id="pay-1",
            webhook=webhook,
            expected_version=1,
        )
        assert pago and pago.pagamento.status is PagamentoStatus.PAGO
        uow.registrar_efeitos(eventos=pago.eventos, auditorias=pago.auditorias)
        uow.commit()

    with Session(engine) as session:
        pagamento = session.scalar(select(PagamentoORM).where(PagamentoORM.id == "pay-1"))
        assert pagamento and pagamento.status == PagamentoStatus.PAGO.value
        assert session.scalar(select(func.count()).select_from(TransacaoPagamentoORM)) == 2
        assert session.scalar(select(func.count()).select_from(OutboxEventoORM)) == 2
        assert session.scalar(select(func.count()).select_from(EventoAuditoriaORM)) == 2


def test_webhook_sem_assinatura_nao_altera_pagamento_sql() -> None:
    _, factory = _factory()
    with UnitOfWorkV1(factory) as uow:
        inicio = criar_obrigacao_pagamento(
            contexto=_contexto(),
            repositorio=uow.pagamentos,
            pagamento_id="pay-2",
            pedido_id="pedido-2",
            valor_previsto=Dinheiro("25"),
            metodo=MetodoPagamento.PIX,
            idempotency_key="obrigacao-pay-2",
            timestamp=AGORA,
        )
        uow.registrar_efeitos(eventos=inicio.eventos, auditorias=inicio.auditorias)
        uow.commit()

    with UnitOfWorkV1(factory) as uow:
        webhook = ProvedorPagamentoFake().normalizar_webhook(
            {
                "evento_externo": "evt-invalido",
                "id_externo": "pix-invalido",
                "tipo": "confirmado",
                "valor": "25",
                "timestamp": AGORA,
                "assinatura_validada": False,
                "idempotency_key": "wh-invalido",
            }
        )
        assert (
            processar_webhook(
                contexto=_contexto(),
                repositorio=uow.pagamentos,
                pagamento_id="pay-2",
                webhook=webhook,
                expected_version=1,
            )
            is None
        )
        uow.commit()

    with UnitOfWorkV1(factory) as uow:
        pagamento = uow.pagamentos.buscar_pagamento("tenant-1", "loja-1", "pay-2")
        assert pagamento and pagamento.status is PagamentoStatus.PENDENTE
        assert len(uow.pagamentos.listar_transacoes("tenant-1", "loja-1", "pay-2")) == 1
