"""HTTP fino session-aware para observabilidade/reconciliação de pagamentos V1."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from application.pagamentos_web import AplicacaoPagamentosWebV1, PagamentoWeb
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from core.seguranca.permissoes import Permissao
from core.seguranca.segredos import SecretStore
from http_api.auth import AuthSessionRuntime
from infra.pagamentos.pagbank_runtime import CredencialPagBankNaoConfigurada


def _jsonavel(pagamento: PagamentoWeb) -> dict[str, Any]:
    payload = asdict(pagamento)
    payload["atualizado_em"] = pagamento.atualizado_em.isoformat()
    payload["transacoes"] = [
        {
            **item,
            "occurred_at": item["occurred_at"].isoformat()
            if isinstance(item["occurred_at"], datetime)
            else item["occurred_at"],
        }
        for item in payload["transacoes"]
    ]
    return payload


def _erro(status_code: int, codigo: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"erro": codigo})


def _tratar_erro(exc: Exception) -> JSONResponse:
    if isinstance(exc, CredenciaisInvalidas):
        return _erro(401, "credenciais_invalidas")
    if isinstance(exc, (ErroSeguranca, PermissionError)):
        return _erro(403, str(getattr(exc, "codigo", str(exc) or "seguranca.permissao_insuficiente")))
    if isinstance(exc, LookupError):
        return _erro(404, str(exc))
    if isinstance(exc, CredencialPagBankNaoConfigurada):
        return _erro(503, "pagbank_nao_configurado")
    if isinstance(exc, (ValueError, TypeError)):
        return _erro(400, str(exc) or "pagamentos.requisicao_invalida")
    return _erro(503, "pagamentos.indisponivel")


def _contexto(request: Request, *, auth_runtime: AuthSessionRuntime) -> ContextoExecucao:
    identidade = auth_runtime.resolver_identidade(request)
    if identidade is None:
        raise CredenciaisInvalidas("credenciais invalidas")
    if Permissao.FINANCEIRO_VISUALIZAR not in identidade.permissoes:
        raise PermissionError("seguranca.financeiro_visualizar_exigido")
    return identidade.contexto(
        origem="pagamentos_web_v1",
        correlation_id=request.headers.get("x-correlation-id") or None,
    )


def build_pagamentos_web_router(
    *,
    session_factory: Callable[[], Session],
    auth_runtime: AuthSessionRuntime,
    secret_store: SecretStore | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1/pagamentos", tags=["pagamentos-web"])
    app = AplicacaoPagamentosWebV1(session_factory, secret_store=secret_store)

    @router.get("/{pagamento_id}", response_model=None)
    def obter(pagamento_id: str, request: Request) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _contexto(request, auth_runtime=auth_runtime)
            return _jsonavel(app.obter(contexto=contexto, pagamento_id=pagamento_id))
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _tratar_erro(exc)

    @router.post("/{pagamento_id}/reconciliar-pagbank", response_model=None)
    def reconciliar_pagbank(
        pagamento_id: str,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _contexto(request, auth_runtime=auth_runtime)
            return _jsonavel(
                app.reconciliar_pagbank(contexto=contexto, pagamento_id=pagamento_id)
            )
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _tratar_erro(exc)

    return router
