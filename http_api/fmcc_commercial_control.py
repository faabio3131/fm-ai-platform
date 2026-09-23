"""Governed FM Control Center boundary for Kordena commercial authority — KCA-12."""

from __future__ import annotations

import secrets
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from fastapi import APIRouter, Header, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from application.commercial_catalog import AplicacaoCatalogoComercialV1
from application.fmcc_commercial_projection import (
    SCHEMA_VERSION,
    AplicacaoFMCCCommercialProjectionV1,
)
from core.comercial.erros import (
    ConflitoConcorrenciaComercial,
    ConflitoIdempotenciaComercial,
    DadoComercialInvalido,
    RegistroComercialDuplicado,
    RegistroComercialNaoEncontrado,
    TransicaoComercialInvalida,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from http_api.admin_comercial import (
    CatalogValidateIn,
    PlanVersionCreateIn,
    PlanVersionPublishIn,
    PriceCreateIn,
    PricePublishIn,
    PromotionPublishIn,
    PromotionVersionBaseIn,
)

CONTROL_PLANE_UNIT = "fm-control-center"
CONTROL_PLANE_TENANT = "nova-fm-control-plane"
STEP_UP_TTL = timedelta(minutes=15)
MIN_SERVICE_TOKEN_LENGTH = 32

CatalogAction = Literal[
    "plan_version.create",
    "plan_version.validate",
    "plan_version.publish",
    "price.create",
    "price.validate",
    "price.publish",
    "promotion.create",
    "promotion_version.create",
    "promotion_version.validate",
    "promotion_version.publish",
]


class FMCCActorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    role: Literal["owner", "admin"]
    step_up_at: datetime


class FMCCCatalogCommandIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: FMCCActorIn
    action: CatalogAction
    resource_id: str | None = Field(default=None, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)


def _serialize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _serialize(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _error(status_code: int, code: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": code})


def _commercial_error(exc: Exception) -> JSONResponse:
    if isinstance(exc, RegistroComercialNaoEncontrado):
        return _error(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(
        exc,
        (
            ConflitoConcorrenciaComercial,
            ConflitoIdempotenciaComercial,
            RegistroComercialDuplicado,
        ),
    ):
        return _error(status.HTTP_409_CONFLICT, str(exc))
    if isinstance(
        exc,
        (
            DadoComercialInvalido,
            TransicaoComercialInvalida,
            ValidationError,
        ),
    ):
        return _error(status.HTTP_400_BAD_REQUEST, str(exc))
    if isinstance(exc, PermissionError):
        return _error(status.HTTP_403_FORBIDDEN, str(exc))
    return _error(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "fmcc_control_plane.internal_error",
    )


def _authorize(authorization: str | None, configured_token: str | None) -> JSONResponse | None:
    token = (configured_token or "").strip()
    if len(token) < MIN_SERVICE_TOKEN_LENGTH:
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "fmcc_control_plane_not_configured",
        )
    prefix = "Bearer "
    supplied = authorization or ""
    if not supplied.startswith(prefix):
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            "fmcc_control_plane.unauthorized",
        )
    if not secrets.compare_digest(supplied[len(prefix) :], token):
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            "fmcc_control_plane.unauthorized",
        )
    return None


def _fresh_step_up(actor: FMCCActorIn, *, now: datetime) -> bool:
    value = actor.step_up_at
    if value.tzinfo is None or value.utcoffset() is None:
        return False
    value = value.astimezone(timezone.utc)
    if value > now + timedelta(minutes=1):
        return False
    return now - value <= STEP_UP_TTL


def _context(
    *,
    actor: FMCCActorIn,
    correlation_id: str,
    requested_at: datetime,
) -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=CONTROL_PLANE_TENANT,
        unidade_id=CONTROL_PLANE_UNIT,
        usuario_id=actor.user_id,
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset({Permissao.ADMIN_ACESSAR}),
        correlation_id=correlation_id,
        solicitado_em=requested_at,
        origem="fmcc_commercial_control_plane_v1",
        unidades_permitidas=frozenset({CONTROL_PLANE_UNIT}),
        identity_user_id=actor.user_id,
        product_code="KORDENA",
        metadata=(
            ("fmcc_role", actor.role),
            ("fmcc_step_up_at", actor.step_up_at.isoformat()),
        ),
    )


def _resource(command: FMCCCatalogCommandIn) -> str:
    value = (command.resource_id or "").strip()
    if not value:
        raise DadoComercialInvalido("fmcc_control_plane.resource_id_required")
    return value


def build_fmcc_commercial_control_router(
    *,
    session_factory,
    control_plane_token: str | None,
) -> APIRouter:
    """Expose a narrow server-to-server FMCC integration boundary."""

    router = APIRouter(
        prefix="/v1/control-plane/fmcc",
        tags=["fmcc-commercial-control-plane"],
    )
    projection = AplicacaoFMCCCommercialProjectionV1(session_factory)
    catalog = AplicacaoCatalogoComercialV1(session_factory)

    def auth(authorization: str | None) -> JSONResponse | None:
        return _authorize(authorization, control_plane_token)

    @router.get("/health", response_model=None)
    def health(
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> dict[str, Any] | JSONResponse:
        denied = auth(authorization)
        if denied is not None:
            return denied
        return {
            "status": "ok",
            "schema_version": SCHEMA_VERSION,
            "product_code": "KORDENA",
            "authority": "fm_commercial_platform",
        }

    @router.get("/snapshot", response_model=None)
    def snapshot(
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> dict[str, Any] | JSONResponse:
        denied = auth(authorization)
        if denied is not None:
            return denied
        return projection.snapshot()

    @router.post("/catalog/commands", response_model=None)
    def catalog_command(
        body: FMCCCatalogCommandIn,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        idempotency_key: str = Header(
            min_length=1,
            max_length=192,
            alias="Idempotency-Key",
        ),
        correlation_id: str | None = Header(
            default=None,
            max_length=128,
            alias="X-Correlation-ID",
        ),
    ) -> dict[str, Any] | JSONResponse:
        denied = auth(authorization)
        if denied is not None:
            return denied

        now = datetime.now(timezone.utc)
        if not _fresh_step_up(body.actor, now=now):
            return _error(
                status.HTTP_403_FORBIDDEN,
                "fmcc_control_plane.step_up_required",
            )

        corr = (correlation_id or "").strip()
        if not corr:
            corr = request.headers.get("x-request-id", "").strip()
        if not corr:
            corr = f"fmcc-{int(now.timestamp() * 1000000)}"

        contexto = _context(
            actor=body.actor,
            correlation_id=corr,
            requested_at=now,
        )

        try:
            payload = dict(body.payload)
            action = body.action
            result: Any

            if action == "plan_version.create":
                data = PlanVersionCreateIn.model_validate(payload)
                result = catalog.criar_versao_plano(
                    contexto=contexto,
                    idempotency_key=idempotency_key,
                    plan_code=_resource(body),
                    display_name=data.display_name,
                    description=data.description,
                    trial_eligible=data.trial_eligible,
                    marketing_badge=data.marketing_badge,
                    metadata=data.metadata,
                    entitlements=tuple(data.entitlements),
                    change_reason=data.change_reason,
                )
            elif action == "plan_version.validate":
                data = CatalogValidateIn.model_validate(payload)
                result = catalog.validar_versao_plano(
                    contexto=contexto,
                    plan_version_id=_resource(body),
                    change_reason=data.change_reason,
                )
            elif action == "plan_version.publish":
                data = PlanVersionPublishIn.model_validate(payload)
                result = catalog.publicar_versao_plano(
                    contexto=contexto,
                    idempotency_key=idempotency_key,
                    plan_version_id=_resource(body),
                    expected_plan_version=data.expected_plan_version,
                    effective_from=data.effective_from,
                    change_reason=data.change_reason,
                )
            elif action == "price.create":
                data = PriceCreateIn.model_validate(payload)
                result = catalog.criar_preco(
                    contexto=contexto,
                    idempotency_key=idempotency_key,
                    plan_version_id=_resource(body),
                    currency=data.currency,
                    billing_period=data.billing_period,
                    amount=data.amount,
                    change_policy=data.change_policy,
                    change_reason=data.change_reason,
                )
            elif action == "price.validate":
                data = CatalogValidateIn.model_validate(payload)
                result = catalog.validar_preco(
                    contexto=contexto,
                    price_id=_resource(body),
                    change_reason=data.change_reason,
                )
            elif action == "price.publish":
                data = PricePublishIn.model_validate(payload)
                result = catalog.publicar_preco(
                    contexto=contexto,
                    idempotency_key=idempotency_key,
                    price_id=_resource(body),
                    expected_plan_version=data.expected_plan_version,
                    effective_from=data.effective_from,
                    change_reason=data.change_reason,
                )
            elif action == "promotion.create":
                data = PromotionVersionBaseIn.model_validate(payload)
                result = catalog.criar_promocao(
                    contexto=contexto,
                    idempotency_key=idempotency_key,
                    name=data.name,
                    discount_type=data.discount_type,
                    discount_value=data.discount_value,
                    currency=data.currency,
                    starts_at=data.starts_at,
                    ends_at=data.ends_at,
                    eligible_plan_codes=tuple(data.eligible_plan_codes),
                    max_redemptions=data.max_redemptions,
                    per_customer_limit=data.per_customer_limit,
                    rules=data.rules,
                    change_reason=data.change_reason,
                )
            elif action == "promotion_version.create":
                data = PromotionVersionBaseIn.model_validate(payload)
                result = catalog.criar_versao_promocao(
                    contexto=contexto,
                    idempotency_key=idempotency_key,
                    promotion_id=_resource(body),
                    name=data.name,
                    discount_type=data.discount_type,
                    discount_value=data.discount_value,
                    currency=data.currency,
                    starts_at=data.starts_at,
                    ends_at=data.ends_at,
                    eligible_plan_codes=tuple(data.eligible_plan_codes),
                    max_redemptions=data.max_redemptions,
                    per_customer_limit=data.per_customer_limit,
                    rules=data.rules,
                    change_reason=data.change_reason,
                )
            elif action == "promotion_version.validate":
                data = CatalogValidateIn.model_validate(payload)
                result = catalog.validar_versao_promocao(
                    contexto=contexto,
                    promotion_version_id=_resource(body),
                    change_reason=data.change_reason,
                )
            else:
                data = PromotionPublishIn.model_validate(payload)
                result = catalog.publicar_versao_promocao(
                    contexto=contexto,
                    idempotency_key=idempotency_key,
                    promotion_version_id=_resource(body),
                    expected_promotion_version=(
                        data.expected_promotion_version
                    ),
                    change_reason=data.change_reason,
                )

            return {
                "status": "accepted",
                "action": action,
                "correlation_id": corr,
                "result": _serialize(result),
            }
        except Exception as exc:  # noqa: BLE001 - fail-closed HTTP boundary
            return _commercial_error(exc)

    return router
