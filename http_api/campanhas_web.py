"""HTTP session-aware da Central Web de Campanhas — WP-017."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from application.campanhas_web import (
    aprovar_campanha_web,
    atualizar_campanha_web,
    criar_campanha_web,
    definir_audiencia_campanha,
    despachar_campanha_web,
    historico_campanha_web,
    listar_audiencia_campanha,
    listar_campanhas_web,
    obter_campanha_web,
    publicar_campanha_web,
    submeter_campanha_web,
)
from core.crm.erros import ErroCRM
from core.gerente_ia.erros import ErroGerenteIA
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from core.seguranca.permissoes import Permissao
from http_api.auth import AuthSessionRuntime
from http_api.operational_auth import obter_identidade_operacional

SessionFactory = Callable[[], Session]
_MAX_IDEMPOTENCY_KEY = 160


class CampanhaConteudoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canal: str = Field(min_length=1, max_length=32)
    finalidade: str = Field(min_length=1, max_length=64)
    objetivo: str = Field(min_length=1, max_length=240)
    texto_base: str = Field(min_length=1, max_length=2000)


class AudienciaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cliente_ids: list[str] = Field(min_length=1, max_length=200)


class FingerprintIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fingerprint: str = Field(min_length=64, max_length=64)


def _erro(http_status: int, codigo: str) -> JSONResponse:
    return JSONResponse(status_code=http_status, content={"erro": codigo})


def _idempotency_key(request: Request) -> str:
    key = request.headers.get("idempotency-key", "").strip()
    if not key:
        raise ValueError("idempotency_key_obrigatoria")
    if len(key) > _MAX_IDEMPOTENCY_KEY:
        raise ValueError("idempotency_key_excede_limite")
    return key


def _identidade(
    request: Request,
    session: Session,
    *,
    auth_runtime: AuthSessionRuntime,
) -> tuple[IdentidadeUsuario, str]:
    resolved = obter_identidade_operacional(
        request,
        session,
        auth_runtime=auth_runtime,
    )
    return resolved.identidade, resolved.modo


def _exigir(identidade: IdentidadeUsuario, *permissoes: Permissao) -> None:
    if any(permissao not in identidade.permissoes for permissao in permissoes):
        raise PermissionError("seguranca.permissao_insuficiente")


def _contexto(identidade: IdentidadeUsuario, request: Request):
    return identidade.contexto(
        origem="campanhas_web_v1",
        correlation_id=request.headers.get("x-correlation-id") or None,
    )


def _step_up(
    *,
    request: Request,
    identidade: IdentidadeUsuario,
    modo: str,
    auth_runtime: AuthSessionRuntime,
) -> None:
    _exigir(identidade, Permissao.CAMPANHA_APROVAR)
    if modo == "session":
        _exigir(identidade, Permissao.ADMIN_ACESSAR)
        _, elevado, _ = auth_runtime.admin_status(request)
        if not elevado:
            raise PermissionError("seguranca.admin_step_up_exigido")


def _tratar_erro(exc: Exception) -> JSONResponse:
    if isinstance(exc, CredenciaisInvalidas):
        return _erro(status.HTTP_401_UNAUTHORIZED, "credenciais_invalidas")
    if isinstance(exc, (ErroSeguranca, PermissionError)):
        return _erro(
            status.HTTP_403_FORBIDDEN,
            str(getattr(exc, "codigo", str(exc) or "seguranca.permissao_insuficiente")),
        )
    if isinstance(exc, ValueError):
        return _erro(status.HTTP_400_BAD_REQUEST, str(exc))
    if isinstance(exc, ErroGerenteIA):
        codigo = exc.codigo
        if codigo in {
            "fingerprint_divergente",
            "conflito_idempotencia",
            "campanha_audiencia_desatualizada",
            "campanha_audiencia_contem_cliente_inelegivel",
            "campanha_nao_aguarda_aprovacao",
            "campanha_nao_esta_aprovada",
            "campanha_nao_publicavel",
            "campanha_nao_editavel",
        }:
            return _erro(status.HTTP_409_CONFLICT, codigo)
        if codigo == "recurso_indisponivel":
            return _erro(status.HTTP_404_NOT_FOUND, codigo)
        if "permiss" in codigo or "humana" in codigo:
            return _erro(status.HTTP_403_FORBIDDEN, codigo)
        return _erro(status.HTTP_400_BAD_REQUEST, codigo)
    if isinstance(exc, ErroCRM):
        return _erro(status.HTTP_409_CONFLICT, str(exc))
    return _erro(status.HTTP_503_SERVICE_UNAVAILABLE, "campanhas.indisponivel")


def _out(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        data = asdict(value)
        for key, item in tuple(data.items()):
            if hasattr(item, "isoformat"):
                data[key] = item.isoformat()
        return data
    return value


def build_campanhas_web_router(
    *,
    session_factory: SessionFactory,
    auth_runtime: AuthSessionRuntime,
) -> APIRouter:
    router = APIRouter(prefix="/v1/campanhas", tags=["campanhas-web"])

    def identidade(request: Request) -> tuple[IdentidadeUsuario, str]:
        with session_factory() as session:
            item, modo = _identidade(request, session, auth_runtime=auth_runtime)
        _exigir(
            item,
            Permissao.ADMIN_ACESSAR,
            Permissao.CLIENTE_VISUALIZAR,
            Permissao.CAMPANHA_CRIAR,
        )
        return item, modo

    @router.get("", response_model=None)
    def listar(request: Request) -> dict[str, Any] | JSONResponse:
        try:
            item, _ = identidade(request)
            dados = listar_campanhas_web(
                session_factory=session_factory,
                contexto=_contexto(item, request),
            )
            return {"itens": [_out(value) for value in dados]}
        except Exception as exc:  # noqa: BLE001
            return _tratar_erro(exc)

    @router.post("", response_model=None)
    def criar(payload: CampanhaConteudoIn, request: Request) -> dict[str, Any] | JSONResponse:
        try:
            item, _ = identidade(request)
            value = criar_campanha_web(
                session_factory=session_factory,
                contexto=_contexto(item, request),
                canal=payload.canal,
                finalidade=payload.finalidade,
                objetivo=payload.objetivo,
                texto_base=payload.texto_base,
                idempotency_key=_idempotency_key(request),
            )
            return _out(value)
        except Exception as exc:  # noqa: BLE001
            return _tratar_erro(exc)

    @router.get("/{campanha_id}", response_model=None)
    def detalhe(campanha_id: str, request: Request) -> dict[str, Any] | JSONResponse:
        try:
            item, _ = identidade(request)
            return _out(
                obter_campanha_web(
                    session_factory=session_factory,
                    contexto=_contexto(item, request),
                    campanha_id=campanha_id,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _tratar_erro(exc)

    @router.patch("/{campanha_id}", response_model=None)
    def editar(
        campanha_id: str, payload: CampanhaConteudoIn, request: Request
    ) -> dict[str, Any] | JSONResponse:
        try:
            item, _ = identidade(request)
            return _out(
                atualizar_campanha_web(
                    session_factory=session_factory,
                    contexto=_contexto(item, request),
                    campanha_id=campanha_id,
                    canal=payload.canal,
                    finalidade=payload.finalidade,
                    objetivo=payload.objetivo,
                    texto_base=payload.texto_base,
                    idempotency_key=_idempotency_key(request),
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _tratar_erro(exc)

    @router.get("/{campanha_id}/audiencia", response_model=None)
    def audiencia(campanha_id: str, request: Request) -> dict[str, Any] | JSONResponse:
        try:
            item, _ = identidade(request)
            dados = listar_audiencia_campanha(
                session_factory=session_factory,
                contexto=_contexto(item, request),
                campanha_id=campanha_id,
            )
            return {"itens": [_out(value) for value in dados]}
        except Exception as exc:  # noqa: BLE001
            return _tratar_erro(exc)

    @router.put("/{campanha_id}/audiencia", response_model=None)
    def salvar_audiencia(
        campanha_id: str, payload: AudienciaIn, request: Request
    ) -> dict[str, Any] | JSONResponse:
        try:
            item, _ = identidade(request)
            return _out(
                definir_audiencia_campanha(
                    session_factory=session_factory,
                    contexto=_contexto(item, request),
                    campanha_id=campanha_id,
                    cliente_ids=tuple(payload.cliente_ids),
                    idempotency_key=_idempotency_key(request),
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _tratar_erro(exc)

    @router.post("/{campanha_id}/submeter", response_model=None)
    def submeter(campanha_id: str, request: Request) -> dict[str, Any] | JSONResponse:
        try:
            item, _ = identidade(request)
            return _out(
                submeter_campanha_web(
                    session_factory=session_factory,
                    contexto=_contexto(item, request),
                    campanha_id=campanha_id,
                    idempotency_key=_idempotency_key(request),
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _tratar_erro(exc)

    @router.post("/{campanha_id}/aprovar", response_model=None)
    def aprovar(
        campanha_id: str, payload: FingerprintIn, request: Request
    ) -> dict[str, Any] | JSONResponse:
        try:
            item, modo = identidade(request)
            _step_up(
                request=request,
                identidade=item,
                modo=modo,
                auth_runtime=auth_runtime,
            )
            return _out(
                aprovar_campanha_web(
                    session_factory=session_factory,
                    contexto=_contexto(item, request),
                    campanha_id=campanha_id,
                    fingerprint=payload.fingerprint,
                    idempotency_key=_idempotency_key(request),
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _tratar_erro(exc)

    @router.post("/{campanha_id}/publicar", response_model=None)
    def publicar(
        campanha_id: str, payload: FingerprintIn, request: Request
    ) -> dict[str, Any] | JSONResponse:
        try:
            item, modo = identidade(request)
            _step_up(
                request=request,
                identidade=item,
                modo=modo,
                auth_runtime=auth_runtime,
            )
            return _out(
                publicar_campanha_web(
                    session_factory=session_factory,
                    contexto=_contexto(item, request),
                    campanha_id=campanha_id,
                    fingerprint=payload.fingerprint,
                    idempotency_key=_idempotency_key(request),
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _tratar_erro(exc)

    @router.post("/{campanha_id}/despachar", response_model=None)
    def despachar(
        campanha_id: str, payload: FingerprintIn, request: Request
    ) -> dict[str, Any] | JSONResponse:
        try:
            item, modo = identidade(request)
            _step_up(
                request=request,
                identidade=item,
                modo=modo,
                auth_runtime=auth_runtime,
            )
            return despachar_campanha_web(
                session_factory=session_factory,
                contexto=_contexto(item, request),
                campanha_id=campanha_id,
                fingerprint=payload.fingerprint,
                idempotency_key=_idempotency_key(request),
            )
        except Exception as exc:  # noqa: BLE001
            return _tratar_erro(exc)

    @router.get("/{campanha_id}/historico", response_model=None)
    def historico(campanha_id: str, request: Request) -> dict[str, Any] | JSONResponse:
        try:
            item, _ = identidade(request)
            dados = historico_campanha_web(
                session_factory=session_factory,
                contexto=_contexto(item, request),
                campanha_id=campanha_id,
            )
            return {"itens": [_out(value) for value in dados]}
        except Exception as exc:  # noqa: BLE001
            return _tratar_erro(exc)

    return router
