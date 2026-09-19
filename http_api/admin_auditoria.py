"""Boundary HTTP read-only para a auditoria administrativa da V1."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from application.auditoria_web import AplicacaoAuditoriaWebV1
from core.seguranca.auditoria import EventoAuditoria
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from core.seguranca.permissoes import Permissao
from http_api.auth import AuthSessionRuntime

SessionFactory = Callable[[], Session]


def _erro(http_status: int, codigo: str) -> JSONResponse:
    return JSONResponse(status_code=http_status, content={"erro": codigo})


def _tratar_erro(exc: Exception) -> JSONResponse:
    if isinstance(exc, CredenciaisInvalidas):
        return _erro(status.HTTP_401_UNAUTHORIZED, "credenciais_invalidas")
    if isinstance(exc, (ErroSeguranca, PermissionError)):
        return _erro(
            status.HTTP_403_FORBIDDEN,
            str(getattr(exc, "codigo", str(exc) or "seguranca.permissao_insuficiente")),
        )
    if isinstance(exc, ValueError):
        return _erro(status.HTTP_400_BAD_REQUEST, str(exc) or "auditoria.parametro_invalido")
    return _erro(status.HTTP_503_SERVICE_UNAVAILABLE, "auditoria.indisponivel")


def _evento_out(evento: EventoAuditoria) -> dict[str, Any]:
    return {
        "audit_id": evento.audit_id,
        "tenant_id": evento.tenant_id,
        "unidade_id": evento.unidade_id,
        "usuario_id": evento.usuario_id,
        "papel_efetivo": evento.papel_efetivo.value if evento.papel_efetivo else None,
        "acao": evento.acao,
        "recurso_tipo": evento.recurso_tipo,
        "recurso_id": evento.recurso_id,
        "resultado": evento.resultado,
        "motivo": evento.motivo,
        "correlation_id": evento.correlation_id,
        "timestamp": evento.timestamp.isoformat(),
        "origem": evento.origem,
        "politica": evento.politica,
        "versao": evento.versao,
        "causation_id": evento.causation_id,
    }


def _contexto(
    request: Request,
    auth_runtime: AuthSessionRuntime,
):
    identidade = auth_runtime.resolver_identidade(request)
    if identidade is None:
        raise CredenciaisInvalidas("credenciais invalidas")
    if Permissao.ADMIN_ACESSAR not in identidade.permissoes:
        raise PermissionError("seguranca.admin_acesso_exigido")
    if Permissao.AUDITORIA_VISUALIZAR not in identidade.permissoes:
        raise PermissionError("seguranca.auditoria_visualizar_exigido")
    _, elevado, _ = auth_runtime.admin_status(request)
    if not elevado:
        raise PermissionError("seguranca.admin_step_up_exigido")
    return identidade.contexto(
        origem="admin_auditoria_http_v1.listar",
        correlation_id=request.headers.get("x-correlation-id") or None,
    )


def build_admin_auditoria_router(
    *,
    session_factory: SessionFactory,
    auth_runtime: AuthSessionRuntime,
) -> APIRouter:
    router = APIRouter(prefix="/v1/admin/auditoria", tags=["admin-auditoria"])
    app = AplicacaoAuditoriaWebV1(session_factory)

    @router.get("", response_model=None)
    def listar(
        request: Request,
        pagina: Annotated[int, Query(ge=1, le=1000)] = 1,
        tamanho: Annotated[int, Query(ge=1, le=100)] = 50,
        acao: str | None = None,
        resultado: str | None = None,
        usuario_id: str | None = None,
        recurso_tipo: str | None = None,
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _contexto(request, auth_runtime)
            eventos, tem_mais = app.listar(
                contexto=contexto,
                pagina=pagina,
                tamanho=tamanho,
                acao=acao,
                resultado=resultado,
                usuario_id=usuario_id,
                recurso_tipo=recurso_tipo,
            )
            return {
                "eventos": [_evento_out(evento) for evento in eventos],
                "pagina": pagina,
                "tamanho": tamanho,
                "tem_mais": tem_mais,
            }
        except Exception as exc:  # noqa: BLE001 - boundary fail-closed
            return _tratar_erro(exc)

    return router
