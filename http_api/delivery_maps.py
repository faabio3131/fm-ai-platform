"""Fronteira HTTP fina para o roteamento Google Maps do Delivery Próprio."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from application.delivery_maps_comercial import (
    RotaDeliveryGoogleMaps,
    calcular_rota_delivery_google_maps_comercial,
)
from core.delivery.erros import ErroDelivery
from core.integracoes.google_maps import ErroGoogleMaps
from core.integracoes.modelos import ErroConfiguracaoServico
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from http_api.auth import AuthSessionRuntime
from http_api.operational_auth import obter_identidade_operacional

SessionFactory = Callable[[], Session]
RouteResolver = Callable[..., RotaDeliveryGoogleMaps]


def _identidade(
    request: Request,
    session: Session,
    *,
    auth_runtime: AuthSessionRuntime | None,
) -> IdentidadeUsuario:
    return obter_identidade_operacional(
        request,
        session,
        auth_runtime=auth_runtime,
    ).identidade


def _erro_http(exc: Exception) -> JSONResponse:
    if isinstance(exc, CredenciaisInvalidas):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"erro": "credenciais_invalidas"},
        )
    if isinstance(exc, (ErroSeguranca, PermissionError)):
        codigo = getattr(exc, "codigo", str(exc) or "permissao_negada")
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"erro": str(codigo)},
        )
    if isinstance(exc, ErroDelivery):
        codigo = str(getattr(exc, "codigo", str(exc) or "delivery_invalido"))
        http_status = (
            status.HTTP_404_NOT_FOUND
            if "indisponivel" in codigo
            else status.HTTP_400_BAD_REQUEST
        )
        return JSONResponse(status_code=http_status, content={"erro": codigo})
    if isinstance(exc, ValueError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"erro": "rota_delivery_invalida"},
        )
    if isinstance(
        exc,
        (ErroConfiguracaoServico, ErroGoogleMaps, RuntimeError),
    ):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"erro": "google_maps_indisponivel"},
        )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"erro": "google_maps_indisponivel"},
    )


def _rota_out(rota: RotaDeliveryGoogleMaps) -> dict[str, Any]:
    return {
        "cliente_id": rota.cliente_id,
        "provedor": rota.provedor,
        "origem_endereco": rota.origem_endereco,
        "destino_endereco": rota.destino_endereco,
        "distancia_metros": rota.distancia_metros,
        "distancia_km": rota.distancia_km,
        "eta_minutos": rota.eta_minutos,
        "polyline_codificada": rota.polyline_codificada,
        "origem": {
            "latitude": rota.origem_latitude,
            "longitude": rota.origem_longitude,
            "versao": rota.origem_versao,
        },
        "destino": {
            "latitude": rota.destino_latitude,
            "longitude": rota.destino_longitude,
            "endereco_ref": rota.endereco_ref,
        },
    }


def build_delivery_maps_router(
    *,
    session_factory: SessionFactory,
    auth_runtime: AuthSessionRuntime | None = None,
    route_resolver: RouteResolver | None = None,
) -> APIRouter:
    resolver = route_resolver or calcular_rota_delivery_google_maps_comercial
    router = APIRouter(prefix="/v1/delivery", tags=["delivery", "google-maps"])

    @router.get(
        "/clientes/{cliente_id}/rota",
        response_model=dict[str, Any],
    )
    def obter_rota(
        cliente_id: str,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            with session_factory() as session:
                identidade = _identidade(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
                rota = resolver(
                    identidade=identidade,
                    cliente_id=cliente_id,
                    session=session,
                )
                return _rota_out(rota)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    return router
