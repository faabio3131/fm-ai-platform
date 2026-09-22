"""HTTP público do cadastro Kordena KCA-06.

A superfície nasce desativada por padrão. A liberação pública pertence ao KCA-17.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import uuid4

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from application.public_signup import (
    AplicacaoPublicSignupV1,
    SignupCreationResult,
    SignupVerificationError,
)
from core.comercial.erros import DadoComercialInvalido, RegistroComercialDuplicado
from core.seguranca.segredos import SecretStore

SessionFactory = Callable[[], Session]


class VerificationDispatcher(Protocol):
    def send_verification(
        self, *, signup_id: str, email: str, token: str
    ) -> None: ...


class SignupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=1024)
    phone: str | None = Field(default=None, max_length=64)
    establishment_name: str = Field(min_length=1, max_length=255)
    segment: str = Field(min_length=1, max_length=96)
    terms_accepted: bool
    consents: dict[str, bool] = Field(default_factory=dict)
    website: str = Field(default="", max_length=255)


class VerifyEmailIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=16, max_length=512)


class _SlidingWindowLimiter:
    def __init__(self, *, limit: int = 5, window_seconds: int = 600) -> None:
        self._limit = limit
        self._window = timedelta(seconds=window_seconds)
        self._events: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = datetime.now(timezone.utc)
        with self._lock:
            bucket = self._events[key]
            cutoff = now - self._window
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self._limit:
                return False
            bucket.append(now)
            return True


def build_public_signup_router(
    *,
    session_factory: SessionFactory,
    secret_store: SecretStore,
    enabled: bool = False,
    verification_dispatcher: VerificationDispatcher | None = None,
    credential_secret_reference: str = "env:FM_AI_SIGNUP_SECRET_KEY",
) -> APIRouter:
    router = APIRouter(prefix="/v1/public/signup", tags=["public-signup"])
    app = AplicacaoPublicSignupV1(
        session_factory,
        secret_store=secret_store,
        credential_secret_reference=credential_secret_reference,
    )
    limiter = _SlidingWindowLimiter()

    def _disabled() -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"erro": "recurso_indisponivel"},
        )

    def _generic_accepted(signup_id: str | None = None) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "accepted": True,
                "signup_id": signup_id or str(uuid4()),
                "message": "Se os dados forem elegíveis, enviaremos a verificação.",
            },
        )

    def _dispatch(result: SignupCreationResult) -> None:
        if verification_dispatcher is None:
            raise RuntimeError("signup_verification_dispatcher_unavailable")
        verification_dispatcher.send_verification(
            signup_id=result.signup.signup_id,
            email=result.signup.owner_email,
            token=result.verification_token,
        )

    @router.post("")
    def create_signup(payload: SignupIn, request: Request) -> JSONResponse:
        if not enabled:
            return _disabled()
        remote = request.client.host if request.client else "unknown"
        if not limiter.allow(f"ip:{remote}"):
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"erro": "signup_rate_limited"},
            )
        if payload.website.strip():
            return _generic_accepted()
        try:
            result = app.criar_intencao(
                owner_name=payload.owner_name,
                owner_email=payload.email,
                owner_password=payload.password,
                primary_contact_phone=payload.phone,
                establishment_name=payload.establishment_name,
                segment=payload.segment,
                terms_accepted=payload.terms_accepted,
                consent_json=payload.consents,
                correlation_id=request.headers.get("x-correlation-id")
                or f"signup:{uuid4()}",
            )
            _dispatch(result)
            return _generic_accepted(result.signup.signup_id)
        except RegistroComercialDuplicado:
            return _generic_accepted()
        except DadoComercialInvalido as exc:
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={"erro": str(exc)},
            )
        except RuntimeError:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"erro": "signup_temporariamente_indisponivel"},
            )

    @router.post("/{signup_id}/resend-verification")
    def resend_verification(signup_id: str) -> JSONResponse:
        if not enabled:
            return _disabled()
        try:
            result = app.reenviar_token(signup_id=signup_id)
            _dispatch(result)
            return _generic_accepted(result.signup.signup_id)
        except SignupVerificationError:
            return _generic_accepted()
        except RuntimeError:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"erro": "signup_temporariamente_indisponivel"},
            )

    @router.post("/{signup_id}/verify-email")
    def verify_email(signup_id: str, payload: VerifyEmailIn) -> JSONResponse:
        if not enabled:
            return _disabled()
        try:
            result = app.verificar_e_provisionar(
                signup_id=signup_id,
                verification_token=payload.token,
            )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "signup_id": result.signup_id,
                    "status": result.status.value,
                    "ready": result.status.value == "ready",
                },
            )
        except SignupVerificationError as exc:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"erro": str(exc)},
            )
        except (ValueError, RuntimeError, SQLAlchemyError):
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"erro": "signup_provisioning_pending"},
            )

    @router.get("/{signup_id}/status")
    def signup_status(signup_id: str) -> JSONResponse:
        if not enabled:
            return _disabled()
        result = app.obter_status(signup_id=signup_id)
        if result is None:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"erro": "signup_not_found"},
            )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "signup_id": result.signup_id,
                "status": result.status.value,
                "ready": result.status.value == "ready",
            },
        )

    return router
