"""Adaptador HTTP canônico de autenticação e sessão operacional V1."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.runtime.config import RuntimeSettings
from core.seguranca.autenticacao import IdentidadeUsuario, ServicoAutenticacao
from core.seguranca.erros import (
    CredenciaisInvalidas,
    ErroSeguranca,
    ReferenciaSegredoInvalida,
    SegredoAusente,
)
from core.seguranca.segredos import SecretStore
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy

SessionFactory = Callable[[], Session]

_SESSION_COOKIE = "fm_ai_session"
_SESSION_SECRET_REFERENCE = "env:FM_AI_SESSION_SECRET"
_SESSION_TTL_SECONDS = 8 * 60 * 60
_MIN_SESSION_SECRET_BYTES = 32


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    senha: str = Field(min_length=1, max_length=1024)


class SelecionarUnidadeIn(BaseModel):
    unidade_id: str = Field(min_length=1, max_length=64)


@dataclass(frozen=True)
class _SessaoOperacional:
    session_id: str
    usuario_id: str
    email: str
    tenant_id: str
    unidade_ativa_id: str
    expira_em: datetime


class _SessaoInvalida(ValueError):
    pass


class _SegredoSessaoInseguro(RuntimeError):
    pass


class _GerenciadorSessaoOperacional:
    def __init__(self, secret: str) -> None:
        segredo = secret.encode("utf-8")
        if len(segredo) < _MIN_SESSION_SECRET_BYTES:
            raise _SegredoSessaoInseguro("segredo de sessao inseguro")
        self._secret = segredo
        self._sessions: dict[str, _SessaoOperacional] = {}
        self._lock = threading.Lock()

    def _assinatura(self, session_id: str) -> str:
        digest = hmac.new(
            self._secret,
            f"auth-session-v1:{session_id}".encode("utf-8"),
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

    def _limpar_expiradas_locked(self, agora: datetime) -> None:
        expiradas = [
            session_id
            for session_id, sessao in self._sessions.items()
            if sessao.expira_em <= agora
        ]
        for session_id in expiradas:
            self._sessions.pop(session_id, None)

    def criar(self, identidade: IdentidadeUsuario) -> tuple[_SessaoOperacional, str]:
        agora = datetime.now(timezone.utc)
        sessao = _SessaoOperacional(
            session_id=secrets.token_urlsafe(32),
            usuario_id=identidade.usuario_id,
            email=identidade.email,
            tenant_id=identidade.tenant_id,
            unidade_ativa_id=identidade.unidade_id,
            expira_em=agora + timedelta(seconds=_SESSION_TTL_SECONDS),
        )
        with self._lock:
            self._limpar_expiradas_locked(agora)
            self._sessions[sessao.session_id] = sessao
        return sessao, self._token(sessao.session_id)

    def resolver(self, token: str) -> _SessaoOperacional:
        session_id = self._session_id_do_token(token)
        agora = datetime.now(timezone.utc)
        with self._lock:
            self._limpar_expiradas_locked(agora)
            sessao = self._sessions.get(session_id)
        if sessao is None:
            raise _SessaoInvalida("sessao invalida")
        return sessao

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
        )
        with self._lock:
            corrente = self._sessions.get(sessao.session_id)
            if corrente != sessao:
                raise _SessaoInvalida("sessao invalida")
            self._sessions.pop(sessao.session_id, None)
            self._sessions[atualizada.session_id] = atualizada
        return atualizada, self._token(atualizada.session_id)

    def invalidar(self, token: str) -> None:
        try:
            session_id = self._session_id_do_token(token)
        except _SessaoInvalida:
            return
        with self._lock:
            self._sessions.pop(session_id, None)


def build_auth_router(
    *,
    session_factory: SessionFactory,
    settings: RuntimeSettings,
    secret_store: SecretStore,
) -> APIRouter:
    router = APIRouter(prefix="/v1/auth", tags=["auth"])
    gerenciador: _GerenciadorSessaoOperacional | None = None
    gerenciador_lock = threading.Lock()

    def _obter_gerenciador() -> _GerenciadorSessaoOperacional:
        nonlocal gerenciador
        with gerenciador_lock:
            if gerenciador is None:
                secret = secret_store.resolve(_SESSION_SECRET_REFERENCE).reveal()
                gerenciador = _GerenciadorSessaoOperacional(secret)
            return gerenciador

    def _token_request(request: Request) -> str | None:
        authorization = request.headers.get("authorization", "").strip()
        if authorization:
            esquema, _, valor = authorization.partition(" ")
            if esquema.casefold() == "bearer":
                return valor.strip() or None
        cookie = request.cookies.get(_SESSION_COOKIE)
        return cookie.strip() if cookie else None

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

    def _carregar_identidade(sessao: _SessaoOperacional) -> IdentidadeUsuario:
        with session_factory() as session:
            identidade = RepositorioIdentidadesSQLAlchemy(session).obter_por_id(
                usuario_id=sessao.usuario_id
            )
        if (
            identidade is None
            or not identidade.ativo
            or identidade.email != sessao.email
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

    def _sessao_autenticada(
        request: Request,
    ) -> tuple[_GerenciadorSessaoOperacional, _SessaoOperacional, IdentidadeUsuario]:
        token = _token_request(request)
        if token is None:
            raise _SessaoInvalida("sessao ausente")
        manager = _obter_gerenciador()
        sessao = manager.resolver(token)
        try:
            identidade = _carregar_identidade(sessao)
        except _SessaoInvalida:
            manager.invalidar(token)
            raise
        return manager, sessao, identidade

    @router.post("/login")
    def login(payload: LoginIn) -> JSONResponse:
        try:
            with session_factory() as session:
                identidade = ServicoAutenticacao(
                    RepositorioIdentidadesSQLAlchemy(session)
                ).autenticar(email=payload.email, password=payload.senha)
            manager = _obter_gerenciador()
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
            return _erro(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "auth.sessao_indisponivel",
            )
        except ErroSeguranca:
            return _erro(
                status.HTTP_401_UNAUTHORIZED,
                CredenciaisInvalidas.codigo,
            )

    @router.get("/me")
    def me(request: Request) -> JSONResponse:
        try:
            _, _, identidade = _sessao_autenticada(request)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=_operador(identidade, incluir_permissoes=True),
            )
        except _SessaoInvalida:
            return _erro(
                status.HTTP_401_UNAUTHORIZED,
                CredenciaisInvalidas.codigo,
            )
        except (ReferenciaSegredoInvalida, SegredoAusente, _SegredoSessaoInseguro):
            return _erro(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "auth.sessao_indisponivel",
            )

    @router.get("/unidades")
    def unidades(request: Request) -> JSONResponse:
        try:
            _, _, identidade = _sessao_autenticada(request)
            content = [
                {"id": unidade_id, "codigo": None, "nome": None}
                for unidade_id in sorted(identidade.unidades_permitidas)
            ]
            return JSONResponse(status_code=status.HTTP_200_OK, content=content)
        except _SessaoInvalida:
            return _erro(
                status.HTTP_401_UNAUTHORIZED,
                CredenciaisInvalidas.codigo,
            )
        except (ReferenciaSegredoInvalida, SegredoAusente, _SegredoSessaoInseguro):
            return _erro(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "auth.sessao_indisponivel",
            )

    @router.post("/select-unit")
    def selecionar_unidade(
        payload: SelecionarUnidadeIn,
        request: Request,
    ) -> JSONResponse:
        try:
            manager, sessao, identidade = _sessao_autenticada(request)
        except _SessaoInvalida:
            return _erro(
                status.HTTP_401_UNAUTHORIZED,
                CredenciaisInvalidas.codigo,
            )
        except (ReferenciaSegredoInvalida, SegredoAusente, _SegredoSessaoInseguro):
            return _erro(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "auth.sessao_indisponivel",
            )

        try:
            identidade_ativa = identidade.no_escopo_ativo(
                tenant_id=identidade.tenant_id,
                unidade_id=payload.unidade_id,
            )
        except CredenciaisInvalidas:
            return _erro(
                status.HTTP_403_FORBIDDEN,
                "seguranca.recurso_indisponivel",
            )

        try:
            _, novo_token = manager.trocar_unidade(
                sessao,
                unidade_id=identidade_ativa.unidade_id,
            )
        except _SessaoInvalida:
            return _erro(
                status.HTTP_401_UNAUTHORIZED,
                CredenciaisInvalidas.codigo,
            )

        response = JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"unidade_ativa_id": identidade_ativa.unidade_id},
        )
        _aplicar_cookie(response, novo_token)
        return response

    @router.post("/logout")
    def logout(request: Request) -> JSONResponse:
        token = _token_request(request)
        if token is not None:
            try:
                _obter_gerenciador().invalidar(token)
            except (ReferenciaSegredoInvalida, SegredoAusente, _SegredoSessaoInseguro):
                pass
        response = JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"ok": True},
        )
        _limpar_cookie(response)
        return response

    return router
