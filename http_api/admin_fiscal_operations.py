"""Administrative HTTP boundary for the fiscal capabilities that were backend-only."""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from application.fiscal_web_operations import AplicacaoFiscalWebOperationsV1
from core.integracoes.modelos import ErroConfiguracaoServico
from core.pagamentos.fiscal_bridge import TipoAjusteObrigacaoCompra
from core.pagamentos.modelos_orm import (
    DecisaoCreditoTributarioORM,
    ObrigacaoCompraFiscalORM,
)
from core.procurement.modelos import ItemPedidoCompra, ItemRecebido
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from core.seguranca.permissoes import Permissao
from http_api.admin_backoffice import contexto_backoffice
from http_api.auth import AuthSessionRuntime
from infra.fiscal.intake_ai import GeminiFiscalIntakeExtractor
from infra.integracoes import FabricaAdaptersExternos
from infra.procurement.modelos_orm import (
    FornecedorORM,
    PedidoCompraORM,
    RecebimentoCompraORM,
    VinculoProdutoFornecedorORM,
)
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore
from kordena_fiscal.domain import (
    ExecutionScope,
    FiscalDomainError,
    FiscalEnvironment,
)
from kordena_fiscal.inbound import FiscalManifestationType
from kordena_fiscal.intake import FiscalIntakeSource
from kordena_fiscal.operations import (
    FiscalOperationsClient,
    FiscalOperationsGateway,
    FiscalQueryRequest,
)
from kordena_fiscal.xml import NfeAccessKey

SessionFactory = Callable[[], Session]
FiscalOperationsGatewayFactory = Callable[[Session], FiscalOperationsGateway]
IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=160),
]


class XmlUploadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: str = "homologation"
    content_base64: str = Field(min_length=4)


class ManifestationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: str = "homologation"
    event_type: FiscalManifestationType
    protocol_reference: str | None = Field(default=None, max_length=512)


class PreliminaryIntakeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: str = "homologation"
    source: str
    media_type: str = Field(min_length=1, max_length=128)
    content_base64: str = Field(min_length=4)


class IntakeReconcileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: str = "homologation"
    official_access_key: str = Field(min_length=44, max_length=44)


class SupplierIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: str = "homologation"
    fornecedor_id: str = Field(min_length=1, max_length=64)
    documento: str = Field(min_length=1, max_length=32)
    nome: str = Field(min_length=1, max_length=256)


class ProductBindingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: str = "homologation"
    fornecedor_id: str = Field(min_length=1, max_length=64)
    codigo_fornecedor: str = Field(min_length=1, max_length=128)
    insumo_id: str = Field(min_length=1, max_length=64)


class PurchaseOrderItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    linha: int = Field(ge=1)
    insumo_id: str = Field(min_length=1, max_length=64)
    codigo_fornecedor: str = Field(min_length=1, max_length=128)
    descricao: str = Field(min_length=1, max_length=512)
    unidade_medida: str = Field(min_length=1, max_length=16)
    quantidade: Decimal = Field(gt=0)
    valor_unitario: Decimal = Field(ge=0)


class PurchaseOrderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: str = "homologation"
    pedido_id: str = Field(min_length=1, max_length=64)
    fornecedor_id: str = Field(min_length=1, max_length=64)
    itens: list[PurchaseOrderItemIn] = Field(min_length=1, max_length=500)
    frete: Decimal = Field(default=Decimal(0), ge=0)
    desconto: Decimal = Field(default=Decimal(0), ge=0)
    total: Decimal = Field(ge=0)


class PurchaseOrderApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: str = "homologation"
    expected_version: int = Field(ge=1)


class ReceiptItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    linha_pedido: int = Field(ge=1)
    linha_fiscal: int = Field(ge=1)
    insumo_id: str = Field(min_length=1, max_length=64)
    quantidade: Decimal = Field(gt=0)
    unidade_medida: str = Field(min_length=1, max_length=16)
    valor_unitario: Decimal = Field(ge=0)
    condicao_aceita: bool = True


class ReceiptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: str = "homologation"
    pedido_id: str = Field(min_length=1, max_length=64)
    access_key: str = Field(min_length=44, max_length=44)
    itens: list[ReceiptItemIn] = Field(min_length=1, max_length=500)


class ReturnReceiptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: str = "production"
    motivo: str = Field(min_length=3, max_length=512)


class FinancialObligationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recebimento_id: str = Field(min_length=1, max_length=64)


class FinancialAdjustmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recebimento_id: str = Field(min_length=1, max_length=64)
    tipo: TipoAjusteObrigacaoCompra
    origem_id: str = Field(min_length=1, max_length=128)
    motivo: str = Field(min_length=3, max_length=512)
    valor: Decimal | None = Field(default=None, gt=0)


class TaxCreditDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recebimento_id: str = Field(min_length=1, max_length=64)
    tributo: str = Field(min_length=1, max_length=32)
    base_calculo: Decimal = Field(ge=0)
    valor_destacado: Decimal = Field(ge=0)
    cfop: str = Field(min_length=1, max_length=16)
    cst: str = Field(min_length=1, max_length=16)
    regra_id: str | None = Field(default=None, max_length=128)
    regra_versao: int | None = Field(default=None, ge=1)
    aliquota_credito: Decimal | None = Field(default=None, ge=0, le=1)
    cfops_elegiveis: list[str] = Field(default_factory=list)
    csts_elegiveis: list[str] = Field(default_factory=list)
    vigente_desde: date | None = None
    vigente_ate: date | None = None


def _environment(value: str) -> FiscalEnvironment:
    aliases = {
        "homologation": FiscalEnvironment.HOMOLOGATION,
        "homologacao": FiscalEnvironment.HOMOLOGATION,
        "production": FiscalEnvironment.PRODUCTION,
        "producao": FiscalEnvironment.PRODUCTION,
    }
    try:
        return aliases[value.strip().casefold()]
    except KeyError as exc:
        raise ValueError("fiscal.ambiente_invalido") from exc


def _content(value: str) -> bytes:
    try:
        content = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("fiscal.conteudo_base64_invalido") from exc
    if not content:
        raise ValueError("fiscal.conteudo_vazio")
    if len(content) > 10 * 1024 * 1024:
        raise ValueError("fiscal.conteudo_excede_10_mib")
    return content


def _error(exc: Exception) -> JSONResponse:
    if isinstance(exc, CredenciaisInvalidas):
        return JSONResponse(status_code=401, content={"erro": "credenciais_invalidas"})
    if isinstance(exc, (ErroSeguranca, PermissionError)):
        return JSONResponse(
            status_code=403,
            content={"erro": str(getattr(exc, "codigo", str(exc)))},
        )
    if isinstance(exc, ErroConfiguracaoServico):
        return JSONResponse(
            status_code=503,
            content={"erro": "fiscal.ia_nao_configurada"},
        )
    if isinstance(exc, (ValueError, TypeError, FiscalDomainError)):
        return JSONResponse(
            status_code=400,
            content={"erro": str(exc) or "fiscal.parametro_invalido"},
        )
    return JSONResponse(
        status_code=503,
        content={"erro": "fiscal.operacao_web_indisponivel"},
    )


def _context(
    request: Request,
    auth_runtime: AuthSessionRuntime,
    permission: Permissao,
    *,
    origin: str,
):
    contexto = contexto_backoffice(
        request,
        auth_runtime=auth_runtime,
        origem=origin,
    )
    if permission not in contexto.permissoes:
        raise PermissionError(f"seguranca.permissao_exigida:{permission.value}")
    return contexto


def _scope(contexto: Any, environment: FiscalEnvironment, suffix: str) -> ExecutionScope:
    return ExecutionScope(
        contexto.tenant_id,
        contexto.unidade_id,
        environment,
        f"{contexto.correlation_id}:{suffix}",
    )


def build_admin_fiscal_operations_router(
    *,
    session_factory: SessionFactory,
    auth_runtime: AuthSessionRuntime,
    operations_gateway_factory: FiscalOperationsGatewayFactory | None = None,
    intake_extractor_factory: Callable[[Any], GeminiFiscalIntakeExtractor] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1/admin/fiscal", tags=["admin-fiscal-operations"])
    app = AplicacaoFiscalWebOperationsV1(session_factory)

    def extractor(contexto: Any) -> GeminiFiscalIntakeExtractor:
        if intake_extractor_factory is not None:
            return intake_extractor_factory(contexto)
        with session_factory() as session:
            vault = EncryptedSQLAlchemySecretStore(session)
            adapter = FabricaAdaptersExternos(
                session=session,
                secret_store=vault,
            ).gemini(
                contexto=contexto,
                configuracao_id="ia.generativa--gemini",
            )
        return GeminiFiscalIntakeExtractor(
            lambda *, contents: adapter.gerar(contents)
        )

    @router.post("/documents/{access_key}/query", response_model=None)
    def query_document(
        access_key: str,
        request: Request,
        environment: Annotated[str, Query()] = "homologation",
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _context(
                request,
                auth_runtime,
                Permissao.FISCAL_VISUALIZAR,
                origin="admin_fiscal_operations.query",
            )
            if operations_gateway_factory is None:
                raise RuntimeError("fiscal.gateway_nao_configurado")
            env = _environment(environment)
            scope = _scope(contexto, env, "provider-query")
            with session_factory() as session:
                result = FiscalOperationsClient(
                    operations_gateway_factory(session)
                ).query(
                    FiscalQueryRequest(
                        scope=scope,
                        access_key=NfeAccessKey(access_key),
                    )
                )
            return {
                "status": result.status.value,
                "access_key": result.access_key.value,
                "provider": result.provider.provider_name,
                "provider_request_id": result.provider_request_id,
                "protocol_reference": result.protocol_reference,
            }
        except RuntimeError as exc:
            if str(exc) == "fiscal.gateway_nao_configurado":
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={"erro": str(exc)},
                )
            return _error(exc)
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    @router.post("/inbound/xml", status_code=201, response_model=None)
    def ingest_xml(
        payload: XmlUploadIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _context(
                request,
                auth_runtime,
                Permissao.FISCAL_COMPRAS_RECEBER,
                origin="admin_fiscal_operations.xml",
            )
            document, created = app.ingest_official_xml(
                contexto=contexto,
                environment=_environment(payload.environment),
                xml_content=_content(payload.content_base64),
            )
            return {
                "created": created,
                "inbound_id": document.inbound_id,
                "access_key": document.access_key.value,
                "issuer_document": document.issuer_document.value,
                "issuer_name": document.issuer_name,
                "status": document.status.value,
                "source": document.source.value,
                "items": len(document.items),
            }
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    @router.post("/inbound/{access_key}/manifest", response_model=None)
    def manifest(
        access_key: str,
        payload: ManifestationIn,
        request: Request,
        idempotency_key: IdempotencyHeader,
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _context(
                request,
                auth_runtime,
                Permissao.FISCAL_MANIFESTAR,
                origin="admin_fiscal_operations.manifest",
            )
            created = app.manifest(
                contexto=contexto,
                environment=_environment(payload.environment),
                access_key=access_key,
                event_type=payload.event_type,
                idempotency_key=idempotency_key,
                protocol_reference=payload.protocol_reference,
            )
            return {
                "recorded": created,
                "access_key": access_key,
                "event_type": payload.event_type.value,
                "external_submission": False,
            }
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    @router.post("/intake/preliminary", status_code=201, response_model=None)
    def preliminary_intake(
        payload: PreliminaryIntakeIn,
        request: Request,
        idempotency_key: IdempotencyHeader,
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _context(
                request,
                auth_runtime,
                Permissao.FISCAL_COMPRAS_RECEBER,
                origin="admin_fiscal_operations.intake",
            )
            source_value = payload.source.strip().casefold()
            source = {
                "pdf": FiscalIntakeSource.PDF,
                "image": FiscalIntakeSource.IMAGE,
                "camera": FiscalIntakeSource.CAMERA,
                "imagem": FiscalIntakeSource.IMAGE,
            }.get(source_value)
            if source is None:
                raise ValueError("fiscal.intake_source_invalido")
            capture, created = app.ingest_preliminary(
                contexto=contexto,
                environment=_environment(payload.environment),
                source=source,
                media_type=payload.media_type,
                content=_content(payload.content_base64),
                idempotency_key=idempotency_key,
                extractor=extractor(contexto),
            )
            return {
                "created": created,
                "capture_id": capture.capture_id,
                "status": capture.status.value,
                "source": capture.source.value,
                "authority": capture.authority.value,
                "media_type": capture.media_type,
                "confidence": (
                    str(capture.extraction.confidence)
                    if capture.extraction is not None
                    else None
                ),
                "items": (
                    len(capture.extraction.items)
                    if capture.extraction is not None
                    else 0
                ),
                "last_error_code": capture.last_error_code,
            }
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    @router.post("/intake/{capture_id}/reconcile", response_model=None)
    def reconcile_intake(
        capture_id: str,
        payload: IntakeReconcileIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _context(
                request,
                auth_runtime,
                Permissao.FISCAL_COMPRAS_RECEBER,
                origin="admin_fiscal_operations.intake_reconcile",
            )
            capture = app.reconcile_intake(
                contexto=contexto,
                environment=_environment(payload.environment),
                capture_id=capture_id,
                official_access_key=payload.official_access_key,
            )
            reconciliation = capture.reconciliation
            return {
                "capture_id": capture.capture_id,
                "status": capture.status.value,
                "reconciliation": (
                    None
                    if reconciliation is None
                    else {
                        "status": reconciliation.status.value,
                        "official_access_key": reconciliation.official_access_key.value,
                        "issues": [item.value for item in reconciliation.issues],
                        "reconciled_at": reconciliation.reconciled_at.isoformat(),
                    }
                ),
            }
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    @router.get("/procurement", response_model=None)
    def procurement_workspace(
        request: Request,
        environment: Annotated[str, Query()] = "homologation",
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _context(
                request,
                auth_runtime,
                Permissao.FISCAL_COMPRAS_VISUALIZAR,
                origin="admin_fiscal_operations.procurement",
            )
            env = _environment(environment)
            with session_factory() as session:
                common = (
                    lambda model: (
                        model.tenant_id == contexto.tenant_id,
                        model.unit_id == contexto.unidade_id,
                        model.environment == env.value,
                    )
                )
                suppliers = session.scalars(
                    select(FornecedorORM)
                    .where(*common(FornecedorORM))
                    .order_by(FornecedorORM.nome)
                    .limit(limit)
                ).all()
                bindings = session.scalars(
                    select(VinculoProdutoFornecedorORM)
                    .where(*common(VinculoProdutoFornecedorORM))
                    .order_by(
                        VinculoProdutoFornecedorORM.fornecedor_id,
                        VinculoProdutoFornecedorORM.codigo_fornecedor,
                    )
                    .limit(limit)
                ).all()
                orders = session.scalars(
                    select(PedidoCompraORM)
                    .where(*common(PedidoCompraORM))
                    .order_by(PedidoCompraORM.atualizado_em.desc())
                    .limit(limit)
                ).all()
                receipts = session.scalars(
                    select(RecebimentoCompraORM)
                    .where(*common(RecebimentoCompraORM))
                    .order_by(RecebimentoCompraORM.confirmado_em.desc())
                    .limit(limit)
                ).all()
                obligations = session.scalars(
                    select(ObrigacaoCompraFiscalORM)
                    .where(
                        ObrigacaoCompraFiscalORM.tenant_id == contexto.tenant_id,
                        ObrigacaoCompraFiscalORM.unidade_id == contexto.unidade_id,
                        ObrigacaoCompraFiscalORM.environment == env.value,
                    )
                    .order_by(ObrigacaoCompraFiscalORM.criado_em.desc())
                    .limit(limit)
                ).all()
                decisions = session.scalars(
                    select(DecisaoCreditoTributarioORM)
                    .where(
                        DecisaoCreditoTributarioORM.tenant_id == contexto.tenant_id,
                        DecisaoCreditoTributarioORM.unidade_id == contexto.unidade_id,
                        DecisaoCreditoTributarioORM.environment == env.value,
                    )
                    .order_by(DecisaoCreditoTributarioORM.decidido_em.desc())
                    .limit(limit)
                ).all()

            return {
                "environment": env.value,
                "suppliers": [
                    {
                        "fornecedor_id": row.fornecedor_id,
                        "documento": row.documento,
                        "nome": row.nome,
                        "ativo": row.ativo,
                        "versao": row.versao,
                    }
                    for row in suppliers
                ],
                "bindings": [
                    {
                        "fornecedor_id": row.fornecedor_id,
                        "codigo_fornecedor": row.codigo_fornecedor,
                        "insumo_id": row.insumo_id,
                    }
                    for row in bindings
                ],
                "orders": [
                    {
                        "pedido_id": row.pedido_id,
                        "fornecedor_id": row.fornecedor_id,
                        "status": row.status,
                        "payload": json.loads(row.payload_json),
                        "versao": row.versao,
                        "updated_at": row.atualizado_em.isoformat(),
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
                        "payload": json.loads(row.payload_json),
                        "versao": row.versao,
                        "confirmed_at": row.confirmado_em.isoformat(),
                    }
                    for row in receipts
                ],
                "obligations": [
                    {
                        "obrigacao_id": row.obrigacao_id,
                        "pedido_id": row.pedido_id,
                        "recebimento_id": row.recebimento_id,
                        "status": row.status,
                        "reconciliation": row.reconciliacao,
                        "original_value": str(row.valor_original),
                        "adjusted_value": str(row.valor_ajustado),
                        "balance": str(row.saldo),
                        "currency": row.moeda,
                        "version": row.versao,
                    }
                    for row in obligations
                ],
                "tax_decisions": [
                    {
                        "decisao_id": row.decisao_id,
                        "obrigacao_id": row.obrigacao_id,
                        "tributo": row.tributo,
                        "resultado": row.resultado,
                        "base_calculo": str(row.base_calculo),
                        "valor_destacado": str(row.valor_destacado),
                        "valor_credito": str(row.valor_credito),
                        "cfop": row.cfop,
                        "cst": row.cst,
                        "regra_id": row.regra_id,
                        "regra_versao": row.regra_versao,
                    }
                    for row in decisions
                ],
            }
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    @router.post("/procurement/suppliers", status_code=201, response_model=None)
    def create_supplier(
        payload: SupplierIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _context(
                request,
                auth_runtime,
                Permissao.COMPRA_APROVAR,
                origin="admin_fiscal_operations.supplier",
            )
            item = app.cadastrar_fornecedor(
                contexto=contexto,
                environment=_environment(payload.environment),
                fornecedor_id=payload.fornecedor_id,
                documento=payload.documento,
                nome=payload.nome,
            )
            return {
                "fornecedor_id": item.fornecedor_id,
                "documento": item.documento,
                "nome": item.nome,
                "ativo": item.ativo,
                "versao": item.versao,
            }
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    @router.post("/procurement/bindings", status_code=201, response_model=None)
    def create_binding(
        payload: ProductBindingIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _context(
                request,
                auth_runtime,
                Permissao.COMPRA_APROVAR,
                origin="admin_fiscal_operations.binding",
            )
            item = app.vincular_produto(
                contexto=contexto,
                environment=_environment(payload.environment),
                fornecedor_id=payload.fornecedor_id,
                codigo_fornecedor=payload.codigo_fornecedor,
                insumo_id=payload.insumo_id,
            )
            return {
                "fornecedor_id": item.fornecedor_id,
                "codigo_fornecedor": item.codigo_fornecedor,
                "insumo_id": item.insumo_id,
            }
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    @router.post("/procurement/orders", status_code=201, response_model=None)
    def create_order(
        payload: PurchaseOrderIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _context(
                request,
                auth_runtime,
                Permissao.COMPRA_APROVAR,
                origin="admin_fiscal_operations.order",
            )
            order = app.criar_pedido(
                contexto=contexto,
                environment=_environment(payload.environment),
                pedido_id=payload.pedido_id,
                fornecedor_id=payload.fornecedor_id,
                itens=tuple(
                    ItemPedidoCompra(
                        item.linha,
                        item.insumo_id,
                        item.codigo_fornecedor,
                        item.descricao,
                        item.unidade_medida,
                        item.quantidade,
                        item.valor_unitario,
                    )
                    for item in payload.itens
                ),
                frete=payload.frete,
                desconto=payload.desconto,
                total=payload.total,
            )
            return {
                "pedido_id": order.pedido_id,
                "status": order.status.value,
                "versao": order.versao,
            }
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    @router.post("/procurement/orders/{pedido_id}/approve", response_model=None)
    def approve_order(
        pedido_id: str,
        payload: PurchaseOrderApproveIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _context(
                request,
                auth_runtime,
                Permissao.COMPRA_APROVAR,
                origin="admin_fiscal_operations.order_approve",
            )
            order = app.aprovar_pedido(
                contexto=contexto,
                environment=_environment(payload.environment),
                pedido_id=pedido_id,
                versao_esperada=payload.expected_version,
            )
            return {
                "pedido_id": order.pedido_id,
                "status": order.status.value,
                "versao": order.versao,
            }
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    @router.post("/procurement/receipts", status_code=201, response_model=None)
    def receive(
        payload: ReceiptIn,
        request: Request,
        idempotency_key: IdempotencyHeader,
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _context(
                request,
                auth_runtime,
                Permissao.FISCAL_COMPRAS_RECEBER,
                origin="admin_fiscal_operations.receipt",
            )
            result = app.receber(
                contexto=contexto,
                environment=_environment(payload.environment),
                pedido_id=payload.pedido_id,
                access_key=payload.access_key,
                itens=tuple(
                    ItemRecebido(
                        item.linha_pedido,
                        item.linha_fiscal,
                        item.insumo_id,
                        item.quantidade,
                        item.unidade_medida,
                        item.valor_unitario,
                        item.condicao_aceita,
                    )
                    for item in payload.itens
                ),
                idempotency_key=idempotency_key,
            )
            receipt = result.recebimento
            return {
                "recebimento_id": receipt.recebimento_id,
                "pedido_id": receipt.pedido_id,
                "status": receipt.status.value,
                "divergencias": [
                    {
                        "tipo": item.tipo.value,
                        "linha_pedido": item.linha_pedido,
                        "esperado": item.esperado,
                        "encontrado": item.encontrado,
                    }
                    for item in receipt.divergencias
                ],
                "stock_movements": len(result.movimentos_estoque),
                "idempotent": result.idempotente,
            }
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    @router.post("/procurement/receipts/{recebimento_id}/return", response_model=None)
    def return_receipt(
        recebimento_id: str,
        payload: ReturnReceiptIn,
        request: Request,
        idempotency_key: IdempotencyHeader,
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _context(
                request,
                auth_runtime,
                Permissao.FISCAL_COMPRAS_RECEBER,
                origin="admin_fiscal_operations.return",
            )
            movements = app.devolver(
                contexto=contexto,
                environment=_environment(payload.environment),
                recebimento_id=recebimento_id,
                idempotency_key=idempotency_key,
                motivo=payload.motivo,
            )
            return {
                "recebimento_id": recebimento_id,
                "stock_movements": len(movements),
            }
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    @router.post("/financial/obligations", status_code=201, response_model=None)
    def create_obligation(
        payload: FinancialObligationIn,
        request: Request,
        idempotency_key: IdempotencyHeader,
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _context(
                request,
                auth_runtime,
                Permissao.FINANCEIRO_COMPRAS_REGISTRAR,
                origin="admin_fiscal_operations.financial",
            )
            result = app.criar_obrigacao(
                contexto=contexto,
                recebimento_id=payload.recebimento_id,
                idempotency_key=idempotency_key,
            )
            item = result.obrigacao
            return {
                "obrigacao_id": item.obrigacao_id,
                "recebimento_id": item.recebimento_id,
                "status": item.status.value,
                "reconciliation": item.reconciliacao.value,
                "original_value": str(item.valor_original),
                "balance": str(item.saldo),
                "idempotent": result.idempotente,
            }
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    @router.post("/financial/adjustments", response_model=None)
    def adjust_obligation(
        payload: FinancialAdjustmentIn,
        request: Request,
        idempotency_key: IdempotencyHeader,
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _context(
                request,
                auth_runtime,
                Permissao.FINANCEIRO_COMPRAS_REGISTRAR,
                origin="admin_fiscal_operations.adjustment",
            )
            item = app.ajustar_obrigacao(
                contexto=contexto,
                recebimento_id=payload.recebimento_id,
                tipo=payload.tipo,
                origem_id=payload.origem_id,
                motivo=payload.motivo,
                idempotency_key=idempotency_key,
                valor=payload.valor,
            )
            return {
                "obrigacao_id": item.obrigacao_id,
                "status": item.status.value,
                "adjusted_value": str(item.valor_ajustado),
                "balance": str(item.saldo),
                "version": item.versao,
            }
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    @router.post("/financial/tax-credit-decisions", response_model=None)
    def tax_credit(
        payload: TaxCreditDecisionIn,
        request: Request,
        idempotency_key: IdempotencyHeader,
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = _context(
                request,
                auth_runtime,
                Permissao.FINANCEIRO_TRIBUTOS_DECIDIR,
                origin="admin_fiscal_operations.tax_credit",
            )
            item = app.decidir_credito(
                contexto=contexto,
                recebimento_id=payload.recebimento_id,
                tributo=payload.tributo,
                base_calculo=payload.base_calculo,
                valor_destacado=payload.valor_destacado,
                cfop=payload.cfop,
                cst=payload.cst,
                idempotency_key=idempotency_key,
                regra_id=payload.regra_id,
                regra_versao=payload.regra_versao,
                aliquota_credito=payload.aliquota_credito,
                cfops_elegiveis=frozenset(payload.cfops_elegiveis),
                csts_elegiveis=frozenset(payload.csts_elegiveis),
                vigente_desde=payload.vigente_desde,
                vigente_ate=payload.vigente_ate,
            )
            return {
                "decisao_id": item.decisao_id,
                "obrigacao_id": item.obrigacao_id,
                "resultado": item.resultado.value,
                "valor_credito": str(item.valor_credito),
                "regra_id": item.regra_id,
                "regra_versao": item.regra_versao,
                "motivo": item.motivo,
            }
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    return router
