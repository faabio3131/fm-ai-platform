"""API interna versionada do FM Cognitive Core para o FM Control Center."""

from __future__ import annotations

import hmac
import os
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from application.ai_router_runtime import construir_ai_model_router
from application.fmcc_core_service import (
    ErroCoreCompartilhadoFMCC,
    ServicoCoreCompartilhadoFMCC,
)
from core.ai_router import ErroAIRouter
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import ReferenciaSegredoInvalida, SegredoAusente
from core.seguranca.segredos import SecretStore

_DEFAULT_SERVICE_TOKEN_REF = "env:FM_CORE_SERVICE_TOKEN"


class FmccPlanIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    tenantId: str = Field(min_length=1, max_length=128)
    userId: str = Field(min_length=1, max_length=128)
    correlationId: str = Field(min_length=1, max_length=128)
    allowedCapabilities: list[str] = Field(min_length=1, max_length=32)
    operationalContext: list[dict[str, Any]] = Field(default_factory=list, max_length=16)


class FmccSynthesizeIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    tenantId: str = Field(min_length=1, max_length=128)
    userId: str = Field(min_length=1, max_length=128)
    correlationId: str = Field(min_length=1, max_length=128)
    facts: list[dict[str, Any]] = Field(min_length=1, max_length=64)
    evidence: list[dict[str, Any]] = Field(min_length=1, max_length=64)
    operationalContext: list[dict[str, Any]] = Field(default_factory=list, max_length=16)


def _service_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "").strip()
    scheme, separator, value = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer":
        return None
    return value.strip() or None


def _autenticar_servico(
    request: Request,
    *,
    secret_store: SecretStore,
) -> JSONResponse | None:
    presented = _service_token(request)
    if presented is None:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "fmcc_core.service_auth_required"},
        )

    reference = os.getenv(
        "FM_CORE_SERVICE_TOKEN_REF",
        _DEFAULT_SERVICE_TOKEN_REF,
    ).strip()
    try:
        expected = secret_store.resolve(reference).reveal()
    except (ReferenciaSegredoInvalida, SegredoAusente):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "fmcc_core.service_auth_unavailable"},
        )

    if not hmac.compare_digest(presented, expected):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "fmcc_core.service_auth_invalid"},
        )
    return None


def _routing_scope() -> tuple[str, str]:
    tenant_id = os.getenv("FM_CORE_ROUTING_TENANT_ID", "").strip()
    unidade_id = os.getenv("FM_CORE_ROUTING_UNIT_ID", "").strip()
    if not tenant_id or not unidade_id:
        raise RuntimeError("fmcc_core.routing_scope_unavailable")
    return tenant_id, unidade_id


def build_fmcc_core_router(
    *,
    session_factory: Callable[[], Session],
    secret_store: SecretStore,
) -> APIRouter:
    router = APIRouter(prefix="/v1/fmcc", tags=["fm-cognitive-core"])

    def construir_servico(
        *,
        session: Session,
        correlation_id: str,
    ) -> ServicoCoreCompartilhadoFMCC:
        routing_tenant_id, routing_unidade_id = _routing_scope()
        contexto = ContextoExecucao.sistema(
            identidade="fmcc-core-service-v1",
            motivo=(
                "rotear cognição do FM Control Center pelo AI Model Router "
                "canônico sem transferir autoridade de negócio ao modelo"
            ),
            tenant_id=routing_tenant_id,
            unidade_id=routing_unidade_id,
            correlation_id=correlation_id,
            solicitado_em=datetime.now(timezone.utc),
        )
        ai_router = construir_ai_model_router(
            session=session,
            contexto=contexto,
            secret_store=secret_store,
        )
        return ServicoCoreCompartilhadoFMCC(ai_router)

    @router.post("/plan")
    def plan(payload: FmccPlanIn, request: Request) -> JSONResponse:
        erro_auth = _autenticar_servico(request, secret_store=secret_store)
        if erro_auth is not None:
            return erro_auth
        try:
            with session_factory() as session:
                service = construir_servico(
                    session=session,
                    correlation_id=payload.correlationId,
                )
                result = service.planejar(
                    pergunta=payload.question,
                    tenant_id=payload.tenantId,
                    usuario_id=payload.userId,
                    correlation_id=payload.correlationId,
                    capabilities_permitidas=tuple(payload.allowedCapabilities),
                    contexto_operacional=tuple(payload.operationalContext),
                )
            return JSONResponse(status_code=status.HTTP_200_OK, content=result)
        except ErroCoreCompartilhadoFMCC as exc:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": exc.codigo},
            )
        except (ErroAIRouter, RuntimeError):
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"error": "fmcc_core.cognitive_runtime_unavailable"},
            )

    @router.post("/synthesize")
    def synthesize(
        payload: FmccSynthesizeIn,
        request: Request,
    ) -> JSONResponse:
        erro_auth = _autenticar_servico(request, secret_store=secret_store)
        if erro_auth is not None:
            return erro_auth
        try:
            with session_factory() as session:
                service = construir_servico(
                    session=session,
                    correlation_id=payload.correlationId,
                )
                result = service.sintetizar(
                    pergunta=payload.question,
                    tenant_id=payload.tenantId,
                    usuario_id=payload.userId,
                    correlation_id=payload.correlationId,
                    fatos=tuple(payload.facts),
                    evidencias=tuple(payload.evidence),
                    contexto_operacional=tuple(payload.operationalContext),
                )
            return JSONResponse(status_code=status.HTTP_200_OK, content=result)
        except ErroCoreCompartilhadoFMCC as exc:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": exc.codigo},
            )
        except (ErroAIRouter, RuntimeError):
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"error": "fmcc_core.cognitive_runtime_unavailable"},
            )

    return router
