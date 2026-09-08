"""Adaptador HTTP fino para Expedição e Entrega V1.

O escopo vem exclusivamente da identidade operacional. Leituras respeitam a
alçada do ``ServicoEntrega`` e writes delegam à ``AplicacaoEntregaV1``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from application.entrega_composicao import listar_entregadores_elegiveis
from application.entrega_transacoes import AplicacaoEntregaV1
from core.entrega import (
    ChecklistExpedicao,
    ErroEntrega,
    ProvaEntrega,
    RepositorioEntregaSQLAlchemy,
    ServicoEntrega,
    financeiro_resolvido_sqlalchemy,
    pedido_cancelado_sqlalchemy,
)
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from http_api.auth import AuthSessionRuntime
from http_api.operational_auth import obter_identidade_operacional

SessionFactory = Callable[[], Session]
_MAX_IDEMPOTENCY_KEY = 96


class EntregaChecklistIn(BaseModel):
    versao_esperada: int = Field(ge=1)
    itens_conferidos: bool
    embalagem_conferida: bool
    identificacao_conferida: bool
    observacao_operacional: str | None = Field(default=None, max_length=500)


class EntregaAtribuirIn(BaseModel):
    versao_esperada: int = Field(ge=1)
    entregador_id: str = Field(min_length=1, max_length=120)


class EntregaVersaoIn(BaseModel):
    versao_esperada: int = Field(ge=1)


class EntregaConfirmarIn(BaseModel):
    versao_esperada: int = Field(ge=1)
    prova_referencia: str = Field(min_length=1, max_length=255)
    prova_tipo: str = Field(default="confirmacao", min_length=1, max_length=40)


class EntregaTentativaFalhaIn(BaseModel):
    versao_esperada: int = Field(ge=1)
    motivo: str = Field(min_length=1, max_length=200)


def _identidade_contexto(
    request: Request,
    session: Session,
    *,
    auth_runtime: AuthSessionRuntime | None,
) -> tuple[IdentidadeUsuario, ContextoExecucao]:
    identidade = obter_identidade_operacional(
        request,
        session,
        auth_runtime=auth_runtime,
    ).identidade
    contexto = identidade.contexto(
        origem="entrega_http_v1",
        correlation_id=request.headers.get("x-correlation-id") or None,
    )
    return identidade, contexto


def _idempotency_key(request: Request) -> str:
    key = request.headers.get("idempotency-key", "").strip()
    if not key:
        raise ValueError("idempotency_key_obrigatoria")
    if len(key) > _MAX_IDEMPOTENCY_KEY:
        raise ValueError("idempotency_key_excede_limite")
    return key


def _servico(session: Session) -> ServicoEntrega:
    return ServicoEntrega(
        RepositorioEntregaSQLAlchemy(session),
        financeiro_resolvido=lambda tenant, unidade, pedido: financeiro_resolvido_sqlalchemy(
            session, tenant, unidade, pedido
        ),
        pedido_cancelado=lambda tenant, unidade, pedido: pedido_cancelado_sqlalchemy(
            session, tenant, unidade, pedido
        ),
    )


def _erro_http(exc: Exception) -> JSONResponse:
    if isinstance(exc, CredenciaisInvalidas):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"erro": "credenciais_invalidas"},
        )
    if isinstance(exc, (ErroSeguranca, PermissionError)):
        codigo = getattr(exc, "codigo", str(exc) or "permissao_negada")
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"erro": str(codigo)},
        )
    if isinstance(exc, ErroEntrega):
        codigo = str(exc.codigo)
        if codigo in {"entrega_nao_encontrada", "entregador_nao_elegivel"}:
            http_status = status.HTTP_404_NOT_FOUND
        elif codigo in {
            "compare_and_swap_falhou",
            "conflito_idempotencia",
            "transicao_entrega_invalida",
            "producao_ainda_nao_pronta",
            "custodia_sem_conferencia",
        }:
            http_status = status.HTTP_409_CONFLICT
        elif any(
            termo in codigo
            for termo in (
                "permissao",
                "papel_sem_alcada",
                "fora_alcada",
                "exige_expedicao",
            )
        ):
            http_status = status.HTTP_403_FORBIDDEN
        else:
            http_status = status.HTTP_400_BAD_REQUEST
        return JSONResponse(status_code=http_status, content={"erro": codigo})
    if isinstance(exc, ValueError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"erro": str(exc) or "requisicao_invalida"},
        )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"erro": "entrega_indisponivel"},
    )


def _entrega_out(entrega: Any) -> dict[str, Any]:
    return {
        "entrega_id": entrega.entrega_id,
        "pedido_id": entrega.pedido_id,
        "endereco_id": entrega.endereco_id,
        "modalidade": entrega.modalidade.value,
        "status": entrega.status.value,
        "versao": entrega.versao,
        "tentativa": entrega.tentativa,
        "entregador_id": entrega.entregador_id,
        "producao_pronta_em": entrega.producao_pronta_em,
        "checklist_concluido_em": entrega.checklist_concluido_em,
        "atribuida_em": entrega.atribuida_em,
        "coletada_em": entrega.coletada_em,
        "saiu_em": entrega.saiu_em,
        "entregue_em": entrega.entregue_em,
        "prova_entrega_ref": entrega.prova_entrega_ref,
    }


def _detalhe_out(entrega: Any, eventos: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "entrega": _entrega_out(entrega),
        "eventos": [
            {
                "event_id": evento.event_id,
                "tipo": evento.tipo,
                "ocorrido_em": evento.ocorrido_em,
                "versao_entrega": evento.versao_entrega,
                "correlation_id": evento.correlation_id,
                "payload": dict(evento.payload_seguro or {}),
            }
            for evento in eventos
        ],
    }


def _encontrar_na_alcada(
    session: Session,
    contexto: ContextoExecucao,
    entrega_id: str,
) -> Any:
    entrega = next(
        (
            item
            for item in _servico(session).listar(contexto)
            if item.entrega_id == entrega_id
        ),
        None,
    )
    if entrega is None:
        raise ErroEntrega("entrega_nao_encontrada")
    return entrega


def build_entrega_router(
    *,
    session_factory: SessionFactory,
    auth_runtime: AuthSessionRuntime | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1/entregas", tags=["entregas"])

    @router.get("", response_model=dict[str, Any])
    def listar_entregas(request: Request) -> dict[str, Any] | JSONResponse:
        try:
            with session_factory() as session:
                _, contexto = _identidade_contexto(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
                entregas = _servico(session).listar(contexto)
                return {"itens": [_entrega_out(entrega) for entrega in entregas]}
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.get("/entregadores-elegiveis", response_model=dict[str, Any])
    def listar_entregadores(request: Request) -> dict[str, Any] | JSONResponse:
        try:
            with session_factory() as session:
                _, contexto = _identidade_contexto(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
                _servico(session).listar(contexto)
                entregadores = listar_entregadores_elegiveis(
                    session,
                    contexto=contexto,
                )
                return {
                    "itens": [
                        {"usuario_id": item.usuario_id, "email": item.email}
                        for item in entregadores
                    ]
                }
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.get("/{entrega_id}", response_model=dict[str, Any])
    def detalhar_entrega(
        entrega_id: str,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            with session_factory() as session:
                _, contexto = _identidade_contexto(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
                entrega = _encontrar_na_alcada(session, contexto, entrega_id)
                eventos = RepositorioEntregaSQLAlchemy(session).listar_eventos(
                    contexto.tenant_id,
                    contexto.unidade_id,
                    entrega.entrega_id,
                )
                return _detalhe_out(entrega, eventos)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.post("/{entrega_id}/checklist", response_model=dict[str, Any])
    def concluir_checklist(
        entrega_id: str,
        payload: EntregaChecklistIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            key = _idempotency_key(request)
            with session_factory() as session:
                _, contexto = _identidade_contexto(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            entrega = AplicacaoEntregaV1(session_factory).concluir_checklist(
                entrega_id,
                ChecklistExpedicao(
                    payload.itens_conferidos,
                    payload.embalagem_conferida,
                    payload.identificacao_conferida,
                    payload.observacao_operacional,
                ),
                versao_esperada=payload.versao_esperada,
                contexto=contexto,
                idempotency_key=key,
            )
            return _entrega_out(entrega)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.post("/{entrega_id}/atribuir", response_model=dict[str, Any])
    def atribuir_entregador(
        entrega_id: str,
        payload: EntregaAtribuirIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            key = _idempotency_key(request)
            with session_factory() as session:
                _, contexto = _identidade_contexto(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            entrega = AplicacaoEntregaV1(session_factory).atribuir_entregador_governado(
                entrega_id,
                payload.entregador_id,
                versao_esperada=payload.versao_esperada,
                contexto=contexto,
                idempotency_key=key,
            )
            return _entrega_out(entrega)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.post("/{entrega_id}/coletar", response_model=dict[str, Any])
    def coletar(
        entrega_id: str,
        payload: EntregaVersaoIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            key = _idempotency_key(request)
            with session_factory() as session:
                _, contexto = _identidade_contexto(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            entrega = AplicacaoEntregaV1(session_factory).coletar(
                entrega_id,
                versao_esperada=payload.versao_esperada,
                contexto=contexto,
                idempotency_key=key,
            )
            return _entrega_out(entrega)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.post("/{entrega_id}/sair-em-rota", response_model=dict[str, Any])
    def sair_em_rota(
        entrega_id: str,
        payload: EntregaVersaoIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            key = _idempotency_key(request)
            with session_factory() as session:
                _, contexto = _identidade_contexto(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            entrega = AplicacaoEntregaV1(session_factory).sair_em_rota(
                entrega_id,
                versao_esperada=payload.versao_esperada,
                contexto=contexto,
                idempotency_key=key,
            )
            return _entrega_out(entrega)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.post("/{entrega_id}/confirmar", response_model=dict[str, Any])
    def confirmar_entrega(
        entrega_id: str,
        payload: EntregaConfirmarIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            key = _idempotency_key(request)
            with session_factory() as session:
                _, contexto = _identidade_contexto(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            entrega = AplicacaoEntregaV1(session_factory).confirmar_entrega(
                entrega_id,
                ProvaEntrega(
                    payload.prova_referencia,
                    payload.prova_tipo,
                    datetime.now(timezone.utc),
                ),
                versao_esperada=payload.versao_esperada,
                contexto=contexto,
                idempotency_key=key,
            )
            return _entrega_out(entrega)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.post("/{entrega_id}/tentativa-falha", response_model=dict[str, Any])
    def registrar_tentativa_falha(
        entrega_id: str,
        payload: EntregaTentativaFalhaIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            key = _idempotency_key(request)
            with session_factory() as session:
                _, contexto = _identidade_contexto(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            entrega = AplicacaoEntregaV1(session_factory).registrar_tentativa_falha(
                entrega_id,
                payload.motivo,
                versao_esperada=payload.versao_esperada,
                contexto=contexto,
                idempotency_key=key,
            )
            return _entrega_out(entrega)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    return router
