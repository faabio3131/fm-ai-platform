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
from sqlalchemy import select
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
from core.entrega.modelos_orm import EventoEntregaORM
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from http_api.auth import AuthSessionRuntime
from http_api.operational_auth import obter_identidade_operacional
from infra.marketplaces.modelos_orm import PedidoExternoMarketplaceORM

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


def _responsavel_atual(modalidade: str) -> str:
    return {
        "propria": "loja",
        "parceiro": "marketplace",
        "indefinida": "desconhecido",
    }.get(modalidade, "desconhecido")


def _contexto_logistico(session: Session, entrega: Any) -> dict[str, Any]:
    marketplace = session.scalar(
        select(PedidoExternoMarketplaceORM)
        .where(
            PedidoExternoMarketplaceORM.tenant_id == entrega.tenant_id,
            PedidoExternoMarketplaceORM.unidade_id == entrega.unidade_id,
            PedidoExternoMarketplaceORM.pedido_id == entrega.pedido_id,
        )
        .order_by(PedidoExternoMarketplaceORM.ultima_ocorrencia_em.desc())
        .limit(1)
    )
    evento_criacao = session.scalar(
        select(EventoEntregaORM)
        .where(
            EventoEntregaORM.tenant_id == entrega.tenant_id,
            EventoEntregaORM.unidade_id == entrega.unidade_id,
            EventoEntregaORM.entrega_id == entrega.entrega_id,
            EventoEntregaORM.tipo == "entrega.criada",
        )
        .order_by(EventoEntregaORM.ocorrido_em.asc())
        .limit(1)
    )
    payload = dict(evento_criacao.payload_seguro or {}) if evento_criacao else {}
    evento_responsavel = session.scalar(
        select(EventoEntregaORM)
        .where(
            EventoEntregaORM.tenant_id == entrega.tenant_id,
            EventoEntregaORM.unidade_id == entrega.unidade_id,
            EventoEntregaORM.entrega_id == entrega.entrega_id,
            EventoEntregaORM.tipo == "entrega.responsavel_logistico_atualizado",
        )
        .order_by(EventoEntregaORM.ocorrido_em.desc(), EventoEntregaORM.event_id.desc())
        .limit(1)
    )
    payload_responsavel = (
        dict(evento_responsavel.payload_seguro or {})
        if evento_responsavel is not None
        else {}
    )
    canal = str(
        payload_responsavel.get("canal_origem")
        or payload.get("canal_origem")
        or ""
    ).strip()
    if not canal and marketplace is not None:
        canal = str(marketplace.integracao_id).rsplit("--", 1)[-1]
    if not canal:
        canal = "delivery_proprio" if entrega.modalidade.value == "propria" else "interno"

    responsavel = _responsavel_atual(entrega.modalidade.value)
    original = str(payload.get("responsavel_original") or responsavel)
    externo = marketplace is not None
    motivo_bloqueio: str | None = None
    if externo and canal == "ifood":
        if responsavel == "marketplace":
            motivo_bloqueio = (
                "Troca iFood para entrega própria depende de capacidade oficial "
                "homologada pelo parceiro; o Kordena não presume essa transição."
            )
        elif responsavel == "loja":
            motivo_bloqueio = (
                "A Shipping API do iFood oferece contratação de entregador, mas "
                "essa composição ainda precisa de homologação específica no Kordena."
            )
    elif externo:
        motivo_bloqueio = (
            "Mudanças logísticas externas só são liberadas quando o adapter do "
            "marketplace declarar a capacidade homologada."
        )

    return {
        "canal_origem": canal,
        "pedido_externo_id": (
            marketplace.id_externo if marketplace is not None else None
        ),
        "status_externo": (
            marketplace.status_externo if marketplace is not None else None
        ),
        "responsavel_original": original,
        "responsavel_atual": responsavel,
        "autoridade_logistica": str(
            payload.get("autoridade_logistica") or ("kordena" if not externo else canal)
        ),
        "delivery_mode_externo": (
            payload_responsavel.get("delivery_mode")
            or payload.get("delivery_mode")
        ),
        "delivered_by_externo": (
            payload_responsavel.get("delivered_by")
            or payload.get("delivered_by")
        ),
        "troca_logistica_permitida": False,
        "alternativas_logisticas": [],
        "motivo_bloqueio_troca": motivo_bloqueio,
    }


def _entrega_out(
    entrega: Any,
    *,
    logistica: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = {
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
    base.update(
        logistica
        or {
            "canal_origem": "interno",
            "pedido_externo_id": None,
            "status_externo": None,
            "responsavel_original": _responsavel_atual(entrega.modalidade.value),
            "responsavel_atual": _responsavel_atual(entrega.modalidade.value),
            "autoridade_logistica": "kordena",
            "delivery_mode_externo": None,
            "delivered_by_externo": None,
            "troca_logistica_permitida": False,
            "alternativas_logisticas": [],
            "motivo_bloqueio_troca": None,
        }
    )
    return base


def _detalhe_out(
    entrega: Any,
    eventos: tuple[Any, ...],
    *,
    logistica: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "entrega": _entrega_out(entrega, logistica=logistica),
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
                return {
                    "itens": [
                        _entrega_out(
                            entrega,
                            logistica=_contexto_logistico(session, entrega),
                        )
                        for entrega in entregas
                    ]
                }
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
                return _detalhe_out(
                    entrega,
                    eventos,
                    logistica=_contexto_logistico(session, entrega),
                )
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
