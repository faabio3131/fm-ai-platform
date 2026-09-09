"""Adaptador HTTP read-only para os agregados AI FinOps da V1."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from application.ai_finops_dashboard import resumir_ai_finops
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from core.seguranca.permissoes import Permissao
from http_api.auth import AuthSessionRuntime
from http_api.operational_auth import obter_identidade_operacional
from infra.ai_finops_read_model import AIFinOpsSQLAlchemyReadModel

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
        return _erro(status.HTTP_400_BAD_REQUEST, str(exc) or "ai_finops.periodo_invalido")
    if isinstance(exc, SQLAlchemyError):
        return _erro(status.HTTP_503_SERVICE_UNAVAILABLE, "ai_finops.indisponivel")
    return _erro(status.HTTP_503_SERVICE_UNAVAILABLE, "ai_finops.indisponivel")


def _resumo_out(resumo: Any) -> dict[str, Any]:
    return {
        "attempts": resumo.attempts,
        "success_attempts": resumo.success_attempts,
        "failure_attempts": resumo.failure_attempts,
        "fallback_attempts": resumo.fallback_attempts,
        "input_tokens": resumo.input_tokens,
        "output_tokens": resumo.output_tokens,
        "cached_tokens": resumo.cached_tokens,
        "latency_ms_average": str(resumo.latency_ms_average),
        "latency_ms_max": resumo.latency_ms_max,
        "cost_known_events": resumo.cost_known_events,
        "cost_unknown_events": resumo.cost_unknown_events,
        "success_rate_pct": str(resumo.success_rate_pct),
        "fallback_rate_pct": str(resumo.fallback_rate_pct),
        "cost_coverage_pct": str(resumo.cost_coverage_pct),
        "custos": [
            {"moeda": item.moeda, "valor": str(item.valor), "eventos": item.eventos}
            for item in resumo.custos
        ],
        "mix": [
            {
                "provider": item.provider,
                "model": item.model,
                "attempts": item.attempts,
            }
            for item in resumo.mix
        ],
    }


def build_ai_finops_router(
    *,
    session_factory: SessionFactory,
    auth_runtime: AuthSessionRuntime,
) -> APIRouter:
    router = APIRouter(prefix="/v1/ai-finops", tags=["ai-finops"])

    @router.get("/resumo", response_model=None)
    def obter_resumo(
        request: Request,
        inicio: Annotated[date, Query()],
        fim: Annotated[date, Query()],
    ) -> dict[str, Any] | JSONResponse:
        try:
            with session_factory() as session:
                identidade = obter_identidade_operacional(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                ).identidade
            if Permissao.ADMIN_ACESSAR not in identidade.permissoes:
                raise PermissionError("administracao_sem_acesso")
            buckets = AIFinOpsSQLAlchemyReadModel(session_factory).listar(
                tenant_id=identidade.tenant_id,
                unidade_id=identidade.unidade_id,
                inicio=inicio,
                fim=fim,
            )
            return {
                "tenant_id": identidade.tenant_id,
                "unidade_id": identidade.unidade_id,
                "inicio": inicio.isoformat(),
                "fim": fim.isoformat(),
                "resumo": _resumo_out(resumir_ai_finops(buckets)),
            }
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _tratar_erro(exc)

    return router
