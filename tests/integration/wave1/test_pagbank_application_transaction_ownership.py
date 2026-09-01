from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from application import pagbank as pagbank_app
from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import PagamentoStatus
from core.pagamentos.modelos import (
    MetodoPagamento,
    StatusTransacao,
    TipoTransacao,
    TransacaoPagamento,
)
from core.pagamentos.modelos_orm import PagamentoORM
from core.pagamentos.pagbank import AdapterPagBank, ConfiguracaoPagBank
from core.pagamentos.servicos import criar_obrigacao_pagamento
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel
from infra.transacoes.uow import UnitOfWorkV1
from migrations.runner import run_migrations

AGORA = datetime(
    2026,
    8,
    28,
    16,
    15,
    tzinfo=timezone.utc,
)

TOKEN = "token-sd1e17"
ORDER_ID = "ORDE_SD1E17"
PAGAMENTO_ID = "pay-sd1e17"
TENANT = "tenant-sd1e17"
UNIDADE = "unidade-sd1e17"


def _infra():
    engine = create_engine(
        "sqlite://",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    run_migrations(engine)

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    return engine, factory


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id="admin-sd1e17",
        papeis=frozenset(
            {
                Papel.ADMINISTRADOR,
            }
        ),
        permissoes=MATRIZ_PADRAO[
            Papel.ADMINISTRADOR
        ],
        correlation_id="corr-sd1e17",
        solicitado_em=AGORA,
        origem="tests.sd1e17.pagbank",
        unidades_permitidas=frozenset(
            {
                UNIDADE,
            }
        ),
    )


def _seed(factory) -> None:
    contexto = _contexto()

    with UnitOfWorkV1(factory) as uow:
        inicio = criar_obrigacao_pagamento(
            contexto=contexto,
            repositorio=uow.pagamentos,
            pagamento_id=PAGAMENTO_ID,
            pedido_id="pedido-sd1e17",
            valor_previsto=Dinheiro("38.90"),
            metodo=MetodoPagamento.PIX,
            idempotency_key="obrigacao-sd1e17",
            timestamp=AGORA,
            provedor="pagbank",
        )

        uow.registrar_efeitos(
            eventos=inicio.eventos,
            auditorias=inicio.auditorias,
        )

        uow.pagamentos.append_transacao(
            TransacaoPagamento(
                str(uuid4()),
                PAGAMENTO_ID,
                TENANT,
                UNIDADE,
                TipoTransacao.INICIACAO,
                StatusTransacao.PENDENTE,
                Dinheiro(0),
                MetodoPagamento.PIX,
                "pagbank",
                ORDER_ID,
                "pagbank:sd1e17:order",
                AGORA,
                AGORA,
                contexto.correlation_id,
                None,
                (
                    (
                        "order_status",
                        "pendente",
                    ),
                ),
            ),
            "fingerprint-sd1e17",
        )

        uow.commit()


def _payload() -> bytes:
    return json.dumps(
        {
            "id": ORDER_ID,
            "charges": [
                {
                    "id": "CHAR_SD1E17",
                    "status": "PAID",
                    "paid_at": (
                        "2026-08-28"
                        "T16:16:00-03:00"
                    ),
                    "amount": {
                        "value": 3890,
                        "currency": "BRL",
                    },
                    "payment_method": {
                        "type": "PIX",
                    },
                }
            ],
        },
        separators=(",", ":"),
    ).encode()


def _assinatura(payload: bytes) -> str:
    return hashlib.sha256(
        TOKEN.encode()
        + b"-"
        + payload
    ).hexdigest()


def _adapter_factory(
    *,
    session: Session,
    tenant_id: str,
    unidade_id: str,
) -> AdapterPagBank:
    del session

    assert tenant_id == TENANT
    assert unidade_id == UNIDADE

    return AdapterPagBank(
        ConfiguracaoPagBank(
            token=TOKEN,
            ambiente="sandbox",
        )
    )


def test_application_pagbank_commita_e_replay_nao_duplica_confirmacao() -> None:
    _, factory = _infra()

    _seed(factory)

    payload = _payload()

    primeira = pagbank_app.processar_webhook_pagbank(
        session_factory=factory,
        adapter_factory=_adapter_factory,
        order_id=ORDER_ID,
        payload_bruto=payload,
        assinatura=_assinatura(payload),
    )

    replay = pagbank_app.processar_webhook_pagbank(
        session_factory=factory,
        adapter_factory=_adapter_factory,
        order_id=ORDER_ID,
        payload_bruto=payload,
        assinatura=_assinatura(payload),
    )

    assert primeira is not None
    assert replay is not None

    with UnitOfWorkV1(factory) as uow:
        pagamento = uow.pagamentos.buscar_pagamento(
            TENANT,
            UNIDADE,
            PAGAMENTO_ID,
        )

        assert pagamento is not None
        assert pagamento.status is PagamentoStatus.PAGO

        transacoes = uow.pagamentos.listar_transacoes(
            TENANT,
            UNIDADE,
            PAGAMENTO_ID,
        )

        confirmacoes = [
            transacao
            for transacao in transacoes
            if (
                transacao.tipo
                is TipoTransacao.CONFIRMACAO
            )
        ]

        assert len(confirmacoes) == 1


def test_application_pagbank_faz_rollback_de_flush_parcial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, factory = _infra()

    _seed(factory)

    def falhar_depois_do_flush(
        *,
        recursos,
        adapter,
        payload_bruto,
        assinatura,
    ):
        del adapter
        del payload_bruto
        del assinatura

        recursos.session.execute(
            update(PagamentoORM)
            .where(
                PagamentoORM.tenant_id
                == TENANT,
                PagamentoORM.unidade_id
                == UNIDADE,
                PagamentoORM.id
                == PAGAMENTO_ID,
            )
            .values(
                status=PagamentoStatus.PAGO.value
            )
        )

        recursos.session.flush()

        raise RuntimeError(
            "falha_depois_do_flush"
        )

    monkeypatch.setattr(
        pagbank_app,
        "processar_webhook_pagbank_em_transacao",
        falhar_depois_do_flush,
    )

    payload = _payload()

    with pytest.raises(
        RuntimeError,
        match="falha_depois_do_flush",
    ):
        pagbank_app.processar_webhook_pagbank(
            session_factory=factory,
            adapter_factory=_adapter_factory,
            order_id=ORDER_ID,
            payload_bruto=payload,
            assinatura=_assinatura(payload),
        )

    with UnitOfWorkV1(factory) as uow:
        pagamento = uow.pagamentos.buscar_pagamento(
            TENANT,
            UNIDADE,
            PAGAMENTO_ID,
        )

        assert pagamento is not None

        assert (
            pagamento.status
            is PagamentoStatus.PENDENTE
        )
