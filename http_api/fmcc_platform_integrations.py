"""Command/FM control plane for platform-managed external integrations.

This boundary is server-to-server and never belongs to a customer tenant UI.
Gemini, Google Maps and future FM-owned providers are configured once in the
canonical FM platform scope and then consumed by authorized product tenants.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from application.integracoes_admin_transacoes import AplicacaoIntegracoesAdminV1
from core.integracoes.catalogo import CATALOGO_V1, EscopoGestaoIntegracao
from core.integracoes.modelos import AmbienteIntegracao, ErroConfiguracaoServico
from core.integracoes.platform_scope import (
    FM_PLATFORM_PRODUCT_CODE,
    FM_PLATFORM_TENANT_ID,
    FM_PLATFORM_UNIT_ID,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import PermissaoInsuficiente
from core.seguranca.permissoes import Papel, Permissao
from http_api.admin_integracoes import (
    CatalogoItemOut,
    ConfiguracaoSalvaOut,
    HealthcheckOut,
    IntegracaoOut,
    IntegracoesListOut,
    IntegracoesPutIn,
    _catalogo_item_out,
    _credenciais_estado,
    _criar_servico_e_vault,
    _executar_healthcheck_por_provedor,
    _prontidao_out,
)
from http_api.fmcc_commercial_control import (
    FMCCActorIn,
    _authorize,
    _fresh_step_up,
)
from infra.integracoes.repositorio_sqlalchemy import (
    RepositorioConfiguracoesExternasSQLAlchemy,
)


class FMCCIntegrationConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: FMCCActorIn
    configuracao: IntegracoesPutIn


class FMCCIntegrationActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: FMCCActorIn


class FMCCIntegrationHomologarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: FMCCActorIn
    evidencia_ref: str = Field(min_length=1, max_length=512)


def _error(http_status: int, code: str) -> JSONResponse:
    return JSONResponse(status_code=http_status, content={"error": code})


def _handle_error(exc: Exception) -> JSONResponse:
    if isinstance(exc, PermissaoInsuficiente):
        return _error(status.HTTP_403_FORBIDDEN, str(exc))
    if isinstance(exc, ErroConfiguracaoServico):
        code = str(exc)
        return _error(
            status.HTTP_409_CONFLICT
            if code == "versao_configuracao_divergente"
            else status.HTTP_400_BAD_REQUEST,
            code,
        )
    if isinstance(exc, PermissionError):
        return _error(status.HTTP_403_FORBIDDEN, str(exc))
    if isinstance(exc, (TypeError, ValueError)):
        return _error(status.HTTP_400_BAD_REQUEST, "fmcc.integrations.invalid_request")
    return _error(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "fmcc.integrations.unavailable",
    )


def _context(
    *,
    actor: FMCCActorIn,
    correlation_id: str,
    requested_at: datetime,
) -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=FM_PLATFORM_TENANT_ID,
        unidade_id=FM_PLATFORM_UNIT_ID,
        usuario_id=actor.user_id,
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(
            {
                Permissao.ADMIN_ACESSAR,
                Permissao.INTEGRACAO_GERENCIAR,
            }
        ),
        correlation_id=correlation_id,
        solicitado_em=requested_at,
        origem="fm_command_platform_integrations_v1",
        unidades_permitidas=frozenset({FM_PLATFORM_UNIT_ID}),
        identity_user_id=actor.user_id,
        product_code=FM_PLATFORM_PRODUCT_CODE,
        metadata=(
            ("fmcc_role", actor.role),
            ("fmcc_step_up_at", actor.step_up_at.isoformat()),
        ),
    )


def _correlation_id(request: Request, requested_at: datetime) -> str:
    value = request.headers.get("x-correlation-id", "").strip()
    if value:
        return value[:128]
    value = request.headers.get("x-request-id", "").strip()
    if value:
        return value[:128]
    return f"fmcc-integrations-{int(requested_at.timestamp() * 1000000)}"


def _require_fresh_actor(
    actor: FMCCActorIn,
    *,
    request: Request,
) -> tuple[ContextoExecucao, JSONResponse | None]:
    now = datetime.now(timezone.utc)
    if not _fresh_step_up(actor, now=now):
        return (
            _context(
                actor=actor,
                correlation_id=_correlation_id(request, now),
                requested_at=now,
            ),
            _error(
                status.HTTP_403_FORBIDDEN,
                "fmcc_control_plane.step_up_required",
            ),
        )
    return (
        _context(
            actor=actor,
            correlation_id=_correlation_id(request, now),
            requested_at=now,
        ),
        None,
    )


def _ensure_platform_spec(servico: str, provedor: str):
    spec = CATALOGO_V1.obter(servico, provedor)
    if spec.escopo_gestao is not EscopoGestaoIntegracao.PLATFORM_MANAGED:
        raise PermissionError("fmcc.integrations.tenant_managed_forbidden")
    return spec


def _config_out(
    *,
    service,
    contexto: ContextoExecucao,
    configuracao,
    spec,
) -> ConfiguracaoSalvaOut:
    readiness = service.avaliar(
        contexto=contexto,
        configuracao_id=configuracao.configuracao_id,
    )
    return ConfiguracaoSalvaOut(
        configuracao_id=configuracao.configuracao_id,
        servico=configuracao.servico,
        provedor=configuracao.provedor,
        conta_externa=configuracao.conta_externa,
        ambiente=configuracao.ambiente.value,
        parametros=configuracao.parametros,
        credenciais_estado=_credenciais_estado(configuracao, spec),
        habilitada=configuracao.habilitada,
        homologada=configuracao.homologada,
        evidencia_homologacao_ref=configuracao.evidencia_homologacao_ref,
        versao=configuracao.versao,
        prontidao=_prontidao_out(readiness),
    )


def build_fmcc_platform_integrations_router(
    *,
    session_factory,
    control_plane_token: str | None,
    master_key: str | None = None,
) -> APIRouter:
    router = APIRouter(
        prefix="/v1/control-plane/fmcc/integrations",
        tags=["fmcc-platform-integrations"],
    )
    app = AplicacaoIntegracoesAdminV1(
        session_factory,
        master_key=master_key,
    )

    def auth(authorization: str | None) -> JSONResponse | None:
        return _authorize(authorization, control_plane_token)

    @router.get("", response_model=None)
    def list_platform_integrations(
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> IntegracoesListOut | JSONResponse:
        denied = auth(authorization)
        if denied is not None:
            return denied

        now = datetime.now(timezone.utc)
        reader = FMCCActorIn(
            user_id="fmcc-platform-reader",
            role="admin",
            step_up_at=now,
        )
        contexto = _context(
            actor=reader,
            correlation_id=_correlation_id(request, now),
            requested_at=now,
        )
        try:
            with session_factory() as session:
                service, _vault = _criar_servico_e_vault(session, master_key)
                configs = {
                    item.configuracao_id: item
                    for item in service.listar(contexto=contexto)
                }
                result: list[IntegracaoOut] = []
                for spec in CATALOGO_V1.listar_por_escopo(
                    EscopoGestaoIntegracao.PLATFORM_MANAGED
                ):
                    config_id = f"{spec.servico}--{spec.provedor}"
                    config = configs.get(config_id)
                    result.append(
                        IntegracaoOut(
                            catalogo=_catalogo_item_out(spec),
                            configuracao=(
                                _config_out(
                                    service=service,
                                    contexto=contexto,
                                    configuracao=config,
                                    spec=spec,
                                )
                                if config is not None
                                else None
                            ),
                        )
                    )
                return IntegracoesListOut(integracoes=result)
        except Exception as exc:  # noqa: BLE001 - fail-closed boundary
            return _handle_error(exc)

    @router.put("/{config_id}", response_model=None)
    def configure_platform_integration(
        config_id: str,
        body: FMCCIntegrationConfigIn,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> ConfiguracaoSalvaOut | JSONResponse:
        denied = auth(authorization)
        if denied is not None:
            return denied
        contexto, actor_denied = _require_fresh_actor(body.actor, request=request)
        if actor_denied is not None:
            return actor_denied

        try:
            payload = body.configuracao
            spec = _ensure_platform_spec(payload.servico, payload.provedor)
            expected_id = f"{spec.servico}--{spec.provedor}"
            if config_id != expected_id:
                raise ValueError("config_id_mismatch")
            ambiente = AmbienteIntegracao(payload.ambiente.strip().casefold())
            parametros = {item.nome: item.valor for item in payload.parametros}
            novos_segredos = {
                item.papel: item.valor
                for item in payload.credenciais
                if item.valor.strip()
            }

            with session_factory() as session:
                existente = RepositorioConfiguracoesExternasSQLAlchemy(session).obter(
                    tenant_id=FM_PLATFORM_TENANT_ID,
                    unidade_id=FM_PLATFORM_UNIT_ID,
                    configuracao_id=config_id,
                )
                finalidades_atuais = dict(existente.credenciais) if existente else {}

            saved, _rotated = app.salvar_configuracao(
                contexto,
                configuracao_id=config_id,
                servico=spec.servico,
                provedor=spec.provedor,
                conta_externa=payload.conta_externa.strip(),
                ambiente=ambiente,
                parametros_publicos=parametros,
                finalidades_atuais=finalidades_atuais,
                novos_segredos=novos_segredos,
                habilitada=payload.habilitada,
                versao_esperada=payload.versao,
            )
            with session_factory() as session:
                service, _vault = _criar_servico_e_vault(session, master_key)
                return _config_out(
                    service=service,
                    contexto=contexto,
                    configuracao=saved,
                    spec=spec,
                )
        except Exception as exc:  # noqa: BLE001
            return _handle_error(exc)

    @router.post("/{config_id}/healthcheck", response_model=None)
    def healthcheck_platform_integration(
        config_id: str,
        body: FMCCIntegrationActionIn,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> HealthcheckOut | JSONResponse:
        denied = auth(authorization)
        if denied is not None:
            return denied
        contexto, actor_denied = _require_fresh_actor(body.actor, request=request)
        if actor_denied is not None:
            return actor_denied

        try:
            with session_factory() as session:
                service, vault = _criar_servico_e_vault(session, master_key)
                config = service.obter(
                    contexto=contexto,
                    configuracao_id=config_id,
                )
                _ensure_platform_spec(config.servico, config.provedor)
                return _executar_healthcheck_por_provedor(
                    session=session,
                    secret_store=vault,
                    contexto=contexto,
                    provedor=config.provedor,
                    configuracao_id=config_id,
                )
        except Exception as exc:  # noqa: BLE001
            return _handle_error(exc)

    @router.post("/{config_id}/homologar", response_model=None)
    def homologate_platform_integration(
        config_id: str,
        body: FMCCIntegrationHomologarIn,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> ConfiguracaoSalvaOut | JSONResponse:
        denied = auth(authorization)
        if denied is not None:
            return denied
        contexto, actor_denied = _require_fresh_actor(body.actor, request=request)
        if actor_denied is not None:
            return actor_denied

        try:
            with session_factory() as session:
                service, _vault = _criar_servico_e_vault(session, master_key)
                current = service.obter(
                    contexto=contexto,
                    configuracao_id=config_id,
                )
                spec = _ensure_platform_spec(
                    current.servico,
                    current.provedor,
                )

            homologated = app.homologar(
                contexto,
                configuracao_id=config_id,
                evidencia_ref=body.evidencia_ref.strip(),
            )
            with session_factory() as session:
                service, _vault = _criar_servico_e_vault(session, master_key)
                return _config_out(
                    service=service,
                    contexto=contexto,
                    configuracao=homologated,
                    spec=spec,
                )
        except Exception as exc:  # noqa: BLE001
            return _handle_error(exc)

    return router
