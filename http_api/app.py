"""HTTP ingress mínimo e fail-closed para webhooks financeiros da V1."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from application.pagbank import (
    PagBankAplicacaoInvalida,
    processar_webhook_pagbank_em_transacao,
)
from core.pagamentos.erros import ConflitoIdempotenciaPagamento
from core.pagamentos.modelos import TipoTransacao
from core.pagamentos.pagbank import ErroPagBank
from core.runtime import build_engine, check_database_health, load_runtime_settings
from core.runtime.config import RuntimeSettings
from core.seguranca.erros import ReferenciaSegredoInvalida, SegredoAusente
from infra.pagamentos.pagbank_runtime import (
    CredencialPagBankNaoConfigurada,
    PagBankAdapterFactory,
)
from infra.seguranca.session_guard import build_session_factory
from infra.transacoes.uow import UnitOfWorkV1

_MAX_WEBHOOK_BYTES = 1024 * 1024


def _extrair_order_id_nao_confiavel(payload_bruto: bytes) -> str | None:
    """Extrai somente a chave de roteamento; não atribui confiança ao payload."""

    try:
        payload = json.loads(payload_bruto.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    order_id = str(payload.get("id", "")).strip()
    return order_id if order_id.startswith("ORDE_") else None


def build_http_app(
    *,
    settings: RuntimeSettings | None = None,
    engine: Engine | None = None,
    session_factory: Callable[[], Session] | None = None,
    pagbank_factory: PagBankAdapterFactory | None = None,
) -> FastAPI:
    settings = settings or load_runtime_settings()
    engine = engine or build_engine(settings)
    session_factory = session_factory or build_session_factory(
        engine=engine, commercial=settings.commercial
    )
    pagbank_factory = pagbank_factory or PagBankAdapterFactory()

    app = FastAPI(
        title="F&M Gerente AI — Integration API",
        version="1.0",
        docs_url=None if settings.commercial else "/docs",
        redoc_url=None,
        openapi_url=None if settings.commercial else "/openapi.json",
    )

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> JSONResponse:
        health = check_database_health(engine)
        return JSONResponse(
            status_code=status.HTTP_200_OK if health.ok else status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"ok": health.ok, "backend": health.backend, "detail": health.detail},
        )

    @app.post("/webhooks/pagbank", include_in_schema=False)
    async def webhook_pagbank(request: Request) -> Response:
        payload_bruto = await request.body()
        if len(payload_bruto) > _MAX_WEBHOOK_BYTES:
            return Response(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

        assinatura = request.headers.get("x-authenticity-token", "").strip()
        if not assinatura:
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        order_id = _extrair_order_id_nao_confiavel(payload_bruto)
        if order_id is None:
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        with UnitOfWorkV1(session_factory) as uow:
            try:
                vinculo = uow.pagamentos.buscar_transacao_externa(
                    "pagbank", order_id, TipoTransacao.INICIACAO
                )
            except ConflitoIdempotenciaPagamento:
                return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

            if vinculo is None:
                return Response(status_code=status.HTTP_204_NO_CONTENT)

            try:
                adapter = pagbank_factory.construir(
                    session=uow.recursos.session,
                    tenant_id=vinculo.tenant_id,
                    unidade_id=vinculo.unidade_id,
                )
            except (
                CredencialPagBankNaoConfigurada,
                ReferenciaSegredoInvalida,
                SegredoAusente,
            ):
                return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

            try:
                resultado = processar_webhook_pagbank_em_transacao(
                    recursos=uow.recursos,
                    adapter=adapter,
                    payload_bruto=payload_bruto,
                    assinatura=assinatura,
                )
            except ErroPagBank:
                return Response(status_code=status.HTTP_204_NO_CONTENT)
            except PagBankAplicacaoInvalida:
                return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

            if resultado is None:
                return Response(status_code=status.HTTP_204_NO_CONTENT)

            uow.commit()
            return Response(status_code=status.HTTP_204_NO_CONTENT)

    return app
