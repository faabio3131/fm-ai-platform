"""Outbound fiscal bridge from the canonical Kordena sale event to Fiscal V1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol

from core.dominio.pedidos import Pedido
from core.eventos.modelos import EnvelopeMensagem
from core.pagamentos.modelos import MetodoPagamento
from kordena_fiscal.contingency import (
    FiscalOutboxEnqueueResult,
    FiscalOutboxService,
    FiscalOutboxStore,
)
from kordena_fiscal.documents import (
    CanonicalFiscalDocument,
    FiscalLineSnapshot,
    FiscalPaymentSnapshot,
    PaymentMethodKind,
)
from kordena_fiscal.documents.serialization import to_canonical_json
from kordena_fiscal.domain import (
    ExecutionScope,
    FiscalDocumentKind,
    FiscalEnvironment,
    FiscalProfile,
    Money,
    SourceReference,
)


class FiscalOutboundBridgeError(ValueError):
    """Raised when the canonical sale cannot be mapped safely to Fiscal V1."""


class FiscalIssuerResolver(Protocol):
    def resolve(
        self,
        *,
        scope: ExecutionScope,
        issued_at: datetime,
    ) -> FiscalProfile: ...


class FiscalOrderLineResolver(Protocol):
    def resolve(
        self,
        *,
        scope: ExecutionScope,
        pedido: Pedido,
        issued_at: datetime,
    ) -> tuple[FiscalLineSnapshot, ...]: ...


@dataclass(frozen=True)
class FiscalOutboundPreparation:
    document: CanonicalFiscalDocument
    outbox: FiscalOutboxEnqueueResult
    sale_id: str
    pedido_id: str
    source_event_id: str


_PAYMENT_METHODS: dict[MetodoPagamento, PaymentMethodKind] = {
    MetodoPagamento.DINHEIRO: PaymentMethodKind.CASH,
    MetodoPagamento.PIX: PaymentMethodKind.PIX,
    MetodoPagamento.CARTAO_CREDITO: PaymentMethodKind.CREDIT_CARD,
    MetodoPagamento.CARTAO_DEBITO: PaymentMethodKind.DEBIT_CARD,
    MetodoPagamento.VOUCHER: PaymentMethodKind.VOUCHER,
    MetodoPagamento.OUTRO: PaymentMethodKind.OTHER,
    MetodoPagamento.PAGAMENTO_NA_ENTREGA: PaymentMethodKind.OTHER,
    MetodoPagamento.RECEBIMENTO_POSTERIOR: PaymentMethodKind.OTHER,
}


def _required_payload_text(
    event: EnvelopeMensagem,
    key: str,
) -> str:
    value = event.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise FiscalOutboundBridgeError(f"venda.criada missing {key}")
    return value.strip()


def _sale_amount(event: EnvelopeMensagem) -> Decimal:
    raw = _required_payload_text(event, "valor")
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise FiscalOutboundBridgeError("venda.criada valor is invalid") from exc
    if not value.is_finite() or value <= 0:
        raise FiscalOutboundBridgeError("venda.criada valor must be positive")
    return value


def _payment_method(event: EnvelopeMensagem) -> PaymentMethodKind:
    raw = _required_payload_text(event, "metodo")
    try:
        method = MetodoPagamento(raw)
    except ValueError as exc:
        raise FiscalOutboundBridgeError("venda.criada metodo is unsupported") from exc
    return _PAYMENT_METHODS[method]


class KordenaFiscalOutboundBridge:
    """Build one immutable fiscal document and one deduplicated issuance intent."""

    def __init__(
        self,
        *,
        outbox_store: FiscalOutboxStore,
        issuer_resolver: FiscalIssuerResolver,
        line_resolver: FiscalOrderLineResolver,
        environment: FiscalEnvironment = FiscalEnvironment.HOMOLOGATION,
    ) -> None:
        self._outbox = FiscalOutboxService(outbox_store)
        self._issuer_resolver = issuer_resolver
        self._line_resolver = line_resolver
        self._environment = environment

    def process(
        self,
        *,
        event: EnvelopeMensagem,
        pedido: Pedido,
    ) -> FiscalOutboundPreparation:
        if event.event_type != "venda.criada" or event.aggregate_type != "venda":
            raise FiscalOutboundBridgeError(
                "outbound bridge accepts only venda.criada events"
            )

        tenant_id = str(event.tenant_id)
        unit_id = str(event.unidade_id)
        if tenant_id != str(pedido.tenant_id) or unit_id != str(pedido.unidade_id):
            raise FiscalOutboundBridgeError(
                "venda.criada and pedido must share tenant/unidade"
            )

        pedido_id = _required_payload_text(event, "pedido_id")
        if pedido_id != str(pedido.id):
            raise FiscalOutboundBridgeError(
                "venda.criada pedido_id does not match canonical pedido"
            )

        currency = _required_payload_text(event, "moeda").upper()
        if currency != pedido.total.moeda:
            raise FiscalOutboundBridgeError(
                "venda.criada currency does not match canonical pedido"
            )

        sale_amount = _sale_amount(event)
        if sale_amount != pedido.total.valor:
            raise FiscalOutboundBridgeError(
                "venda.criada valor does not match canonical pedido total"
            )

        criterio_versao = event.payload.get("criterio_versao")
        if (
            not isinstance(criterio_versao, int)
            or isinstance(criterio_versao, bool)
            or criterio_versao < 1
        ):
            raise FiscalOutboundBridgeError(
                "venda.criada criterio_versao must be a positive integer"
            )

        scope = ExecutionScope(
            tenant_id=tenant_id,
            unit_id=unit_id,
            environment=self._environment,
            correlation_id=str(event.correlation_id),
        )
        issuer = self._issuer_resolver.resolve(
            scope=scope,
            issued_at=event.occurred_at,
        )
        if issuer.scope.partition_key != scope.partition_key:
            raise FiscalOutboundBridgeError(
                "issuer resolver returned profile outside fiscal scope"
            )

        lines = self._line_resolver.resolve(
            scope=scope,
            pedido=pedido,
            issued_at=event.occurred_at,
        )
        if not lines:
            raise FiscalOutboundBridgeError(
                "fiscal line resolver returned no lines"
            )
        net_amount = sum(
            (line.net_amount.amount for line in lines),
            Decimal(0),
        )
        if net_amount != sale_amount:
            raise FiscalOutboundBridgeError(
                "resolved fiscal lines do not reconcile with canonical sale total"
            )

        sale_id = event.aggregate_id
        document = CanonicalFiscalDocument(
            document_id=f"nfce:{sale_id}",
            scope=scope,
            source=SourceReference("venda", sale_id),
            document_kind=FiscalDocumentKind.NFCE,
            issued_at=event.occurred_at,
            issuer=issuer,
            items=lines,
            payments=(
                FiscalPaymentSnapshot(
                    method=_payment_method(event),
                    amount=Money(sale_amount, currency),
                    provider_reference=(
                        _required_payload_text(event, "pagamento_id")
                        if event.payload.get("pagamento_id")
                        else None
                    ),
                ),
            ),
        )

        payload = to_canonical_json(document).encode("utf-8")
        outbox = self._outbox.enqueue(
            scope=scope,
            operation="nfce.issue",
            deduplication_key=f"venda:{sale_id}:nfce:v1",
            payload=payload,
            created_at=event.occurred_at,
        )
        return FiscalOutboundPreparation(
            document=document,
            outbox=outbox,
            sale_id=sale_id,
            pedido_id=pedido_id,
            source_event_id=str(event.event_id),
        )
