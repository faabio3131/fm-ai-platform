"""Entrada HTTP do Backoffice; identidade e auditoria canônicas preservadas."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from application.administracao_proprietario import AplicacaoAdministracaoProprietarioV1
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import CredenciaisInvalidas
from core.seguranca.permissoes import Permissao
from http_api.admin_dashboard import _tratar_erro
from http_api.auth import AuthSessionRuntime


def contexto_backoffice(
    request: Request, *, auth_runtime: AuthSessionRuntime, origem: str
) -> ContextoExecucao:
    identidade = auth_runtime.resolver_identidade(request)
    if identidade is None:
        raise CredenciaisInvalidas("credenciais invalidas")
    if Permissao.ADMIN_ACESSAR not in identidade.permissoes:
        raise PermissionError("seguranca.admin_acesso_exigido")
    _, elevado, _ = auth_runtime.admin_status(request)
    if not elevado:
        raise PermissionError("seguranca.admin_step_up_exigido")
    return identidade.contexto(
        origem=origem,
        correlation_id=request.headers.get("x-correlation-id") or None,
    )


def build_admin_backoffice_router(
    *, session_factory: Callable[[], Session], auth_runtime: AuthSessionRuntime
) -> APIRouter:
    router = APIRouter(prefix="/v1/admin", tags=["admin-backoffice"])

    @router.post("/acesso", response_model=None)
    def registrar_acesso(request: Request) -> dict[str, bool] | JSONResponse:
        try:
            contexto = contexto_backoffice(
                request, auth_runtime=auth_runtime, origem="admin_backoffice_http_v1"
            )
            AplicacaoAdministracaoProprietarioV1(session_factory).registrar_acesso(
                contexto=contexto
            )
            return {"ok": True}
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _tratar_erro(exc)

    return router
