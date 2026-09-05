"""Composition root comercial da integração KDS -> impressão."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from application.impressao_kds import IntegracaoImpressaoKDSV1
from core.impressao.flags import impressao_v1_enabled
from core.seguranca.contexto import ContextoExecucao
from infra.impressao import ImpressoraTCPRaw, ResolverDestinosImpressaoSQLAlchemy

SessionFactory = Callable[[], Session]


def montar_integracao_impressao_kds(
    *,
    session_factory: SessionFactory,
    contexto: ContextoExecucao,
) -> IntegracaoImpressaoKDSV1 | None:
    """Monta o efeito comercial de impressão somente quando o módulo está pronto."""

    if not impressao_v1_enabled():
        return None

    with session_factory() as session:
        destinos = ResolverDestinosImpressaoSQLAlchemy(session).listar(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
        )

    return IntegracaoImpressaoKDSV1(
        session_factory,
        impressora=ImpressoraTCPRaw(),
        destinos=destinos,
    )
