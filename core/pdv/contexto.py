"""Fronteira de composição do contexto mínimo do Caixa no PDV."""

from datetime import datetime

from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel


def contexto_caixa_pdv(
    *,
    tenant_id: str,
    unidade_id: str,
    usuario_id: str,
    correlation_id: str,
    instante: datetime,
    origem: str,
) -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id,
        unidade_id,
        usuario_id,
        frozenset({Papel.CAIXA}),
        MATRIZ_PADRAO[Papel.CAIXA],
        correlation_id,
        instante,
        origem,
        unidades_permitidas=frozenset({unidade_id}),
    )
