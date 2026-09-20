"""Functional administrative fiscal Web boundary for WP-031J.

Read models come directly from the canonical fiscal/procurement/financial authorities.
No fiscal state or secret material is duplicated here.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.pagamentos.modelos_orm import ObrigacaoCompraFiscalORM
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from core.seguranca.permissoes import Permissao
from http_api.auth import AuthSessionRuntime
from infra.fiscal.modelos_orm import (
    FiscalArchiveORM,
    FiscalDocumentProjectionORM,
    FiscalOutboxORM,
    FiscalProductBindingORM,
    FiscalInboundDocumentORM,
    FiscalIntakeCaptureORM,
    FiscalManifestationORM,
)
from infra.integracoes.modelos_orm import ServicoExternoConfigORM
from infra.legacy_product_scope import ErroEscopoLojaLegada, listar_produtos_legados
from infra.procurement.modelos_orm import PedidoCompraORM, RecebimentoCompraORM
from kordena_fiscal.domain import ElectronicInvoiceModel, FiscalEnvironment
from kordena_fiscal.operations import (
    CancellationRequest,
    FiscalOperationsClient,
    FiscalOperationsGateway,
    InutilizationRequest,
)
from kordena_fiscal.xml import NfeAccessKey

SessionFactory = Callable[[], Session]
FiscalOperationsGatewayFactory = Callable[[Session], FiscalOperationsGateway]


class FiscalCancelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: str = "homologation"
    authorization_protocol: str = Field(min_length=1, max_length=512)
    justification: str = Field(min_length=15, max_length=255)


class FiscalInutilizationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: str = "homologation"
    model: int
    series: int
    first_number: int
    last_number: int
    justification: str = Field(min_length=15, max_length=255)


def _erro(http_status: int, codigo: str) -> JSONResponse:
    return JSONResponse(status_code=http_status, content={"erro": codigo})


def _tratar_erro(exc: Exception) -> JSONResponse:
    if isinstance(exc, CredenciaisInvalidas):
        return _erro(status.HTTP_401_UNAUTHORIZED, "credenciais_invalidas")
    if isinstance(exc, (ErroSeguranca, PermissionError)):
        return _erro(
            status.HTTP_403_FORBIDDEN,
            str(getattr(exc, "codigo", str(exc) or "seguranca.permissao_insuficiente")),
        )
    if isinstance(exc, (ValueError, TypeError)):
        return _erro(status.HTTP_400_BAD_REQUEST, str(exc) or "fiscal.parametro_invalido")
    return _erro(status.HTTP_503_SERVICE_UNAVAILABLE, "fiscal.web_indisponivel")


def _environment(value: str) -> FiscalEnvironment:
    normalized = value.strip().casefold()
    aliases = {
        "homologation": FiscalEnvironment.HOMOLOGATION,
        "homologacao": FiscalEnvironment.HOMOLOGATION,
        "production": FiscalEnvironment.PRODUCTION,
        "producao": FiscalEnvironment.PRODUCTION,
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValueError("fiscal.ambiente_invalido") from exc


def _dt(value: object | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        return str(value)
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _identity(
    request: Request,
    auth_runtime: AuthSessionRuntime,
    *,
    permission: Permissao,
    require_step_up: bool = True,
):
    identidade = auth_runtime.resolver_identidade(request)
    if identidade is None:
        raise CredenciaisInvalidas("credenciais invalidas")
    if Permissao.ADMIN_ACESSAR not in identidade.permissoes:
        raise PermissionError("seguranca.admin_acesso_exigido")
    if permission not in identidade.permissoes:
        raise PermissionError(f"seguranca.permissao_exigida:{permission.value}")
    if require_step_up:
        _, elevated, _ = auth_runtime.admin_status(request)
        if not elevated:
            raise PermissionError("seguranca.admin_step_up_exigido")
    return identidade


def _scope_filters(model: Any, identidade: Any, environment: FiscalEnvironment) -> tuple[Any, ...]:
    tenant_column = getattr(model, "tenant_id")
    unit_column = getattr(model, "unit_id", getattr(model, "unidade_id", None))
    if unit_column is None:
        raise RuntimeError("fiscal model without unit scope")
    filters: list[Any] = [
        tenant_column == identidade.tenant_id,
        unit_column == identidade.unidade_id,
    ]
    if hasattr(model, "environment"):
        filters.append(getattr(model, "environment") == environment.value)
    return tuple(filters)


def build_admin_fiscal_router(
    *,
    session_factory: SessionFactory,
    auth_runtime: AuthSessionRuntime,
    operations_gateway_factory: FiscalOperationsGatewayFactory | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1/admin/fiscal", tags=["admin-fiscal"])

    @router.get("/workspace", response_model=None)
    def workspace(
        request: Request,
        environment: Annotated[str, Query()] = "homologation",
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> dict[str, Any] | JSONResponse:
        try:
            identidade = _identity(
                request,
                auth_runtime,
                permission=Permissao.FISCAL_VISUALIZAR,
            )
            env = _environment(environment)
            with session_factory() as session:
                projections = session.scalars(
                    select(FiscalDocumentProjectionORM)
                    .where(*_scope_filters(FiscalDocumentProjectionORM, identidade, env))
                    .order_by(FiscalDocumentProjectionORM.updated_at.desc())
                    .limit(limit)
                ).all()
                inbound = session.scalars(
                    select(FiscalInboundDocumentORM)
                    .where(*_scope_filters(FiscalInboundDocumentORM, identidade, env))
                    .order_by(FiscalInboundDocumentORM.discovered_at.desc())
                    .limit(limit)
                ).all()
                manifestations = session.scalars(
                    select(FiscalManifestationORM)
                    .where(*_scope_filters(FiscalManifestationORM, identidade, env))
                    .order_by(FiscalManifestationORM.occurred_at.desc())
                    .limit(limit)
                ).all()
                intake = session.scalars(
                    select(FiscalIntakeCaptureORM)
                    .where(*_scope_filters(FiscalIntakeCaptureORM, identidade, env))
                    .order_by(FiscalIntakeCaptureORM.updated_at.desc())
                    .limit(limit)
                ).all()
                orders = session.scalars(
                    select(PedidoCompraORM)
                    .where(*_scope_filters(PedidoCompraORM, identidade, env))
                    .order_by(PedidoCompraORM.atualizado_em.desc())
                    .limit(limit)
                ).all()
                receipts = session.scalars(
                    select(RecebimentoCompraORM)
                    .where(*_scope_filters(RecebimentoCompraORM, identidade, env))
                    .order_by(RecebimentoCompraORM.confirmado_em.desc())
                    .limit(limit)
                ).all()
                obligations = session.scalars(
                    select(ObrigacaoCompraFiscalORM)
                    .where(*_scope_filters(ObrigacaoCompraFiscalORM, identidade, env))
                    .order_by(ObrigacaoCompraFiscalORM.criado_em.desc())
                    .limit(limit)
                ).all()
                archive_count = session.scalar(
                    select(func.count())
                    .select_from(FiscalArchiveORM)
                    .where(*_scope_filters(FiscalArchiveORM, identidade, env))
                ) or 0
                integration = session.scalar(
                    select(ServicoExternoConfigORM).where(
                        ServicoExternoConfigORM.tenant_id == identidade.tenant_id,
                        ServicoExternoConfigORM.unidade_id == identidade.unidade_id,
                        ServicoExternoConfigORM.servico == "fiscal.documentos",
                    )
                )
                contingency = session.scalars(
                    select(FiscalOutboxORM)
                    .where(
                        *_scope_filters(FiscalOutboxORM, identidade, env),
                        FiscalOutboxORM.status.in_(
                            ("pending", "in_flight", "retry_wait", "dead_letter")
                        ),
                    )
                    .order_by(FiscalOutboxORM.available_at.desc())
                    .limit(limit)
                ).all()
                fiscal_product_ids = set(
                    session.scalars(
                        select(FiscalProductBindingORM.product_id).where(
                            *_scope_filters(
                                FiscalProductBindingORM,
                                identidade,
                                env,
                            )
                        )
                    ).all()
                )
                try:
                    catalog_rows = listar_produtos_legados(
                        session,
                        tenant_id=identidade.tenant_id,
                        unidade_id=identidade.unidade_id,
                    )
                    pending_products_available = True
                    pending_products = [
                        {
                            "product_id": str(row._mapping["id"]),
                            "name": str(row._mapping.get("nome") or ""),
                        }
                        for row in catalog_rows
                        if str(row._mapping["id"]) not in fiscal_product_ids
                    ]
                except ErroEscopoLojaLegada:
                    pending_products_available = False
                    pending_products = []

            return {
                "tenant_id": identidade.tenant_id,
                "unit_id": identidade.unidade_id,
                "environment": env.value,
                "summary": {
                    "outbound_documents": len(projections),
                    "inbound_documents": len(inbound),
                    "manifestations": len(manifestations),
                    "intake_captures": len(intake),
                    "purchase_orders": len(orders),
                    "receipts": len(receipts),
                    "financial_obligations": len(obligations),
                    "archive_entries": int(archive_count),
                    "contingency_entries": len(contingency),
                    "products_pending_fiscal": len(pending_products),
                },
                "outbound": [
                    {
                        "document_id": row.document_id,
                        "document_kind": row.document_kind,
                        "state": row.state,
                        "access_key": row.access_key,
                        "protocol_reference": row.protocol_reference,
                        "rejection_code": row.rejection_code,
                        "rejection_message": row.rejection_message,
                        "updated_at": _dt(row.updated_at),
                    }
                    for row in projections
                ],
                "inbound": [
                    {
                        "inbound_id": row.inbound_id,
                        "access_key": row.access_key,
                        "nsu": row.nsu,
                        "issuer_document": row.issuer_document,
                        "issuer_name": row.issuer_name,
                        "status": row.status,
                        "source": row.source,
                        "discovered_at": _dt(row.discovered_at),
                        "updated_at": _dt(row.updated_at),
                    }
                    for row in inbound
                ],
                "manifestations": [
                    {
                        "manifestation_id": row.manifestation_id,
                        "access_key": row.access_key,
                        "event_type": row.event_type,
                        "protocol_reference": row.protocol_reference,
                        "occurred_at": _dt(row.occurred_at),
                    }
                    for row in manifestations
                ],
                "intake": [
                    {
                        "capture_id": row.capture_id,
                        "source": row.source,
                        "authority": row.authority,
                        "status": row.status,
                        "media_type": row.media_type,
                        "last_error_code": row.last_error_code,
                        "captured_at": _dt(row.captured_at),
                        "updated_at": _dt(row.updated_at),
                    }
                    for row in intake
                ],
                "procurement": {
                    "orders": [
                        {
                            "pedido_id": row.pedido_id,
                            "fornecedor_id": row.fornecedor_id,
                            "status": row.status,
                            "updated_at": _dt(row.atualizado_em),
                        }
                        for row in orders
                    ],
                    "receipts": [
                        {
                            "recebimento_id": row.recebimento_id,
                            "pedido_id": row.pedido_id,
                            "inbound_id": row.inbound_id,
                            "access_key": row.chave_acesso,
                            "status": row.status,
                            "confirmed_at": _dt(row.confirmado_em),
                        }
                        for row in receipts
                    ],
                },
                "financial": [
                    {
                        "obrigacao_id": row.obrigacao_id,
                        "fornecedor_id": row.fornecedor_id,
                        "pedido_id": row.pedido_id,
                        "recebimento_id": row.recebimento_id,
                        "status": row.status,
                        "reconciliation": row.reconciliacao,
                        "original_value": str(row.valor_original),
                        "adjusted_value": str(row.valor_ajustado),
                        "balance": str(row.saldo),
                        "currency": row.moeda,
                        "created_at": _dt(row.criado_em),
                    }
                    for row in obligations
                ],
                "products_pending_fiscal": {
                    "available": pending_products_available,
                    "items": pending_products,
                },
                "contingency": [
                    {
                        "entry_id": row.entry_id,
                        "operation": row.operation,
                        "status": row.status,
                        "attempt_count": row.attempt_count,
                        "available_at": _dt(row.available_at),
                        "last_error": row.last_error,
                    }
                    for row in contingency
                ],
                "configuration": (
                    None
                    if integration is None
                    else {
                        "configuration_id": integration.configuracao_id,
                        "provider": integration.provedor,
                        "environment": integration.ambiente,
                        "enabled": integration.habilitada,
                        "homologated": integration.homologada,
                        "homologation_evidence_reference": integration.evidencia_homologacao_ref,
                        "version": integration.versao,
                        "credential_roles": sorted(
                            dict(integration.finalidades_credenciais).keys()
                        ),
                    }
                ),
                "capabilities": {
                    "configure": Permissao.FISCAL_CONFIGURAR in identidade.permissoes,
                    "certificate": Permissao.FISCAL_CERTIFICADO in identidade.permissoes,
                    "cancel": Permissao.FISCAL_CANCELAR in identidade.permissoes,
                    "inutilize": Permissao.FISCAL_INUTILIZAR in identidade.permissoes,
                    "manifest": Permissao.FISCAL_MANIFESTAR in identidade.permissoes,
                    "purchases_view": Permissao.FISCAL_COMPRAS_VISUALIZAR
                    in identidade.permissoes,
                    "purchases_receive": Permissao.FISCAL_COMPRAS_RECEBER
                    in identidade.permissoes,
                    "archive_view": Permissao.FISCAL_ARCHIVE_VISUALIZAR
                    in identidade.permissoes,
                },
            }
        except Exception as exc:  # noqa: BLE001 - HTTP boundary fail-closed
            return _tratar_erro(exc)

    @router.post("/documents/{access_key}/cancel", response_model=None)
    def cancel_document(
        access_key: str,
        payload: FiscalCancelIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            identidade = _identity(
                request,
                auth_runtime,
                permission=Permissao.FISCAL_CANCELAR,
            )
            if operations_gateway_factory is None:
                return _erro(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "fiscal.gateway_nao_configurado",
                )
            env = _environment(payload.environment)
            scope = __import__("kordena_fiscal.domain", fromlist=["ExecutionScope"]).ExecutionScope(
                identidade.tenant_id,
                identidade.unidade_id,
                env,
                request.headers.get("x-correlation-id") or "admin_fiscal_cancel",
            )
            operation = CancellationRequest.build(
                scope=scope,
                access_key=NfeAccessKey(access_key),
                authorization_protocol=payload.authorization_protocol,
                justification=payload.justification,
            )
            with session_factory() as session:
                result = FiscalOperationsClient(
                    operations_gateway_factory(session)
                ).cancel(operation)
            return {
                "status": result.status.value,
                "access_key": result.access_key.value,
                "request_id": result.request_id,
                "provider": result.provider.provider_name,
                "provider_request_id": result.provider_request_id,
                "event_protocol_reference": result.event_protocol_reference,
                "rejection_code": result.rejection_code,
                "rejection_message": result.rejection_message,
            }
        except Exception as exc:  # noqa: BLE001
            return _tratar_erro(exc)

    @router.post("/inutilizations", response_model=None)
    def inutilize_numbers(
        payload: FiscalInutilizationIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            identidade = _identity(
                request,
                auth_runtime,
                permission=Permissao.FISCAL_INUTILIZAR,
            )
            if operations_gateway_factory is None:
                return _erro(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "fiscal.gateway_nao_configurado",
                )
            env = _environment(payload.environment)
            scope = __import__("kordena_fiscal.domain", fromlist=["ExecutionScope"]).ExecutionScope(
                identidade.tenant_id,
                identidade.unidade_id,
                env,
                request.headers.get("x-correlation-id") or "admin_fiscal_inutilize",
            )
            operation = InutilizationRequest.build(
                scope=scope,
                model=ElectronicInvoiceModel(payload.model),
                series=payload.series,
                first_number=payload.first_number,
                last_number=payload.last_number,
                justification=payload.justification,
            )
            with session_factory() as session:
                result = FiscalOperationsClient(
                    operations_gateway_factory(session)
                ).inutilize(operation)
            return {
                "status": result.status.value,
                "request_id": result.request_id,
                "provider": result.provider.provider_name,
                "provider_request_id": result.provider_request_id,
                "event_protocol_reference": result.event_protocol_reference,
                "rejection_code": result.rejection_code,
                "rejection_message": result.rejection_message,
            }
        except Exception as exc:  # noqa: BLE001
            return _tratar_erro(exc)

    @router.get("/archive", response_model=None)
    def archive(
        request: Request,
        environment: Annotated[str, Query()] = "homologation",
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> dict[str, Any] | JSONResponse:
        try:
            identidade = _identity(
                request,
                auth_runtime,
                permission=Permissao.FISCAL_ARCHIVE_VISUALIZAR,
            )
            env = _environment(environment)
            with session_factory() as session:
                rows = session.scalars(
                    select(FiscalArchiveORM)
                    .where(*_scope_filters(FiscalArchiveORM, identidade, env))
                    .order_by(FiscalArchiveORM.archived_at.desc())
                    .limit(limit)
                ).all()
            return {
                "environment": env.value,
                "entries": [
                    {
                        "entry_id": row.entry_id,
                        "document_reference": row.document_reference,
                        "kind": row.kind,
                        "content_sha256": row.content_sha256,
                        "media_type": row.media_type,
                        "archived_at": _dt(row.archived_at),
                        "retention_policy_id": row.retention_policy_id,
                        "retention_policy_version": row.retention_policy_version,
                        "retain_until": _dt(row.retain_until),
                    }
                    for row in rows
                ],
            }
        except Exception as exc:  # noqa: BLE001
            return _tratar_erro(exc)

    return router
