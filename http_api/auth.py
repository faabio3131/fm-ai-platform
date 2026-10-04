"""Adaptador HTTP canônico de autenticação e sessão operacional V1."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import threading
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from application.password_recovery import (
    AplicacaoPasswordRecoveryV1,
    PasswordRecoveryDispatcher,
    PasswordRecoveryError,
)
from core.runtime.config import RuntimeSettings
from core.seguranca.autenticacao import (
    IdentidadeUsuario,
    ServicoAutenticacao,
    verify_password,
)
from core.seguranca.erros import (
    CredenciaisInvalidas,
    ErroSeguranca,
    ReferenciaSegredoInvalida,
    SegredoAusente,
)
from core.seguranca.permissoes import Permissao
from core.seguranca.segredos import SecretStore
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from infra.seguranca.google_oidc import (
    GoogleIdentityError,
    GoogleIdentityUnavailable,
    verify_google_id_token,
)
from infra.seguranca.modelos_orm import OperationalSessionORM

SessionFactory = Callable[[], Session]

logger = logging.getLogger(__name__)

_SESSION_COOKIE = "fm_ai_session"
_SESSION_SECRET_REFERENCE = "env:FM_AI_SESSION_SECRET"
_SESSION_TTL_SECONDS = 8 * 60 * 60
_ADMIN_STEP_UP_TTL_SECONDS = 15 * 60
_MIN_SESSION_SECRET_BYTES = 32


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    senha: str = Field(min_length=1, max_length=1024)


class GoogleCredentialIn(BaseModel):
    credential: str = Field(min_length=20, max_length=8192)


class ForgotPasswordIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=16, max_length=1024)
    nova_senha: str = Field(min_length=10, max_length=1024)


class ChangePasswordIn(BaseModel):
    senha_atual: str = Field(min_length=1, max_length=1024)
    nova_senha: str = Field(min_length=10, max_length=1024)


class SelecionarUnidadeIn(BaseModel):
    unidade_id: str = Field(min_length=1, max_length=64)


class SelecionarMembershipIn(BaseModel):
    membership_id: str = Field(min_length=1, max_length=64)


class AdminStepUpIn(BaseModel):
    senha: str = Field(min_length=1, max_length=1024)


@dataclass(frozen=True)
class _SessaoOperacional:
    session_id: str
    usuario_id: str
    identity_user_id: str
    membership_id: str
    email: str
    tenant_id: str
    unidade_ativa_id: str
    expira_em: datetime
    admin_elevado_ate: datetime | None = None


class _SessaoInvalida(ValueError):
    pass


class _SegredoSessaoInseguro(RuntimeError):
    pass


class _PasswordRecoveryLimiter:
    def __init__(self, *, limit: int = 5, window_seconds: int = 600) -> None:
        self._limit = limit
        self._window = timedelta(seconds=window_seconds)
        self._events: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = datetime.now(timezone.utc)
        cutoff = now - self._window
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self._limit:
                return False
            bucket.append(now)
            return True


class _GerenciadorSessaoOperacional:
    def __init__(
        self,
        secret: str,
        session_factory: SessionFactory | None = None,
    ) -> None:
        segredo = secret.encode("utf-8")
        if len(segredo) < _MIN_SESSION_SECRET_BYTES:
            raise _SegredoSessaoInseguro("segredo de sessao inseguro")
        self._secret = segredo
        self._session_factory = session_factory
        self._sessions: dict[str, _SessaoOperacional] = {}
        self._lock = threading.Lock()

    def _assinatura(self, session_id: str) -> str:
        digest = hmac.new(
            self._secret,
            f"auth-session-v1:{session_id}".encode(),
            hashlib.sha256,
        ).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def _token(self, session_id: str) -> str:
        return f"{session_id}.{self._assinatura(session_id)}"

    def _session_id_do_token(self, token: str) -> str:
        session_id, separador, assinatura = token.partition(".")
        if not separador or not session_id or not assinatura:
            raise _SessaoInvalida("sessao invalida")
        esperada = self._assinatura(session_id)
        if not hmac.compare_digest(assinatura, esperada):
            raise _SessaoInvalida("sessao invalida")
        return session_id

    @staticmethod
    def _normalizar_data(valor: datetime | None) -> datetime | None:
        if valor is None:
            return None
        if valor.tzinfo is None:
            return valor.replace(tzinfo=timezone.utc)
        return valor.astimezone(timezone.utc)

    @classmethod
    def _sessao_do_row(cls, row: OperationalSessionORM) -> _SessaoOperacional:
        expira_em = cls._normalizar_data(row.expira_em)
        if expira_em is None:
            raise _SessaoInvalida("sessao invalida")
        return _SessaoOperacional(
            session_id=row.session_id,
            usuario_id=row.usuario_id,
            identity_user_id=row.identity_user_id,
            membership_id=row.membership_id,
            email=row.email,
            tenant_id=row.tenant_id,
            unidade_ativa_id=row.unidade_ativa_id,
            expira_em=expira_em,
            admin_elevado_ate=cls._normalizar_data(row.admin_elevado_ate),
        )

    @staticmethod
    def _row_da_sessao(sessao: _SessaoOperacional) -> OperationalSessionORM:
        return OperationalSessionORM(
            session_id=sessao.session_id,
            usuario_id=sessao.usuario_id,
            identity_user_id=sessao.identity_user_id,
            membership_id=sessao.membership_id,
            email=sessao.email,
            tenant_id=sessao.tenant_id,
            unidade_ativa_id=sessao.unidade_ativa_id,
            expira_em=sessao.expira_em,
            admin_elevado_ate=sessao.admin_elevado_ate,
        )

    def _limpar_expiradas_locked(self, agora: datetime) -> None:
        expiradas = [
            session_id
            for session_id, sessao in self._sessions.items()
            if sessao.expira_em <= agora
        ]
        for session_id in expiradas:
            self._sessions.pop(session_id, None)

    @staticmethod
    def _limpar_expiradas_db(session: Session, agora: datetime) -> None:
        session.execute(
            delete(OperationalSessionORM).where(
                OperationalSessionORM.expira_em <= agora
            )
        )

    def criar(self, identidade: IdentidadeUsuario) -> tuple[_SessaoOperacional, str]:
        agora = datetime.now(timezone.utc)
        sessao = _SessaoOperacional(
            session_id=secrets.token_urlsafe(32),
            usuario_id=identidade.usuario_id,
            identity_user_id=identidade.global_identity_id,
            membership_id=identidade.membership_subject_id,
            email=identidade.email,
            tenant_id=identidade.tenant_id,
            unidade_ativa_id=identidade.unidade_id,
            expira_em=agora + timedelta(seconds=_SESSION_TTL_SECONDS),
        )
        if self._session_factory is None:
            with self._lock:
                self._limpar_expiradas_locked(agora)
                self._sessions[sessao.session_id] = sessao
        else:
            with self._session_factory() as db, db.begin():
                self._limpar_expiradas_db(db, agora)
                db.add(self._row_da_sessao(sessao))
        return sessao, self._token(sessao.session_id)

    def resolver(self, token: str) -> _SessaoOperacional:
        session_id = self._session_id_do_token(token)
        agora = datetime.now(timezone.utc)
        if self._session_factory is None:
            with self._lock:
                self._limpar_expiradas_locked(agora)
                sessao = self._sessions.get(session_id)
            if sessao is None:
                raise _SessaoInvalida("sessao invalida")
            return sessao

        encontrada: _SessaoOperacional | None = None
        with self._session_factory() as db, db.begin():
            self._limpar_expiradas_db(db, agora)
            row = db.get(OperationalSessionORM, session_id)
            if row is not None:
                encontrada = self._sessao_do_row(row)
        if encontrada is None or encontrada.expira_em <= agora:
            raise _SessaoInvalida("sessao invalida")
        return encontrada

    def _rotacionar(
        self,
        sessao: _SessaoOperacional,
        atualizada: _SessaoOperacional,
    ) -> tuple[_SessaoOperacional, str]:
        if self._session_factory is None:
            with self._lock:
                corrente = self._sessions.get(sessao.session_id)
                if corrente != sessao:
                    raise _SessaoInvalida("sessao invalida")
                self._sessions.pop(sessao.session_id, None)
                self._sessions[atualizada.session_id] = atualizada
            return atualizada, self._token(atualizada.session_id)

        with self._session_factory() as db, db.begin():
            removida = cast(
                CursorResult[Any],
                db.execute(
                    delete(OperationalSessionORM).where(
                        OperationalSessionORM.session_id == sessao.session_id
                    )
                ),
            )
            if removida.rowcount != 1:
                raise _SessaoInvalida("sessao invalida")
            db.add(self._row_da_sessao(atualizada))
        return atualizada, self._token(atualizada.session_id)

    def trocar_unidade(
        self,
        sessao: _SessaoOperacional,
        *,
        unidade_id: str,
    ) -> tuple[_SessaoOperacional, str]:
        atualizada = replace(
            sessao,
            session_id=secrets.token_urlsafe(32),
            unidade_ativa_id=unidade_id,
            admin_elevado_ate=None,
        )
        return self._rotacionar(sessao, atualizada)

    def trocar_membership(
        self,
        sessao: _SessaoOperacional,
        *,
        identidade: IdentidadeUsuario,
    ) -> tuple[_SessaoOperacional, str]:
        atualizada = replace(
            sessao,
            session_id=secrets.token_urlsafe(32),
            usuario_id=identidade.usuario_id,
            identity_user_id=identidade.global_identity_id,
            membership_id=identidade.membership_subject_id,
            email=identidade.email,
            tenant_id=identidade.tenant_id,
            unidade_ativa_id=identidade.unidade_id,
            admin_elevado_ate=None,
        )
        return self._rotacionar(sessao, atualizada)

    def elevar_admin(
        self,
        sessao: _SessaoOperacional,
    ) -> tuple[_SessaoOperacional, str]:
        agora = datetime.now(timezone.utc)
        elevado_ate = min(
            sessao.expira_em,
            agora + timedelta(seconds=_ADMIN_STEP_UP_TTL_SECONDS),
        )
        atualizada = replace(
            sessao,
            session_id=secrets.token_urlsafe(32),
            admin_elevado_ate=elevado_ate,
        )
        return self._rotacionar(sessao, atualizada)

    def invalidar_identidade(self, identity_user_id: str) -> None:
        identity_id = identity_user_id.strip()
        if not identity_id:
            return
        if self._session_factory is None:
            with self._lock:
                removidas = [
                    session_id
                    for session_id, sessao in self._sessions.items()
                    if sessao.identity_user_id == identity_id
                ]
                for session_id in removidas:
                    self._sessions.pop(session_id, None)
            return
        with self._session_factory() as db, db.begin():
            db.execute(
                delete(OperationalSessionORM).where(
                    OperationalSessionORM.identity_user_id == identity_id
                )
            )

    def invalidar(self, token: str) -> None:
        try:
            session_id = self._session_id_do_token(token)
        except _SessaoInvalida:
            return
        if self._session_factory is None:
            with self._lock:
                self._sessions.pop(session_id, None)
            return
        with self._session_factory() as db, db.begin():
            db.execute(
                delete(OperationalSessionORM).where(
                    OperationalSessionORM.session_id == session_id
                )
            )


class AuthSessionRuntime:
    """Runtime de sessão compartilhado pelos routers HTTP do mesmo app."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        secret_store: SecretStore,
    ) -> None:
        self._session_factory = session_factory
        self._secret_store = secret_store
        self._gerenciador: _GerenciadorSessaoOperacional | None = None
        self._gerenciador_lock = threading.Lock()

    def _obter_gerenciador(self) -> _GerenciadorSessaoOperacional:
        with self._gerenciador_lock:
            if self._gerenciador is None:
                secret = self._secret_store.resolve(
                    _SESSION_SECRET_REFERENCE
                ).reveal()
                self._gerenciador = _GerenciadorSessaoOperacional(
                    secret,
                    session_factory=self._session_factory,
                )
            return self._gerenciador

    @staticmethod
    def token_request(request: Request) -> str | None:
        authorization = request.headers.get("authorization", "").strip()
        if authorization:
            esquema, _, valor = authorization.partition(" ")
            if esquema.casefold() == "bearer":
                return valor.strip() or None
        cookie = request.cookies.get(_SESSION_COOKIE)
        return cookie.strip() if cookie else None

    def _carregar_identidade(
        self,
        sessao: _SessaoOperacional,
    ) -> IdentidadeUsuario:
        with self._session_factory() as session:
            identidade = RepositorioIdentidadesSQLAlchemy(
                session
            ).obter_por_id(usuario_id=sessao.membership_id)
        if (
            identidade is None
            or not identidade.ativo
            or identidade.email != sessao.email
            or identidade.global_identity_id != sessao.identity_user_id
            or identidade.membership_subject_id != sessao.membership_id
            or identidade.tenant_id != sessao.tenant_id
        ):
            raise _SessaoInvalida("sessao invalida")
        try:
            return identidade.no_escopo_ativo(
                tenant_id=sessao.tenant_id,
                unidade_id=sessao.unidade_ativa_id,
            )
        except CredenciaisInvalidas as exc:
            raise _SessaoInvalida("sessao invalida") from exc

    def sessao_autenticada(
        self,
        request: Request,
    ) -> tuple[_GerenciadorSessaoOperacional, _SessaoOperacional, IdentidadeUsuario]:
        token = self.token_request(request)
        if token is None:
            raise _SessaoInvalida("sessao ausente")
        manager = self._obter_gerenciador()
        sessao = manager.resolver(token)
        try:
            identidade = self._carregar_identidade(sessao)
        except _SessaoInvalida:
            manager.invalidar(token)
            raise
        return manager, sessao, identidade

    def resolver_identidade(
        self,
        request: Request,
    ) -> IdentidadeUsuario | None:
        if self.token_request(request) is None:
            return None
        try:
            _, _, identidade = self.sessao_autenticada(request)
            return identidade
        except _SessaoInvalida as exc:
            raise CredenciaisInvalidas("credenciais invalidas") from exc

    def invalidar_identidade(self, identity_user_id: str) -> None:
        self._obter_gerenciador().invalidar_identidade(identity_user_id)

    def admin_status(
        self,
        request: Request,
    ) -> tuple[IdentidadeUsuario, bool, datetime | None]:
        _, sessao, identidade = self.sessao_autenticada(request)
        permitido = Permissao.ADMIN_ACESSAR in identidade.permissoes
        agora = datetime.now(timezone.utc)
        elevado = bool(
            permitido
            and sessao.admin_elevado_ate is not None
            and sessao.admin_elevado_ate > agora
        )
        return identidade, elevado, sessao.admin_elevado_ate if elevado else None


def build_auth_router(
    *,
    session_factory: SessionFactory,
    settings: RuntimeSettings,
    secret_store: SecretStore,
    runtime: AuthSessionRuntime | None = None,
    password_recovery_dispatcher: PasswordRecoveryDispatcher | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1/auth", tags=["auth"])
    runtime = runtime or AuthSessionRuntime(
        session_factory=session_factory,
        secret_store=secret_store,
    )

    def _aplicar_cookie(response: Response, token: str) -> None:
        response.set_cookie(
            key=_SESSION_COOKIE,
            value=token,
            max_age=_SESSION_TTL_SECONDS,
            httponly=True,
            secure=settings.commercial,
            samesite="lax",
            path="/",
        )

    def _limpar_cookie(response: Response) -> None:
        response.delete_cookie(
            key=_SESSION_COOKIE,
            path="/",
            secure=settings.commercial,
            httponly=True,
            samesite="lax",
        )

    def _erro(http_status: int, codigo: str) -> JSONResponse:
        return JSONResponse(status_code=http_status, content={"erro": codigo})

    password_recovery = AplicacaoPasswordRecoveryV1(session_factory)
    password_recovery_limiter = _PasswordRecoveryLimiter()

    def _password_recovery_accepted() -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "accepted": True,
                "message": (
                    "Se existir uma conta elegível com este e-mail, "
                    "enviaremos as instruções de recuperação."
                ),
            },
        )

    def _operador(
        identidade: IdentidadeUsuario,
        *,
        incluir_permissoes: bool,
    ) -> dict[str, object]:
        resumo: dict[str, object] = {
            "usuario_id": identidade.usuario_id,
            "nome": None,
            "email": identidade.email,
            "tenant_id": identidade.tenant_id,
            "unidade_ativa_id": identidade.unidade_id,
            "papeis": sorted(papel.value for papel in identidade.papeis),
        }
        if incluir_permissoes:
            resumo["permissoes"] = sorted(
                permissao.value for permissao in identidade.permissoes
            )
        return resumo

    @router.post("/login")
    def login(payload: LoginIn) -> JSONResponse:
        try:
            with session_factory() as session:
                identidade = ServicoAutenticacao(
                    RepositorioIdentidadesSQLAlchemy(session)
                ).autenticar(email=payload.email, password=payload.senha)
            manager = runtime._obter_gerenciador()
            sessao, token = manager.criar(identidade)
            identidade_ativa = identidade.no_escopo_ativo(
                tenant_id=sessao.tenant_id,
                unidade_id=sessao.unidade_ativa_id,
            )
            response = JSONResponse(
                status_code=status.HTTP_200_OK,
                content=_operador(identidade_ativa, incluir_permissoes=False),
            )
            _aplicar_cookie(response, token)
            return response
        except (ReferenciaSegredoInvalida, SegredoAusente, _SegredoSessaoInseguro):
            return _erro(status.HTTP_503_SERVICE_UNAVAILABLE, "auth.sessao_indisponivel")
        except ErroSeguranca:
            return _erro(status.HTTP_401_UNAUTHORIZED, CredenciaisInvalidas.codigo)

    @router.post("/google")
    def google_login(payload: GoogleCredentialIn) -> JSONResponse:
        client_id = settings.google_oauth_client_id
        if not client_id:
            return _erro(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "auth.google_indisponivel",
            )
        try:
            claims = verify_google_id_token(
                payload.credential,
                client_id=client_id,
            )
        except GoogleIdentityUnavailable as exc:
            return _erro(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
        except GoogleIdentityError as exc:
            return _erro(status.HTTP_401_UNAUTHORIZED, str(exc))

        try:
            with session_factory() as session, session.begin():
                repo = RepositorioIdentidadesSQLAlchemy(session)
                identity_user_id = repo.obter_identity_user_id_por_provedor(
                    provider="google",
                    provider_subject=claims.subject,
                )
                identidade = (
                    repo.obter_por_identity_user_id(
                        identity_user_id=identity_user_id,
                    )
                    if identity_user_id is not None
                    else None
                )
                if identidade is None and identity_user_id is None:
                    identidade = repo.obter_por_email(claims.email)
                    if identidade is None:
                        return JSONResponse(
                            status_code=status.HTTP_404_NOT_FOUND,
                            content={
                                "erro": "auth.google_signup_required",
                                "profile": {
                                    "email": claims.email,
                                    "name": claims.name,
                                },
                            },
                        )
                    repo.vincular_provedor(
                        identity_user_id=identidade.global_identity_id,
                        provider="google",
                        provider_subject=claims.subject,
                        email_at_link=claims.email,
                        hosted_domain=claims.hosted_domain,
                    )
                elif identidade is not None:
                    repo.vincular_provedor(
                        identity_user_id=identidade.global_identity_id,
                        provider="google",
                        provider_subject=claims.subject,
                        email_at_link=claims.email,
                        hosted_domain=claims.hosted_domain,
                    )

            if identidade is None or not identidade.ativo:
                return _erro(
                    status.HTTP_401_UNAUTHORIZED,
                    CredenciaisInvalidas.codigo,
                )
            manager = runtime._obter_gerenciador()
            sessao, token = manager.criar(identidade)
            identidade_ativa = identidade.no_escopo_ativo(
                tenant_id=sessao.tenant_id,
                unidade_id=sessao.unidade_ativa_id,
            )
            response = JSONResponse(
                status_code=status.HTTP_200_OK,
                content=_operador(
                    identidade_ativa,
                    incluir_permissoes=False,
                ),
            )
            _aplicar_cookie(response, token)
            return response
        except (ReferenciaSegredoInvalida, SegredoAusente, _SegredoSessaoInseguro):
            return _erro(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "auth.sessao_indisponivel",
            )
        except (RuntimeError, ValueError):
            return _erro(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "auth.google_vinculo_indisponivel",
            )

    @router.post("/forgot-password")
    def forgot_password(payload: ForgotPasswordIn, request: Request) -> JSONResponse:
        remote = request.client.host if request.client else "unknown"
        email_key = hashlib.sha256(
            payload.email.strip().casefold().encode("utf-8")
        ).hexdigest()
        if not (
            password_recovery_limiter.allow(f"ip:{remote}")
            and password_recovery_limiter.allow(f"email:{email_key}")
        ):
            return _password_recovery_accepted()

        try:
            requested = password_recovery.solicitar(
                email=payload.email,
                correlation_id=request.headers.get("x-correlation-id")
                or f"password-recovery:{secrets.token_urlsafe(12)}",
            )
        except ValueError:
            return _password_recovery_accepted()

        if requested is not None and password_recovery_dispatcher is not None:
            try:
                password_recovery_dispatcher.send_password_reset(
                    email=requested.email,
                    token=requested.token,
                )
            except Exception as exc:  # noqa: BLE001 - provedor externo não altera resposta pública
                logger.warning(
                    "Falha ao enviar e-mail de recuperação de senha",
                    extra={"erro_tipo": type(exc).__name__},
                )
        return _password_recovery_accepted()

    @router.post("/reset-password")
    def reset_password(payload: ResetPasswordIn, request: Request) -> JSONResponse:
        try:
            result = password_recovery.redefinir(
                token=payload.token,
                nova_senha=payload.nova_senha,
                correlation_id=request.headers.get("x-correlation-id")
                or f"password-reset:{secrets.token_urlsafe(12)}",
            )
        except PasswordRecoveryError as exc:
            code = str(exc)
            http_status = (
                status.HTTP_422_UNPROCESSABLE_ENTITY
                if code == "password_recovery_password_invalid"
                else status.HTTP_400_BAD_REQUEST
            )
            return _erro(http_status, code)

        runtime.invalidar_identidade(result.identity_user_id)
        if password_recovery_dispatcher is not None:
            try:
                password_recovery_dispatcher.send_password_changed(
                    email=result.email,
                )
            except Exception as exc:  # noqa: BLE001 - notificação é best-effort
                logger.warning(
                    "Falha ao enviar aviso de alteração de senha",
                    extra={"erro_tipo": type(exc).__name__},
                )
        response = JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"ok": True},
        )
        _limpar_cookie(response)
        return response

    @router.post("/change-password")
    def change_password(payload: ChangePasswordIn, request: Request) -> JSONResponse:
        try:
            _, _, identidade = runtime.sessao_autenticada(request)
        except _SessaoInvalida:
            return _erro(status.HTTP_401_UNAUTHORIZED, CredenciaisInvalidas.codigo)
        except (ReferenciaSegredoInvalida, SegredoAusente, _SegredoSessaoInseguro):
            return _erro(status.HTTP_503_SERVICE_UNAVAILABLE, "auth.sessao_indisponivel")

        if not verify_password(payload.senha_atual, identidade.senha_hash):
            return _erro(status.HTTP_401_UNAUTHORIZED, CredenciaisInvalidas.codigo)

        try:
            result = password_recovery.alterar_senha_autenticada(
                identity=identidade,
                nova_senha=payload.nova_senha,
                correlation_id=request.headers.get("x-correlation-id")
                or f"password-change:{secrets.token_urlsafe(12)}",
            )
        except PasswordRecoveryError as exc:
            return _erro(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

        runtime.invalidar_identidade(result.identity_user_id)
        if password_recovery_dispatcher is not None:
            try:
                password_recovery_dispatcher.send_password_changed(
                    email=result.email,
                )
            except Exception as exc:  # noqa: BLE001 - notificação é best-effort
                logger.warning(
                    "Falha ao enviar aviso de alteração de senha",
                    extra={"erro_tipo": type(exc).__name__},
                )
        response = JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"ok": True, "reauthentication_required": True},
        )
        _limpar_cookie(response)
        return response

    @router.get("/me")
    def me(request: Request) -> JSONResponse:
        try:
            _, _, identidade = runtime.sessao_autenticada(request)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=_operador(identidade, incluir_permissoes=True),
            )
        except _SessaoInvalida:
            return _erro(status.HTTP_401_UNAUTHORIZED, CredenciaisInvalidas.codigo)
        except (ReferenciaSegredoInvalida, SegredoAusente, _SegredoSessaoInseguro):
            return _erro(status.HTTP_503_SERVICE_UNAVAILABLE, "auth.sessao_indisponivel")

    @router.get("/unidades")
    def unidades(request: Request) -> JSONResponse:
        try:
            _, _, identidade = runtime.sessao_autenticada(request)
            content = [
                {"id": unidade_id, "codigo": None, "nome": None}
                for unidade_id in sorted(identidade.unidades_permitidas)
            ]
            return JSONResponse(status_code=status.HTTP_200_OK, content=content)
        except _SessaoInvalida:
            return _erro(status.HTTP_401_UNAUTHORIZED, CredenciaisInvalidas.codigo)
        except (ReferenciaSegredoInvalida, SegredoAusente, _SegredoSessaoInseguro):
            return _erro(status.HTTP_503_SERVICE_UNAVAILABLE, "auth.sessao_indisponivel")

    @router.post("/select-unit")
    def selecionar_unidade(
        payload: SelecionarUnidadeIn,
        request: Request,
    ) -> JSONResponse:
        try:
            manager, sessao, identidade = runtime.sessao_autenticada(request)
        except _SessaoInvalida:
            return _erro(status.HTTP_401_UNAUTHORIZED, CredenciaisInvalidas.codigo)
        except (ReferenciaSegredoInvalida, SegredoAusente, _SegredoSessaoInseguro):
            return _erro(status.HTTP_503_SERVICE_UNAVAILABLE, "auth.sessao_indisponivel")

        try:
            identidade_ativa = identidade.no_escopo_ativo(
                tenant_id=identidade.tenant_id,
                unidade_id=payload.unidade_id,
            )
        except CredenciaisInvalidas:
            return _erro(status.HTTP_403_FORBIDDEN, "seguranca.recurso_indisponivel")

        try:
            _, novo_token = manager.trocar_unidade(
                sessao,
                unidade_id=identidade_ativa.unidade_id,
            )
        except _SessaoInvalida:
            return _erro(status.HTTP_401_UNAUTHORIZED, CredenciaisInvalidas.codigo)

        response = JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"unidade_ativa_id": identidade_ativa.unidade_id},
        )
        _aplicar_cookie(response, novo_token)
        return response


    @router.get("/memberships")
    def memberships(request: Request) -> JSONResponse:
        try:
            _, _, identidade = runtime.sessao_autenticada(request)
            with session_factory() as session:
                memberships_autorizados = RepositorioIdentidadesSQLAlchemy(
                    session
                ).listar_memberships(
                    identity_user_id=identidade.global_identity_id,
                    product_code=identidade.product_code,
                )
            content = [
                {
                    "membership_id": item.membership_subject_id,
                    "tenant_id": item.tenant_id,
                    "product_code": item.product_code,
                    "unidade_padrao_id": item.unidade_id,
                    "ativo": item.ativo,
                    "atual": item.membership_subject_id
                    == identidade.membership_subject_id,
                }
                for item in memberships_autorizados
                if item.ativo
            ]
            return JSONResponse(status_code=status.HTTP_200_OK, content=content)
        except _SessaoInvalida:
            return _erro(status.HTTP_401_UNAUTHORIZED, CredenciaisInvalidas.codigo)
        except (ReferenciaSegredoInvalida, SegredoAusente, _SegredoSessaoInseguro):
            return _erro(status.HTTP_503_SERVICE_UNAVAILABLE, "auth.sessao_indisponivel")

    @router.post("/select-membership")
    def selecionar_membership(
        payload: SelecionarMembershipIn,
        request: Request,
    ) -> JSONResponse:
        try:
            manager, sessao, identidade = runtime.sessao_autenticada(request)
        except _SessaoInvalida:
            return _erro(status.HTTP_401_UNAUTHORIZED, CredenciaisInvalidas.codigo)
        except (ReferenciaSegredoInvalida, SegredoAusente, _SegredoSessaoInseguro):
            return _erro(status.HTTP_503_SERVICE_UNAVAILABLE, "auth.sessao_indisponivel")

        with session_factory() as session:
            alvo = RepositorioIdentidadesSQLAlchemy(session).obter_por_id(
                usuario_id=payload.membership_id
            )
        if (
            alvo is None
            or not alvo.ativo
            or alvo.global_identity_id != identidade.global_identity_id
            or alvo.product_code != identidade.product_code
        ):
            return _erro(status.HTTP_403_FORBIDDEN, "seguranca.recurso_indisponivel")

        try:
            _, novo_token = manager.trocar_membership(sessao, identidade=alvo)
        except _SessaoInvalida:
            return _erro(status.HTTP_401_UNAUTHORIZED, CredenciaisInvalidas.codigo)

        response = JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "membership_id": alvo.membership_subject_id,
                "tenant_id": alvo.tenant_id,
                "unidade_ativa_id": alvo.unidade_id,
            },
        )
        _aplicar_cookie(response, novo_token)
        return response

    @router.get("/admin-status")
    def admin_status(request: Request) -> JSONResponse:
        try:
            identidade, elevado, expira_em = runtime.admin_status(request)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "permitido": Permissao.ADMIN_ACESSAR in identidade.permissoes,
                    "elevado": elevado,
                    "expira_em": expira_em.isoformat() if expira_em else None,
                },
            )
        except _SessaoInvalida:
            return _erro(status.HTTP_401_UNAUTHORIZED, CredenciaisInvalidas.codigo)
        except (ReferenciaSegredoInvalida, SegredoAusente, _SegredoSessaoInseguro):
            return _erro(status.HTTP_503_SERVICE_UNAVAILABLE, "auth.sessao_indisponivel")

    @router.post("/admin-step-up")
    def admin_step_up(payload: AdminStepUpIn, request: Request) -> JSONResponse:
        try:
            manager, sessao, identidade = runtime.sessao_autenticada(request)
            if Permissao.ADMIN_ACESSAR not in identidade.permissoes:
                return _erro(status.HTTP_403_FORBIDDEN, "seguranca.permissao_insuficiente")

            with session_factory() as session:
                confirmada = ServicoAutenticacao(
                    RepositorioIdentidadesSQLAlchemy(session)
                ).autenticar(email=identidade.email, password=payload.senha)
            if confirmada.global_identity_id != identidade.global_identity_id:
                return _erro(status.HTTP_401_UNAUTHORIZED, CredenciaisInvalidas.codigo)

            elevada, novo_token = manager.elevar_admin(sessao)
            response = JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "ok": True,
                    "expira_em": elevada.admin_elevado_ate.isoformat()
                    if elevada.admin_elevado_ate
                    else None,
                },
            )
            _aplicar_cookie(response, novo_token)
            return response
        except CredenciaisInvalidas:
            return _erro(status.HTTP_401_UNAUTHORIZED, CredenciaisInvalidas.codigo)
        except _SessaoInvalida:
            return _erro(status.HTTP_401_UNAUTHORIZED, CredenciaisInvalidas.codigo)
        except (ReferenciaSegredoInvalida, SegredoAusente, _SegredoSessaoInseguro):
            return _erro(status.HTTP_503_SERVICE_UNAVAILABLE, "auth.sessao_indisponivel")

    @router.post("/logout")
    def logout(request: Request) -> JSONResponse:
        token = runtime.token_request(request)
        if token is not None:
            try:
                runtime._obter_gerenciador().invalidar(token)
            except (ReferenciaSegredoInvalida, SegredoAusente, _SegredoSessaoInseguro):
                pass
        response = JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"ok": True},
        )
        _limpar_cookie(response)
        return response

    return router
