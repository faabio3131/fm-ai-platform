"""Composição comercial da governança de entregadores da Entrega V1."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from core.entrega.erros import ErroEntrega
from core.seguranca import ContextoExecucao, IdentidadeUsuario, Papel
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy


@dataclass(frozen=True)
class EntregadorElegivel:
    usuario_id: str
    email: str


def _elegivel(
    identidade: IdentidadeUsuario,
    *,
    contexto: ContextoExecucao,
) -> bool:
    return bool(
        identidade.ativo
        and identidade.tenant_id == contexto.tenant_id
        and Papel.ENTREGADOR in identidade.papeis
        and contexto.unidade_id in identidade.unidades_permitidas
    )


def listar_entregadores_elegiveis(
    session: Session,
    *,
    contexto: ContextoExecucao,
) -> tuple[EntregadorElegivel, ...]:
    """Lista somente entregadores ativos do tenant e da unidade corrente."""

    repositorio = RepositorioIdentidadesSQLAlchemy(session)
    identidades = repositorio.listar_por_tenant(tenant_id=contexto.tenant_id)
    elegiveis = (
        EntregadorElegivel(
            usuario_id=identidade.usuario_id,
            email=identidade.email,
        )
        for identidade in identidades
        if _elegivel(identidade, contexto=contexto)
    )
    return tuple(sorted(elegiveis, key=lambda item: (item.email, item.usuario_id)))


def validar_entregador_elegivel(
    session: Session,
    *,
    contexto: ContextoExecucao,
    entregador_id: str,
) -> IdentidadeUsuario:
    """Revalida elegibilidade dentro da UoW que realizará a atribuição."""

    usuario_id = entregador_id.strip()
    if not usuario_id:
        raise ErroEntrega("entregador_nao_elegivel")

    identidade = RepositorioIdentidadesSQLAlchemy(session).obter_por_id(
        usuario_id=usuario_id
    )
    if identidade is None or not _elegivel(identidade, contexto=contexto):
        # Resposta deliberadamente genérica: não revela existência, tenant,
        # papel, status ou escopo de uma identidade que não seja elegível.
        raise ErroEntrega("entregador_nao_elegivel")
    return identidade
