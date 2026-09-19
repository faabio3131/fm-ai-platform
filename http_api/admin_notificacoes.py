"""Boundary HTTP administrativa para Notificações Internas V1."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from application.notificacoes_internas_admin import (
    AplicacaoNotificacoesInternasAdminV1,
)
from core.notificacoes_internas.modelos import DestinatarioNotificacaoInterna
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from core.seguranca.permissoes import Permissao
from http_api.auth import AuthSessionRuntime

SessionFactory = Callable[[], Session]


class DestinatarioIn(BaseModel):
    destinatario_id: str = Field(min_length=1, max_length=64)
    nome_exibicao: str = Field(min_length=1, max_length=120)
    cargo: str | None = Field(default=None, max_length=80)
    contato: str = Field(min_length=10, max_length=32)
    receber_alertas_estoque: bool = True
    ativo: bool = True


class PreferenciasIn(BaseModel):
    receber_alertas_estoque: bool
    ativo: bool


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
    if isinstance(exc, LookupError):
        return _erro(
            status.HTTP_404_NOT_FOUND,
            str(exc) or "notificacao.destinatario_indisponivel",
        )
    if isinstance(exc, ValueError):
        return _erro(
            status.HTTP_400_BAD_REQUEST,
            str(exc) or "notificacao.dados_invalidos",
        )
    return _erro(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "notificacao_interna.indisponivel",
    )


def _out(item: DestinatarioNotificacaoInterna) -> dict[str, Any]:
    return {
        "destinatario_id": item.destinatario_id,
        "tenant_id": item.tenant_id,
        "unidade_id": item.unidade_id,
        "nome_exibicao": item.nome_exibicao,
        "cargo": item.cargo,
        "canal": item.canal.value,
        "contato_mascara": item.contato_mascara,
        "receber_alertas_estoque": item.receber_alertas_estoque,
        "ativo": item.ativo,
        "versao": item.versao,
    }


def _contexto(
    request: Request,
    auth_runtime: AuthSessionRuntime,
    *,
    origem: str,
    exigir_step_up: bool,
):
    identidade = auth_runtime.resolver_identidade(request)
    if identidade is None:
        raise CredenciaisInvalidas("credenciais invalidas")
    if Permissao.ADMIN_ACESSAR not in identidade.permissoes:
        raise PermissionError("seguranca.admin_acesso_exigido")
    if Permissao.NOTIFICACAO_INTERNA_GERENCIAR not in identidade.permissoes:
        raise PermissionError("seguranca.notificacao_interna_gerenciar_exigido")
    if exigir_step_up:
        _, elevado, _ = auth_runtime.admin_status(request)
        if not elevado:
            raise PermissionError("seguranca.admin_step_up_exigido")
    return identidade.contexto(
        origem=origem,
        correlation_id=request.headers.get("x-correlation-id") or None,
    )


def build_admin_notificacoes_router(
    *,
    session_factory: SessionFactory,
    auth_runtime: AuthSessionRuntime,
    master_key: str | None = None,
) -> APIRouter:
    router = APIRouter(
        prefix="/v1/admin/notificacoes",
        tags=["admin-notificacoes"],
    )
    app = AplicacaoNotificacoesInternasAdminV1(
        session_factory,
        master_key=master_key,
    )

    @router.get("", response_model=None)
    def listar(request: Request) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _contexto(
                request,
                auth_runtime,
                origem="admin_notificacoes_http_v1.listar",
                exigir_step_up=False,
            )
            return {
                "destinatarios": [
                    _out(item) for item in app.listar(contexto=contexto)
                ]
            }
        except Exception as exc:  # noqa: BLE001 - boundary fail-closed
            return _tratar_erro(exc)

    @router.put("/{destinatario_id}", response_model=None)
    def configurar(
        destinatario_id: str,
        payload: DestinatarioIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            if payload.destinatario_id != destinatario_id:
                raise ValueError("destinatario_id_divergente")
            contexto = _contexto(
                request,
                auth_runtime,
                origem="admin_notificacoes_http_v1.configurar",
                exigir_step_up=True,
            )
            return _out(
                app.configurar(
                    contexto=contexto,
                    destinatario_id=destinatario_id,
                    nome_exibicao=payload.nome_exibicao,
                    cargo=payload.cargo,
                    contato=payload.contato,
                    receber_alertas_estoque=payload.receber_alertas_estoque,
                    ativo=payload.ativo,
                )
            )
        except Exception as exc:  # noqa: BLE001 - boundary fail-closed
            return _tratar_erro(exc)

    @router.patch("/{destinatario_id}/preferencias", response_model=None)
    def preferencias(
        destinatario_id: str,
        payload: PreferenciasIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _contexto(
                request,
                auth_runtime,
                origem="admin_notificacoes_http_v1.preferencias",
                exigir_step_up=True,
            )
            return _out(
                app.atualizar_preferencias(
                    contexto=contexto,
                    destinatario_id=destinatario_id,
                    receber_alertas_estoque=payload.receber_alertas_estoque,
                    ativo=payload.ativo,
                )
            )
        except Exception as exc:  # noqa: BLE001 - boundary fail-closed
            return _tratar_erro(exc)

    return router
