"""Application boundary para persistência durável de cobranças Pix.

A infraestrutura executa a mutação dentro de uma Session recebida, mas não
decide commit/rollback. Esta camada possui a fronteira transacional através do
UnitOfWorkV1.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from core.pagamentos.modelos import ResultadoPagamento, TransacaoPagamento
from core.seguranca.contexto import ContextoExecucao
from infra.integracoes.pix_durabilidade import (
    confirmar_cobranca_pix_consultada as _confirmar_cobranca_pix_consultada,
)
from infra.integracoes.pix_durabilidade import (
    registrar_vinculo_cobranca_pix as _registrar_vinculo_cobranca_pix,
)
from infra.integracoes.pix_runtime import CobrancaPixRuntime
from infra.transacoes.uow import UnitOfWorkV1


def _session_ativa(uow: UnitOfWorkV1) -> Session:
    if uow.session is None:
        raise RuntimeError("UnitOfWorkV1 sem Session ativa")
    return uow.session


def registrar_vinculo_cobranca_pix(
    *,
    session_factory: Callable[[], Session],
    contexto: ContextoExecucao,
    pagamento_id: str,
    pedido_id: str,
    valor: Decimal,
    provedor: str,
    id_externo: str,
    idempotency_key: str,
    timestamp: datetime | None = None,
    terminal_id: str | None = None,
    assinatura_checkout: str | None = None,
) -> TransacaoPagamento:
    """Registra o vínculo Pix e finaliza exatamente uma transação na application."""

    with UnitOfWorkV1(session_factory) as uow:
        salva = _registrar_vinculo_cobranca_pix(
            session=_session_ativa(uow),
            contexto=contexto,
            pagamento_id=pagamento_id,
            pedido_id=pedido_id,
            valor=valor,
            provedor=provedor,
            id_externo=id_externo,
            idempotency_key=idempotency_key,
            timestamp=timestamp,
            terminal_id=terminal_id,
            assinatura_checkout=assinatura_checkout,
        )
        uow.commit()
        return salva


def confirmar_cobranca_pix_consultada(
    *,
    session_factory: Callable[[], Session],
    contexto: ContextoExecucao,
    pagamento_id: str,
    cobranca: CobrancaPixRuntime,
    timestamp: datetime | None = None,
) -> ResultadoPagamento | None:
    """Confirma consulta Pix sob ownership transacional da application."""

    with UnitOfWorkV1(session_factory) as uow:
        resultado = _confirmar_cobranca_pix_consultada(
            session=_session_ativa(uow),
            contexto=contexto,
            pagamento_id=pagamento_id,
            cobranca=cobranca,
            timestamp=timestamp,
        )
        uow.commit()
        return resultado
