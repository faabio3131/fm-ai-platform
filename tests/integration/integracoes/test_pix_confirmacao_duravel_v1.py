from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.dominio.enums import PagamentoStatus
from core.pagamentos.adaptador_sqlalchemy import RepositorioPagamentosSQLAlchemy
from core.pagamentos.modelos_orm import PaymentsBase
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from infra.integracoes.pix_durabilidade import (
    confirmar_cobranca_pix_consultada,
    registrar_vinculo_cobranca_pix,
)
from infra.integracoes.pix_runtime import CobrancaPixRuntime


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="tenant-a",
        unidade_id="loja-1",
        usuario_id="admin-1",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id="corr-pix-confirmacao",
        solicitado_em=datetime.now(timezone.utc),
        origem="tests.pix-confirmacao-duravel",
        unidades_permitidas=frozenset({"loja-1"}),
    )


def _registrar(session: Session, *, pagamento_id: str, provedor: str) -> None:
    registrar_vinculo_cobranca_pix(
        session=session,
        contexto=_contexto(),
        pagamento_id=pagamento_id,
        pedido_id=pagamento_id.removeprefix("pdv-") or pagamento_id,
        valor=Decimal("49.90"),
        provedor=provedor,
        id_externo=f"ext-{pagamento_id}",
        idempotency_key=f"{pagamento_id}:charge",
        timestamp=datetime(2026, 8, 18, 14, 40, tzinfo=timezone.utc),
    )


def test_consulta_mercado_pago_approved_liquida_pagamento_de_forma_duravel() -> None:
    engine = create_engine("sqlite:///:memory:")
    PaymentsBase.metadata.create_all(engine)

    with Session(engine) as session:
        _registrar(session, pagamento_id="pdv-checkout-1", provedor="mercado_pago")
        resultado = confirmar_cobranca_pix_consultada(
            session=session,
            contexto=_contexto(),
            pagamento_id="pdv-checkout-1",
            cobranca=CobrancaPixRuntime(
                provedor="mercado_pago",
                id_externo="ext-pdv-checkout-1",
                status="approved",
                valor=Decimal("49.90"),
                pix_copia_cola=None,
            ),
            timestamp=datetime(2026, 8, 18, 14, 41, tzinfo=timezone.utc),
        )
        assert resultado is not None
        assert resultado.pagamento.status is PagamentoStatus.PAGO
        assert resultado.pagamento.saldo.valor == Decimal("0.00")
        session.commit()

    with Session(engine) as nova_session:
        persistido = RepositorioPagamentosSQLAlchemy(nova_session).buscar_pagamento(
            "tenant-a", "loja-1", "pdv-checkout-1"
        )
        assert persistido is not None
        assert persistido.status is PagamentoStatus.PAGO
        assert persistido.valor_pago.valor == Decimal("49.90")


def test_consulta_pendente_nao_liquida_pagamento() -> None:
    engine = create_engine("sqlite:///:memory:")
    PaymentsBase.metadata.create_all(engine)

    with Session(engine) as session:
        _registrar(session, pagamento_id="pdv-checkout-2", provedor="pagbank")
        resultado = confirmar_cobranca_pix_consultada(
            session=session,
            contexto=_contexto(),
            pagamento_id="pdv-checkout-2",
            cobranca=CobrancaPixRuntime(
                provedor="pagbank",
                id_externo="ext-pdv-checkout-2",
                status="pendente",
                valor=Decimal("49.90"),
                pix_copia_cola=None,
            ),
        )
        assert resultado is None

        persistido = RepositorioPagamentosSQLAlchemy(session).buscar_pagamento(
            "tenant-a", "loja-1", "pdv-checkout-2"
        )
        assert persistido is not None
        assert persistido.status is PagamentoStatus.PENDENTE
        assert persistido.valor_pago.valor == Decimal("0.00")


def test_confirmacao_por_consulta_e_idempotente() -> None:
    engine = create_engine("sqlite:///:memory:")
    PaymentsBase.metadata.create_all(engine)

    with Session(engine) as session:
        _registrar(session, pagamento_id="pdv-checkout-3", provedor="pagbank")
        cobranca = CobrancaPixRuntime(
            provedor="pagbank",
            id_externo="ext-pdv-checkout-3",
            status="paid",
            valor=Decimal("49.90"),
            pix_copia_cola=None,
        )
        primeira = confirmar_cobranca_pix_consultada(
            session=session,
            contexto=_contexto(),
            pagamento_id="pdv-checkout-3",
            cobranca=cobranca,
        )
        repetida = confirmar_cobranca_pix_consultada(
            session=session,
            contexto=_contexto(),
            pagamento_id="pdv-checkout-3",
            cobranca=cobranca,
        )
        assert primeira is not None
        assert repetida is not None
        assert repetida.idempotente is True
        assert repetida.pagamento.valor_pago.valor == Decimal("49.90")
