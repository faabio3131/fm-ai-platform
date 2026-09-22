"""Fronteira HTTP administrativa do Commercial Registry KCA-01."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.orm import Session

from application.comercial_registry import AplicacaoCommercialRegistryV1
from core.comercial.erros import (
    ConflitoConcorrenciaComercial,
    ConflitoIdempotenciaComercial,
    DadoComercialInvalido,
    RegistroComercialDuplicado,
    RegistroComercialNaoEncontrado,
    TransicaoComercialInvalida,
)
from core.comercial.modelos import (
    ClasseContaComercial,
    ClienteComercial,
    ContaProdutoComercial,
    StatusClienteComercial,
    StatusContaProduto,
)
from http_api.admin_backoffice import contexto_backoffice
from http_api.admin_dashboard import _tratar_erro
from http_api.auth import AuthSessionRuntime

SessionFactory = Callable[[], Session]
IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=192),
]


class CustomerCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    account_class: ClasseContaComercial
    primary_contact_email: EmailStr
    primary_contact_phone: str | None = Field(default=None, max_length=64)


class CustomerUpdateIn(CustomerCreateIn):
    expected_version: int = Field(ge=1)
    status: StatusClienteComercial


class ProductAccountCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_code: str = Field(min_length=1, max_length=64)
    product_tenant_id: str | None = Field(default=None, max_length=64)


class ProductAccountTransitionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    status: StatusContaProduto
    product_tenant_id: str | None = Field(default=None, max_length=64)


def _customer_out(customer: ClienteComercial) -> dict[str, Any]:
    return {
        "fm_customer_id": customer.fm_customer_id,
        "customer_code": customer.customer_code,
        "display_name": customer.display_name,
        "legal_name": customer.legal_name,
        "status": customer.status.value,
        "account_class": customer.account_class.value,
        "primary_contact_email": customer.primary_contact_email,
        "primary_contact_phone": customer.primary_contact_phone,
        "version": customer.version,
        "created_at": customer.created_at.isoformat(),
        "updated_at": customer.updated_at.isoformat(),
    }


def _product_account_out(account: ContaProdutoComercial) -> dict[str, Any]:
    return {
        "product_account_id": account.product_account_id,
        "fm_customer_id": account.fm_customer_id,
        "product_code": account.product_code,
        "product_tenant_id": account.product_tenant_id,
        "status": account.status.value,
        "version": account.version,
        "created_at": account.created_at.isoformat(),
        "updated_at": account.updated_at.isoformat(),
        "activated_at": (
            account.activated_at.isoformat() if account.activated_at else None
        ),
        "suspended_at": (
            account.suspended_at.isoformat() if account.suspended_at else None
        ),
        "closed_at": account.closed_at.isoformat() if account.closed_at else None,
    }


def _erro_comercial(exc: Exception) -> JSONResponse:
    if isinstance(exc, RegistroComercialNaoEncontrado):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"erro": str(exc)},
        )
    if isinstance(
        exc,
        (
            ConflitoConcorrenciaComercial,
            ConflitoIdempotenciaComercial,
            RegistroComercialDuplicado,
        ),
    ):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"erro": str(exc)},
        )
    if isinstance(exc, (DadoComercialInvalido, TransicaoComercialInvalida)):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"erro": str(exc)},
        )
    return _tratar_erro(exc)


def build_admin_comercial_router(
    *,
    session_factory: SessionFactory,
    auth_runtime: AuthSessionRuntime,
) -> APIRouter:
    router = APIRouter(prefix="/v1/admin/commercial", tags=["admin-commercial"])
    app = AplicacaoCommercialRegistryV1(session_factory)

    def contexto(request: Request):
        return contexto_backoffice(
            request,
            auth_runtime=auth_runtime,
            origem="admin_commercial_http_v1",
        )

    @router.post("/customers", status_code=201, response_model=None)
    def criar_customer(
        payload: CustomerCreateIn,
        request: Request,
        idempotency_key: IdempotencyHeader,
    ) -> dict[str, Any] | JSONResponse:
        try:
            customer = app.criar_cliente(
                contexto=contexto(request),
                idempotency_key=idempotency_key,
                display_name=payload.display_name,
                legal_name=payload.legal_name,
                account_class=payload.account_class,
                primary_contact_email=str(payload.primary_contact_email),
                primary_contact_phone=payload.primary_contact_phone,
            )
            return _customer_out(customer)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_comercial(exc)

    @router.get("/customers/{fm_customer_id}", response_model=None)
    def obter_customer(
        fm_customer_id: str,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto(request)
            return _customer_out(app.obter_cliente(fm_customer_id=fm_customer_id))
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.put("/customers/{fm_customer_id}", response_model=None)
    def atualizar_customer(
        fm_customer_id: str,
        payload: CustomerUpdateIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            customer = app.atualizar_cliente(
                contexto=contexto(request),
                fm_customer_id=fm_customer_id,
                expected_version=payload.expected_version,
                display_name=payload.display_name,
                legal_name=payload.legal_name,
                status=payload.status,
                account_class=payload.account_class,
                primary_contact_email=str(payload.primary_contact_email),
                primary_contact_phone=payload.primary_contact_phone,
            )
            return _customer_out(customer)
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.post(
        "/customers/{fm_customer_id}/product-accounts",
        status_code=201,
        response_model=None,
    )
    def criar_product_account(
        fm_customer_id: str,
        payload: ProductAccountCreateIn,
        request: Request,
        idempotency_key: IdempotencyHeader,
    ) -> dict[str, Any] | JSONResponse:
        try:
            account = app.criar_conta_produto(
                contexto=contexto(request),
                idempotency_key=idempotency_key,
                fm_customer_id=fm_customer_id,
                product_code=payload.product_code,
                product_tenant_id=payload.product_tenant_id,
            )
            return _product_account_out(account)
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.get("/product-accounts/{product_account_id}", response_model=None)
    def obter_product_account(
        product_account_id: str,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto(request)
            return _product_account_out(
                app.obter_conta_produto(product_account_id=product_account_id)
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.post(
        "/product-accounts/{product_account_id}/transition",
        response_model=None,
    )
    def transicionar_product_account(
        product_account_id: str,
        payload: ProductAccountTransitionIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            account = app.transicionar_conta_produto(
                contexto=contexto(request),
                product_account_id=product_account_id,
                expected_version=payload.expected_version,
                status=payload.status,
                product_tenant_id=payload.product_tenant_id,
            )
            return _product_account_out(account)
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    return router
