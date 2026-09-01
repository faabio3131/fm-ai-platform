"""Fronteira de composição do contexto mínimo do Caixa no PDV."""

from datetime import datetime

from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import CredenciaisInvalidas
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


def contexto_caixa_pdv_autenticado(
    *,
    identidade: IdentidadeUsuario,
    usuario_id: str,
    correlation_id: str,
    instante: datetime,
    origem: str,
) -> ContextoExecucao:
    """Deriva o Caixa exclusivamente do Active Execution Scope autenticado."""

    if not identidade.ativo:
        raise CredenciaisInvalidas("credenciais invalidas")
    escopo_ativo = identidade.contexto(
        origem=origem,
        correlation_id=correlation_id,
        solicitado_em=instante,
    )
    return contexto_caixa_pdv(
        tenant_id=escopo_ativo.tenant_id,
        unidade_id=escopo_ativo.unidade_id,
        usuario_id=usuario_id,
        correlation_id=escopo_ativo.correlation_id,
        instante=escopo_ativo.solicitado_em,
        origem=escopo_ativo.origem,
    )
