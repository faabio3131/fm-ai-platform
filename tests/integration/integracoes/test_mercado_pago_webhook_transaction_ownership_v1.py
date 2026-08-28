from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from application.pix_durabilidade import (
    registrar_vinculo_cobranca_pix,
)
from core.dominio.enums import PagamentoStatus
from core.integracoes.provedores import (
    CobrancaMercadoPago,
    EventoWebhookProvedor,
)
from core.pagamentos.adaptador_sqlalchemy import (
    RepositorioPagamentosSQLAlchemy,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from infra.integracoes import (
    mercado_pago_webhook_app as modulo,
)
from migrations.runner import run_migrations

AGORA = datetime(
    2026,
    8,
    28,
    15,
    45,
    tzinfo=timezone.utc,
)


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="tenant-a",
        unidade_id="unidade-a",
        usuario_id="sistema-mp",
        papeis=frozenset(
            {
                Papel.ADMINISTRADOR,
            }
        ),
        permissoes=frozenset(
            Permissao
        ),
        correlation_id=(
            "corr-sd1e16-mercado-pago"
        ),
        solicitado_em=AGORA,
        origem=(
            "tests.sd1e16."
            "mercado_pago_webhook"
        ),
        unidades_permitidas=frozenset(
            {
                "unidade-a",
            }
        ),
    )


class _AdapterPago:
    def normalizar_webhook(
        self,
        **kwargs,
    ) -> EventoWebhookProvedor:
        return EventoWebhookProvedor(
            provedor="mercado_pago",
            evento_id="evt-sd1e16",
            recurso_id="ORD-SD1E16",
            tipo="order.updated",
            assinatura_validada=True,
            idempotency_key=(
                "mercado_pago:"
                "evt-sd1e16:"
                "ORD-SD1E16:"
                "order.updated"
            ),
        )

    def consultar_pagamento(
        self,
        pagamento_id: str,
    ) -> CobrancaMercadoPago:
        assert pagamento_id == "ORD-SD1E16"

        return CobrancaMercadoPago(
            pagamento_id="ORD-SD1E16",
            status="paid",
            valor=Decimal("49.90"),
            referencia_externa=(
                "pagamento-sd1e16"
            ),
            pix_copia_cola=None,
            qr_code_base64=None,
            ticket_url=None,
        )


def test_webhook_mercado_pago_commita_via_application_e_preserva_replay(
    monkeypatch,
) -> None:
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

    registrar_vinculo_cobranca_pix(
        session_factory=factory,
        contexto=_contexto(),
        pagamento_id="pagamento-sd1e16",
        pedido_id="pedido-sd1e16",
        valor=Decimal("49.90"),
        provedor="mercado_pago",
        id_externo="ORD-SD1E16",
        idempotency_key=(
            "sd1e16:mercado-pago:charge"
        ),
        timestamp=AGORA,
    )

    adapter = _AdapterPago()

    monkeypatch.setattr(
        modulo,
        "_adapter_pre_homologacao",
        lambda *args, **kwargs: adapter,
    )

    app = modulo.create_app(
        session_factory=factory,
        tenant_id="tenant-a",
        unidade_id="unidade-a",
    )

    client = TestClient(app)

    def enviar():
        return client.post(
            (
                "/webhooks/mercado-pago"
                "?data.id=ORD-SD1E16"
                "&type=order"
            ),
            headers={
                "x-request-id":
                    "req-sd1e16",
                "x-signature":
                    "ts=1,v1=assinatura-testada",
            },
            json={
                "id": "evt-sd1e16",
                "action": "order.updated",
                "type": "order",
                "data": {
                    "id": "ORD-SD1E16",
                },
            },
        )

    primeira = enviar()
    segunda = enviar()

    assert primeira.status_code == 200
    assert segunda.status_code == 200

    assert primeira.json() == {
        "accepted": True,
        "resource": "order",
        "reconciled": True,
    }

    assert segunda.json() == {
        "accepted": True,
        "resource": "order",
        "reconciled": True,
    }

    with Session(engine) as session:
        repo = RepositorioPagamentosSQLAlchemy(
            session
        )

        pagamento = repo.buscar_pagamento(
            "tenant-a",
            "unidade-a",
            "pagamento-sd1e16",
        )

        assert pagamento is not None

        assert (
            pagamento.status
            is PagamentoStatus.PAGO
        )

        assert (
            pagamento.valor_pago.valor
            == Decimal("49.90")
        )

        transacoes = repo.listar_transacoes(
            "tenant-a",
            "unidade-a",
            "pagamento-sd1e16",
        )

        confirmacoes = [
            transacao
            for transacao in transacoes
            if (
                transacao.tipo.value
                == "confirmacao"
            )
        ]

        assert len(confirmacoes) == 1
