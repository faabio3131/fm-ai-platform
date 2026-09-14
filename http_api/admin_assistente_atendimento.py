"""Adaptador HTTP fino para a administração do Assistente de Atendimento V1."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from application.assistente_atendimento_admin import (
    AplicacaoAssistenteAtendimentoAdminV1,
    ConversaDetalheAdmin,
    ConversaResumoAdmin,
)
from core.assistente_atendimento.modelos import ConfiguracaoIdentidadeAssistente
from core.gerente_ia.erros import ErroGerenteIA
from http_api.admin_backoffice import contexto_backoffice
from http_api.admin_dashboard import _tratar_erro
from http_api.auth import AuthSessionRuntime

SessionFactory = Callable[[], Session]


class IdentidadeAssistenteOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str
    unidade_id: str
    nome_publico: str
    atributos: dict[str, Any]
    versao: int
    atualizado_em: str | None = None


class IdentidadeAssistentePutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome_publico: str = Field(min_length=1, max_length=80)
    atributos: dict[str, Any] = Field(default_factory=dict)
    versao_esperada: int | None = Field(default=None, ge=0)


class ConversaResumoOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversa_id: str
    estado: str
    pedido_id: str | None = None
    pagamento_id: str | None = None
    entrega_id: str | None = None
    versao: int
    atualizado_em: str


class ConversasListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversas: list[ConversaResumoOut]


class ConversaDetalheOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversa_id: str
    estado: str
    pedido_id: str | None = None
    pagamento_id: str | None = None
    entrega_id: str | None = None
    ultimo_inbound_id: str | None = None
    ultimo_outbound_id: str | None = None
    versao: int
    handoff_contexto: dict[str, Any] | None = None


class HandoffIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    motivo: str = Field(min_length=3, max_length=240)


class HandoffOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    conversa_id: str
    motivo: str


def _identidade_out(config: ConfiguracaoIdentidadeAssistente) -> IdentidadeAssistenteOut:
    return IdentidadeAssistenteOut(
        tenant_id=config.tenant_id,
        unidade_id=config.unidade_id,
        nome_publico=config.nome_publico,
        atributos=dict(config.atributos),
        versao=config.versao,
        atualizado_em=config.atualizado_em.isoformat() if config.atualizado_em else None,
    )


def _resumo_out(conversa: ConversaResumoAdmin) -> ConversaResumoOut:
    return ConversaResumoOut(
        conversa_id=conversa.conversa_id,
        estado=conversa.estado,
        pedido_id=conversa.pedido_id,
        pagamento_id=conversa.pagamento_id,
        entrega_id=conversa.entrega_id,
        versao=conversa.versao,
        atualizado_em=conversa.atualizado_em.isoformat(),
    )


def _detalhe_out(conversa: ConversaDetalheAdmin) -> ConversaDetalheOut:
    return ConversaDetalheOut(
        conversa_id=conversa.conversa_id,
        estado=conversa.estado,
        pedido_id=conversa.pedido_id,
        pagamento_id=conversa.pagamento_id,
        entrega_id=conversa.entrega_id,
        ultimo_inbound_id=conversa.ultimo_inbound_id,
        ultimo_outbound_id=conversa.ultimo_outbound_id,
        versao=conversa.versao,
        handoff_contexto=(
            dict(conversa.handoff_contexto)
            if conversa.handoff_contexto is not None
            else None
        ),
    )


def _erro_assistente(exc: Exception) -> JSONResponse:
    if isinstance(exc, ErroGerenteIA):
        if exc.codigo == "configuracao_assistente_desatualizada":
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={"erro": exc.codigo},
            )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"erro": exc.codigo},
        )
    if isinstance(exc, RuntimeError) and "concorrente" in str(exc).casefold():
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"erro": str(exc)},
        )
    if isinstance(exc, (ValueError, TypeError, RuntimeError)):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"erro": str(exc) or "admin.assistente_requisicao_invalida"},
        )
    return _tratar_erro(exc)


def build_admin_assistente_atendimento_router(
    *,
    session_factory: SessionFactory,
    auth_runtime: AuthSessionRuntime,
) -> APIRouter:
    router = APIRouter(
        prefix="/v1/admin/assistente-atendimento",
        tags=["admin-assistente-atendimento"],
    )
    app = AplicacaoAssistenteAtendimentoAdminV1(session_factory)

    @router.get("/identidade", response_model=None)
    def obter_identidade(request: Request) -> IdentidadeAssistenteOut | JSONResponse:
        try:
            contexto = contexto_backoffice(
                request,
                auth_runtime=auth_runtime,
                origem="admin_assistente_atendimento_http_v1.identidade",
            )
            return _identidade_out(app.obter_identidade(contexto=contexto))
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_assistente(exc)

    @router.put("/identidade", response_model=None)
    def configurar_identidade(
        payload: IdentidadeAssistentePutIn,
        request: Request,
    ) -> IdentidadeAssistenteOut | JSONResponse:
        try:
            contexto = contexto_backoffice(
                request,
                auth_runtime=auth_runtime,
                origem="admin_assistente_atendimento_http_v1.configurar_identidade",
            )
            configuracao = app.configurar_identidade(
                contexto=contexto,
                nome_publico=payload.nome_publico,
                atributos=payload.atributos,
                versao_esperada=payload.versao_esperada,
            )
            return _identidade_out(configuracao)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_assistente(exc)

    @router.get("/conversas", response_model=None)
    def listar_conversas(request: Request) -> ConversasListOut | JSONResponse:
        try:
            contexto = contexto_backoffice(
                request,
                auth_runtime=auth_runtime,
                origem="admin_assistente_atendimento_http_v1.listar_conversas",
            )
            conversas = app.listar_conversas(contexto=contexto)
            return ConversasListOut(
                conversas=[_resumo_out(conversa) for conversa in conversas]
            )
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_assistente(exc)

    @router.get("/conversas/{conversa_id}", response_model=None)
    def obter_conversa(
        conversa_id: str,
        request: Request,
    ) -> ConversaDetalheOut | JSONResponse:
        try:
            contexto = contexto_backoffice(
                request,
                auth_runtime=auth_runtime,
                origem="admin_assistente_atendimento_http_v1.obter_conversa",
            )
            return _detalhe_out(
                app.obter_conversa(
                    contexto=contexto,
                    conversa_id=conversa_id,
                )
            )
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_assistente(exc)

    @router.post("/conversas/{conversa_id}/handoff", response_model=None)
    def forcar_handoff(
        conversa_id: str,
        payload: HandoffIn,
        request: Request,
    ) -> HandoffOut | JSONResponse:
        try:
            contexto = contexto_backoffice(
                request,
                auth_runtime=auth_runtime,
                origem="admin_assistente_atendimento_http_v1.forcar_handoff",
            )
            app.forcar_handoff(
                contexto=contexto,
                conversa_id=conversa_id,
                motivo=payload.motivo,
            )
            return HandoffOut(
                status="handoff_registrado",
                conversa_id=conversa_id,
                motivo=" ".join(payload.motivo.split()),
            )
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_assistente(exc)

    return router
