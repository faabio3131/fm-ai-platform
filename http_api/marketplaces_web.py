"""Boundary Web do WP-012 dentro da Central de Pedidos existente."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from application.marketplaces_web import AplicacaoMarketplacesWebV1
from core.marketplaces.erros import ErroMarketplace, ErroMarketplaceTransitorio
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from core.seguranca.permissoes import Permissao
from http_api.auth import AuthSessionRuntime
from http_api.operational_auth import obter_identidade_operacional

SessionFactory = Callable[[], Session]


class MarketplaceIntegracaoOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    configuracao_id: str
    plataforma: str
    conta_externa: str
    ambiente: str
    habilitada: bool
    homologada: bool
    evidencia_homologacao_ref: str | None
    pedidos_sincronizados: int
    pronta_para_sincronizar: bool


class MarketplaceIntegracoesOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    integracoes: list[MarketplaceIntegracaoOut]


class MarketplaceSyncOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recebidos: int
    processados: int
    duplicados: int
    retry: int
    dlq: int
    reconhecidos: int


def _contexto(
    request: Request,
    session: Session,
    *,
    auth_runtime: AuthSessionRuntime,
):
    identidade = obter_identidade_operacional(
        request,
        session,
        auth_runtime=auth_runtime,
    )
    if identidade.modo != "session":
        raise CredenciaisInvalidas("sessao_web_obrigatoria")
    if Permissao.PEDIDO_VISUALIZAR not in identidade.identidade.permissoes:
        raise PermissionError("seguranca.pedido_visualizar_exigido")
    return identidade.identidade.contexto(
        origem="marketplaces_web_v1",
        correlation_id=request.headers.get("x-correlation-id") or None,
    )


def _erro_http(exc: Exception) -> JSONResponse:
    if isinstance(exc, CredenciaisInvalidas):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"erro": exc.codigo},
        )
    if isinstance(exc, (ErroSeguranca, PermissionError)):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"erro": str(getattr(exc, "codigo", str(exc)))},
        )
    if isinstance(exc, ErroMarketplaceTransitorio):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"erro": str(exc)},
        )
    if isinstance(exc, ErroMarketplace):
        codigo = str(exc)
        http_status = (
            status.HTTP_404_NOT_FOUND
            if codigo == "integracao_marketplace_indisponivel"
            else status.HTTP_409_CONFLICT
            if codigo in {"marketplace_nao_homologado", "integracao_inativa"}
            else status.HTTP_400_BAD_REQUEST
        )
        return JSONResponse(status_code=http_status, content={"erro": codigo})
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"erro": "marketplace_indisponivel"},
    )


def build_marketplaces_web_router(
    *,
    session_factory: SessionFactory,
    auth_runtime: AuthSessionRuntime,
    master_key: str | None = None,
) -> APIRouter:
    router = APIRouter(
        prefix="/v1/marketplaces",
        tags=["central-pedidos-marketplaces"],
    )
    app = AplicacaoMarketplacesWebV1(session_factory, master_key=master_key)

    @router.get("", response_model=MarketplaceIntegracoesOut)
    def listar(request: Request) -> MarketplaceIntegracoesOut | JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            itens = app.listar(contexto)
            return MarketplaceIntegracoesOut(
                integracoes=[
                    MarketplaceIntegracaoOut(
                        configuracao_id=item.configuracao_id,
                        plataforma=item.plataforma,
                        conta_externa=item.conta_externa,
                        ambiente=item.ambiente,
                        habilitada=item.habilitada,
                        homologada=item.homologada,
                        evidencia_homologacao_ref=item.evidencia_homologacao_ref,
                        pedidos_sincronizados=item.pedidos_sincronizados,
                        pronta_para_sincronizar=item.pronta_para_sincronizar,
                    )
                    for item in itens
                ]
            )
        except Exception as exc:  # noqa: BLE001 - boundary fail-closed
            return _erro_http(exc)

    @router.post(
        "/{configuracao_id}/sincronizar",
        response_model=MarketplaceSyncOut,
    )
    def sincronizar(
        configuracao_id: str,
        request: Request,
        limite: int = Query(default=100, ge=1, le=100),
    ) -> MarketplaceSyncOut | JSONResponse:
        try:
            with session_factory() as session:
                identidade = obter_identidade_operacional(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
                if identidade.modo != "session":
                    raise CredenciaisInvalidas("sessao_web_obrigatoria")
                if (
                    Permissao.INTEGRACAO_GERENCIAR
                    not in identidade.identidade.permissoes
                ):
                    raise PermissionError(
                        "seguranca.integracao_gerenciar_exigido"
                    )
                _, elevado, _ = auth_runtime.admin_status(request)
                if not elevado:
                    raise PermissionError("seguranca.admin_step_up_exigido")
                contexto = identidade.identidade.contexto(
                    origem="marketplaces_web_v1.sincronizar",
                    correlation_id=request.headers.get("x-correlation-id")
                    or None,
                )
            resultado = app.sincronizar(
                contexto,
                configuracao_id=configuracao_id,
                limite=limite,
            )
            return MarketplaceSyncOut(
                recebidos=resultado.recebidos,
                processados=resultado.processados,
                duplicados=resultado.duplicados,
                retry=resultado.retry,
                dlq=resultado.dlq,
                reconhecidos=resultado.reconhecidos,
            )
        except Exception as exc:  # noqa: BLE001 - boundary fail-closed
            return _erro_http(exc)

    return router
