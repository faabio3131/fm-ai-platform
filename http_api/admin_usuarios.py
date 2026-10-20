"""DTOs HTTP da administração de usuários original, sem autoridade paralela."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy.orm import Session

from application.administracao_proprietario import AplicacaoAdministracaoProprietarioV1
from core.seguranca.erros import ErroSeguranca
from core.seguranca.permissoes import Papel
from http_api.admin_backoffice import contexto_backoffice
from http_api.admin_dashboard import _tratar_erro
from http_api.auth import AuthSessionRuntime


class UsuarioResumoOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    usuario_id: str
    email: str
    ativo: bool
    papeis: list[str]
    unidades: list[str]
    unidade_padrao: str
    acesso_admin_sensivel: bool
    permissoes_efetivas: list[str]


class UsuarioCriarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str
    unidade_padrao_id: str
    papeis: list[str]
    unidades_permitidas: list[str]
    acesso_admin_sensivel: bool = False
    admin_pin: str | None = None


class UsuarioAtualizarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    papeis: list[str]
    unidades_permitidas: list[str]
    unidade_padrao_id: str
    ativo: bool
    acesso_admin_sensivel: bool
    nova_senha: str | None = None


def _usuario_out(usuario: Any) -> dict[str, Any]:
    return {
        "usuario_id": usuario.usuario_id,
        "email": usuario.email,
        "ativo": usuario.ativo,
        "papeis": list(usuario.papeis),
        "unidades": list(usuario.unidades),
        "unidade_padrao": usuario.unidade_padrao,
        "acesso_admin_sensivel": usuario.acesso_admin_sensivel,
        "permissoes_efetivas": list(usuario.permissoes_efetivas),
    }


def _erro_usuario(exc: Exception) -> JSONResponse:
    if isinstance(exc, ErroSeguranca):
        return _tratar_erro(exc)
    if isinstance(exc, PermissionError):
        return _tratar_erro(exc)
    if isinstance(exc, LookupError):
        return JSONResponse(status_code=404, content={"erro": str(exc) or "admin.usuario_nao_encontrado"})
    if isinstance(exc, (ValueError, TypeError)):
        return JSONResponse(status_code=400, content={"erro": "admin.usuario_invalido"})
    return _tratar_erro(exc)


def _papel_from_str(papel_str: str) -> Papel:
    try:
        return Papel(papel_str)
    except ValueError:
        raise ValueError(f"papel_invalido: {papel_str}")


def build_admin_usuarios_router(
    *, session_factory: Callable[[], Session], auth_runtime: AuthSessionRuntime
) -> APIRouter:
    router = APIRouter(prefix="/v1/admin", tags=["admin-usuarios"])
    app = AplicacaoAdministracaoProprietarioV1(session_factory)

    @router.get("/usuarios", response_model=None)
    def listar_usuarios(request: Request) -> list[dict[str, Any]] | JSONResponse:
        try:
            contexto = contexto_backoffice(
                request,
                auth_runtime=auth_runtime,
                origem="admin_usuarios_http_v1.listar",
            )
            usuarios = app.listar_usuarios(contexto=contexto)
            return [_usuario_out(u) for u in usuarios]
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_usuario(exc)

    @router.post("/usuarios", status_code=201, response_model=None)
    def criar_usuario(
        payload: UsuarioCriarIn, request: Request
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = contexto_backoffice(
                request,
                auth_runtime=auth_runtime,
                origem="admin_usuarios_http_v1.criar",
            )
            papeis = frozenset(_papel_from_str(p) for p in payload.papeis)
            identidade = app.criar_usuario(
                contexto=contexto,
                email=payload.email,
                password=payload.password,
                unidade_padrao_id=payload.unidade_padrao_id,
                papeis=papeis,
                unidades_permitidas=payload.unidades_permitidas,
                acesso_admin_sensivel=payload.acesso_admin_sensivel,
                admin_pin=payload.admin_pin,
            )
            return _usuario_out(identidade)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_usuario(exc)

    @router.put("/usuarios/{usuario_id}", response_model=None)
    def atualizar_usuario(
        usuario_id: str, payload: UsuarioAtualizarIn, request: Request
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = contexto_backoffice(
                request,
                auth_runtime=auth_runtime,
                origem="admin_usuarios_http_v1.atualizar",
            )
            papeis = frozenset(_papel_from_str(p) for p in payload.papeis)
            identidade = app.atualizar_usuario(
                contexto=contexto,
                usuario_id=usuario_id,
                papeis=papeis,
                unidades_permitidas=payload.unidades_permitidas,
                unidade_padrao_id=payload.unidade_padrao_id,
                ativo=payload.ativo,
                acesso_admin_sensivel=payload.acesso_admin_sensivel,
                nova_senha=payload.nova_senha,
            )
            return _usuario_out(identidade)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_usuario(exc)

    return router