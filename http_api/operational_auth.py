"""Resolução unificada de identidade operacional para HTTP V1.

O navegador usa a sessão assinada ``fm_ai_session`` como autoridade de
identidade e escopo. Clientes legados/machine-to-machine permanecem
compatíveis com Basic Auth + X-Tenant-ID/X-Unit-ID quando não existe sessão.

Regra fail-closed: se uma sessão estiver presente e for inválida, não ocorre
downgrade silencioso para Basic Auth.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Literal

from fastapi import Request
from sqlalchemy.orm import Session

from core.seguranca.autenticacao import IdentidadeUsuario, ServicoAutenticacao
from core.seguranca.erros import CredenciaisInvalidas
from http_api.auth import AuthSessionRuntime
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy

AuthMode = Literal["session", "basic"]


@dataclass(frozen=True)
class IdentidadeOperacional:
    identidade: IdentidadeUsuario
    modo: AuthMode


def _credenciais_basic(request: Request) -> tuple[str, str] | None:
    cabecalho = request.headers.get("authorization", "").strip()
    esquema, _, valor = cabecalho.partition(" ")
    if esquema.casefold() != "basic" or not valor:
        return None
    try:
        decodificado = base64.b64decode(valor, validate=True).decode("utf-8")
        email, password = decodificado.split(":", 1)
    except (ValueError, UnicodeDecodeError):
        return None
    if not email.strip() or not password:
        return None
    return email, password


def obter_identidade_operacional(
    request: Request,
    session: Session,
    *,
    auth_runtime: AuthSessionRuntime | None,
) -> IdentidadeOperacional:
    """Resolve sessão web primeiro e Basic legado somente quando ela inexiste."""

    if auth_runtime is not None:
        identidade_sessao = auth_runtime.resolver_identidade(request)
        if identidade_sessao is not None:
            return IdentidadeOperacional(
                identidade=identidade_sessao,
                modo="session",
            )

    credenciais = _credenciais_basic(request)
    tenant_id = request.headers.get("x-tenant-id", "").strip()
    unidade_id = request.headers.get("x-unit-id", "").strip()
    if credenciais is None or not tenant_id or not unidade_id:
        raise CredenciaisInvalidas("credenciais invalidas")

    email, password = credenciais
    identidade = ServicoAutenticacao(
        RepositorioIdentidadesSQLAlchemy(session)
    ).autenticar(email=email, password=password)
    return IdentidadeOperacional(
        identidade=identidade.no_escopo_ativo(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
        ),
        modo="basic",
    )
