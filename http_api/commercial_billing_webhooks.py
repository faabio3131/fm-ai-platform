"""Ingress HTTP provider-neutral para billing webhooks — KCA-10."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from application.commercial_billing import BillingProviderAdapterRegistryV1
from application.commercial_billing_events import AplicacaoBillingEventsV1
from core.comercial.billing import BillingProviderError
from core.comercial.billing_events import BillingWebhookInboxStatus
from core.comercial.erros import (
    ConflitoIdempotenciaComercial,
    DadoComercialInvalido,
    RegistroComercialNaoEncontrado,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import ReferenceSecretStore, SecretStore

_MAX_BILLING_WEBHOOK_BYTES = 1024 * 1024

SessionFactory = Callable[[], Session]


def build_commercial_billing_webhook_router(
    *,
    session_factory: SessionFactory,
    adapter_registry: BillingProviderAdapterRegistryV1 | None = None,
    fallback_secret_store: SecretStore | None = None,
) -> APIRouter:
    router = APIRouter(
        prefix="/v1/commercial/billing",
        tags=["commercial-billing-webhooks"],
    )
    app = AplicacaoBillingEventsV1(
        session_factory,
        adapter_registry=adapter_registry or BillingProviderAdapterRegistryV1(),
        fallback_secret_store=fallback_secret_store or ReferenceSecretStore(),
    )

    @router.post(
        "/webhooks/{provider_account_id}",
        include_in_schema=False,
        response_model=None,
    )
    async def receive_billing_webhook(
        provider_account_id: str,
        request: Request,
    ) -> JSONResponse:
        body = await request.body()
        if not body or len(body) > _MAX_BILLING_WEBHOOK_BYTES:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={"accepted": False, "code": "billing_webhook_size_invalid"},
            )
        correlation_id = (
            request.headers.get("x-correlation-id")
            or f"billing-webhook:{provider_account_id}"
        )
        contexto = ContextoExecucao.sistema(
            identidade="fm-commercial-billing-webhook-kca10",
            motivo="KCA-10 provider billing webhook ingress",
            tenant_id="fm-commercial-platform",
            unidade_id="billing",
            correlation_id=correlation_id,
            solicitado_em=datetime.now(timezone.utc),
        )
        try:
            inbox = app.receber_webhook(
                contexto=contexto,
                provider_account_id=provider_account_id,
                payload=body,
                headers=dict(request.headers.items()),
            )
        except BillingProviderError as exc:
            return JSONResponse(
                status_code=(
                    status.HTTP_503_SERVICE_UNAVAILABLE
                    if exc.retryable
                    else status.HTTP_400_BAD_REQUEST
                ),
                content={
                    "accepted": False,
                    "code": type(exc).__name__,
                    "retryable": bool(exc.retryable),
                },
            )
        except ConflitoIdempotenciaComercial:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "accepted": False,
                    "code": "billing_webhook_replay_conflict",
                },
            )
        except RegistroComercialNaoEncontrado:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={
                    "accepted": False,
                    "code": "billing_provider_account_not_found",
                },
            )
        except (DadoComercialInvalido, PermissionError):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"accepted": False, "code": "billing_webhook_invalid"},
            )

        if inbox.status == BillingWebhookInboxStatus.REJECTED.value:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "accepted": False,
                    "status": inbox.status,
                    "event_id": inbox.external_event_id,
                },
            )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "accepted": True,
                "status": inbox.status,
                "event_id": inbox.external_event_id,
            },
        )

    return router
