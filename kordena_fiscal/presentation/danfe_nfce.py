"""Deterministic DANFE NFC-e HTML, QR-code and printer adapter contracts."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from html import escape
from typing import Protocol
from urllib.parse import urlsplit

from kordena_fiscal.documents import CanonicalFiscalDocument, PaymentMethodKind
from kordena_fiscal.domain import (
    ElectronicInvoiceModel,
    FiscalDocumentKind,
    FiscalDomainError,
    FiscalValidationError,
)
from kordena_fiscal.gateway import AuthorizationResult, AuthorizationStatus
from kordena_fiscal.xml import NfeAccessKey


class NfcePrintContractError(FiscalDomainError):
    """Raised when a QR, render or printer adapter violates its public contract."""


class DanfeNfceLayout(StrEnum):
    FULL = "full"
    SUMMARY = "summary"


@dataclass(frozen=True, slots=True)
class NfceQrCodePayload:
    """Opaque HTTPS QR payload produced by a jurisdiction/provider adapter."""

    value: str

    def __post_init__(self) -> None:
        value = self.value.strip()
        if not value:
            raise FiscalValidationError("QR-code payload must not be blank")
        if len(value) > 4096:
            raise FiscalValidationError("QR-code payload exceeds max length 4096")
        parsed = urlsplit(value)
        if parsed.scheme.lower() != "https" or not parsed.netloc:
            raise FiscalValidationError("QR-code payload must be an absolute HTTPS URL")
        if parsed.username is not None or parsed.password is not None:
            raise FiscalValidationError("QR-code payload cannot contain URL credentials")
        if parsed.fragment:
            raise FiscalValidationError("QR-code payload cannot contain a URL fragment")
        object.__setattr__(self, "value", value)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class NfceQrCodeArtifact:
    """Rendered QR image bound cryptographically to one payload."""

    content: bytes
    media_type: str
    payload_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.content, bytes) or not self.content:
            raise FiscalValidationError("QR-code artifact content must be non-empty bytes")
        media_type = self.media_type.strip().lower()
        if media_type not in {"image/svg+xml", "image/png"}:
            raise FiscalValidationError("QR-code artifact media_type must be SVG or PNG")
        digest = self.payload_sha256.strip().lower()
        _require_sha256(digest, "payload_sha256")
        object.__setattr__(self, "media_type", media_type)
        object.__setattr__(self, "payload_sha256", digest)

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


class NfceQrCodePayloadProvider(Protocol):
    """Build the normative QR URL; CSC/secret handling remains inside the adapter."""

    def build(
        self,
        document: CanonicalFiscalDocument,
        access_key: NfeAccessKey,
        authorization: AuthorizationResult,
    ) -> NfceQrCodePayload: ...


class NfceQrCodeRenderer(Protocol):
    """Render a QR payload into an image artifact without fiscal-domain secrets."""

    def render(self, payload: NfceQrCodePayload) -> NfceQrCodeArtifact: ...


@dataclass(frozen=True, slots=True)
class DanfeNfceData:
    """Validated normal-authorized NFC-e data required by this presentation stage."""

    document: CanonicalFiscalDocument
    access_key: NfeAccessKey
    authorization: AuthorizationResult
    layout: DanfeNfceLayout = DanfeNfceLayout.FULL
    consumer_label: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.document, CanonicalFiscalDocument):
            raise FiscalValidationError("document must be CanonicalFiscalDocument")
        if self.document.document_kind is not FiscalDocumentKind.NFCE:
            raise FiscalValidationError("DANFE NFC-e requires an NFCE document")
        if not isinstance(self.access_key, NfeAccessKey):
            raise FiscalValidationError("access_key must be NfeAccessKey")
        if self.access_key.model is not ElectronicInvoiceModel.NFCE:
            raise FiscalValidationError("DANFE NFC-e requires model 65 access key")
        if self.access_key.issuer_identifier != self.document.issuer.cnpj.value:
            raise FiscalValidationError("access key issuer does not match document issuer")
        if not isinstance(self.authorization, AuthorizationResult):
            raise FiscalValidationError("authorization must be AuthorizationResult")
        if self.authorization.status is not AuthorizationStatus.AUTHORIZED:
            raise FiscalValidationError("normal DANFE NFC-e requires authorized result")
        if self.authorization.access_key != self.access_key:
            raise FiscalValidationError("authorization access key does not match DANFE")
        if self.authorization.scope.partition_key != self.document.scope.partition_key:
            raise FiscalValidationError("authorization scope does not match document scope")
        if not isinstance(self.layout, DanfeNfceLayout):
            raise FiscalValidationError("layout must be DanfeNfceLayout")
        if self.consumer_label is not None:
            label = self.consumer_label.strip()
            if len(label) > 512:
                raise FiscalValidationError("consumer_label exceeds max length 512")
            object.__setattr__(self, "consumer_label", label or None)


@dataclass(frozen=True, slots=True)
class DanfeNfcePrintArtifact:
    """Self-contained printable HTML with an embedded QR image."""

    content: bytes
    media_type: str = "text/html; charset=utf-8"

    def __post_init__(self) -> None:
        if not isinstance(self.content, bytes) or not self.content:
            raise FiscalValidationError("print artifact content must be non-empty bytes")
        if self.media_type != "text/html; charset=utf-8":
            raise FiscalValidationError("DANFE NFC-e print artifact must be UTF-8 HTML")

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True, slots=True)
class NfcePrintReceipt:
    """Non-secret acknowledgment returned by a printer adapter."""

    printer_reference: str
    job_reference: str
    content_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "printer_reference",
            _required(self.printer_reference, "printer_reference", 256),
        )
        object.__setattr__(
            self,
            "job_reference",
            _required(self.job_reference, "job_reference", 256),
        )
        digest = self.content_sha256.strip().lower()
        _require_sha256(digest, "content_sha256")
        object.__setattr__(self, "content_sha256", digest)


class FiscalPrintSink(Protocol):
    """Submit one prepared artifact to a printer/queue owned by infrastructure."""

    def submit(self, artifact: DanfeNfcePrintArtifact) -> NfcePrintReceipt: ...


class DanfeNfceHtmlRenderer:
    """Render a deterministic, self-contained 80-mm-oriented HTML document."""

    def render(
        self,
        data: DanfeNfceData,
        qr_payload: NfceQrCodePayload,
        qr_artifact: NfceQrCodeArtifact,
    ) -> DanfeNfcePrintArtifact:
        if not isinstance(data, DanfeNfceData):
            raise FiscalValidationError("data must be DanfeNfceData")
        if not isinstance(qr_payload, NfceQrCodePayload):
            raise FiscalValidationError("qr_payload must be NfceQrCodePayload")
        if not isinstance(qr_artifact, NfceQrCodeArtifact):
            raise FiscalValidationError("qr_artifact must be NfceQrCodeArtifact")
        if qr_artifact.payload_sha256 != qr_payload.sha256:
            raise NfcePrintContractError("QR renderer returned artifact for another payload")

        document = data.document
        issuer = document.issuer
        address = issuer.address
        key_groups = " ".join(
            data.access_key.value[index : index + 4]
            for index in range(0, len(data.access_key.value), 4)
        )
        item_rows = ""
        if data.layout is DanfeNfceLayout.FULL:
            item_rows = "".join(
                "<tr>"
                f"<td>{escape(item.product.commercial_code)}</td>"
                f"<td>{escape(item.product.description)}</td>"
                f"<td>{escape(_format_decimal(item.quantity))}</td>"
                f"<td>{escape(item.product.commercial_unit.value)}</td>"
                f"<td>{escape(_format_money(item.unit_price.amount))}</td>"
                f"<td>{escape(_format_money(item.net_amount.amount))}</td>"
                "</tr>"
                for item in document.items
            )

        payments = "".join(
            "<tr>"
            f"<td>{escape(_payment_label(payment.method))}</td>"
            f"<td>{escape(_format_money(payment.amount.amount))}</td>"
            "</tr>"
            for payment in document.payments
        )
        protocol = data.authorization.protocol_reference
        if protocol is None:
            raise NfcePrintContractError("authorized DANFE is missing protocol reference")

        qr_b64 = base64.b64encode(qr_artifact.content).decode("ascii")
        consumer_block = ""
        if data.consumer_label is not None:
            consumer_block = f'<div class="consumer">{escape(data.consumer_label)}</div>'
        items_block = ""
        if data.layout is DanfeNfceLayout.FULL:
            items_block = (
                '<table class="items"><thead><tr>'
                "<th>Cód</th><th>Descrição</th><th>Qtd</th><th>Un</th>"
                "<th>Vl Unit</th><th>Vl Total</th>"
                f"</tr></thead><tbody>{item_rows}</tbody></table>"
            )

        html = (
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            "<style>"
            "@page{size:80mm auto;margin:2mm}"
            "body{width:76mm;margin:0;font-family:monospace;font-size:9pt;color:#000}"
            "h1,h2,p{margin:2mm 0;text-align:center}"
            "h1{font-size:11pt}h2{font-size:9pt}"
            "table{width:100%;border-collapse:collapse;margin:2mm 0}"
            "th,td{padding:.6mm;text-align:left;vertical-align:top}"
            ".items th,.items td{border-bottom:.15mm solid #aaa;font-size:7pt}"
            ".right{text-align:right}.key{overflow-wrap:anywhere;text-align:center}"
            ".qr{text-align:center}.qr img{width:34mm;height:34mm}"
            ".consumer{text-align:center;margin:2mm 0}.sep{border-top:.2mm dashed #000}"
            "</style></head><body>"
            f"<h1>{escape(issuer.legal_name)}</h1>"
            f"<p>CNPJ: {escape(issuer.cnpj.formatted)}</p>"
            f"<p>{escape(address.street)}, {escape(address.number)} - "
            f"{escape(address.district)} - {escape(address.municipality_name)}/"
            f"{escape(address.jurisdiction.state_code)} - CEP {escape(address.postal_code)}</p>"
            '<div class="sep"></div>'
            "<h2>DOCUMENTO AUXILIAR DA NOTA FISCAL DE CONSUMIDOR ELETRÔNICA</h2>"
            f"{items_block}"
            '<table class="totals">'
            f"<tr><td>Qtde. total de itens</td><td class=\"right\">{len(document.items)}</td></tr>"
            f"<tr><td>Valor total R$</td><td class=\"right\">"
            f"{escape(_format_money(document.totals.gross_amount.amount))}</td></tr>"
            f"<tr><td>Desconto R$</td><td class=\"right\">"
            f"{escape(_format_money(document.totals.discount_amount.amount))}</td></tr>"
            f"<tr><td>Acréscimo R$</td><td class=\"right\">"
            f"{escape(_format_money(document.totals.surcharge_amount.amount))}</td></tr>"
            f"<tr><td>Valor a pagar R$</td><td class=\"right\">"
            f"{escape(_format_money(document.totals.net_amount.amount))}</td></tr>"
            "</table>"
            '<table class="payments"><thead><tr><th>FORMA PAGAMENTO</th>'
            f"<th>VALOR PAGO R$</th></tr></thead><tbody>{payments}</tbody></table>"
            '<div class="sep"></div>'
            "<p>Chave de Acesso</p>"
            f'<p class="key">{escape(key_groups)}</p>'
            f"{consumer_block}"
            f"<p>NFC-e nº {data.access_key.invoice_number:09d} Série "
            f"{data.access_key.series:03d} Emissão "
            f"{escape(document.issued_at.isoformat())}</p>"
            f"<p>Protocolo de autorização: {escape(protocol)}</p>"
            f'<div class="qr"><img alt="QR Code NFC-e" '
            f'src="data:{escape(qr_artifact.media_type)};base64,{qr_b64}"></div>'
            "</body></html>"
        )
        return DanfeNfcePrintArtifact(content=html.encode("utf-8"))


class NfcePrintService:
    """Build QR + DANFE and optionally hand the result to a printer adapter."""

    def __init__(
        self,
        *,
        qr_payload_provider: NfceQrCodePayloadProvider,
        qr_renderer: NfceQrCodeRenderer,
        danfe_renderer: DanfeNfceHtmlRenderer | None = None,
        print_sink: FiscalPrintSink | None = None,
    ) -> None:
        self._qr_payload_provider = qr_payload_provider
        self._qr_renderer = qr_renderer
        self._danfe_renderer = danfe_renderer or DanfeNfceHtmlRenderer()
        self._print_sink = print_sink

    def prepare(self, data: DanfeNfceData) -> DanfeNfcePrintArtifact:
        if not isinstance(data, DanfeNfceData):
            raise FiscalValidationError("data must be DanfeNfceData")
        payload = self._qr_payload_provider.build(
            data.document,
            data.access_key,
            data.authorization,
        )
        if not isinstance(payload, NfceQrCodePayload):
            raise NfcePrintContractError("QR payload provider must return NfceQrCodePayload")
        artifact = self._qr_renderer.render(payload)
        if not isinstance(artifact, NfceQrCodeArtifact):
            raise NfcePrintContractError("QR renderer must return NfceQrCodeArtifact")
        if artifact.payload_sha256 != payload.sha256:
            raise NfcePrintContractError("QR renderer returned artifact for another payload")
        return self._danfe_renderer.render(data, payload, artifact)

    def print(self, data: DanfeNfceData) -> NfcePrintReceipt:
        if self._print_sink is None:
            raise NfcePrintContractError("no print sink configured")
        artifact = self.prepare(data)
        receipt = self._print_sink.submit(artifact)
        if not isinstance(receipt, NfcePrintReceipt):
            raise NfcePrintContractError("print sink must return NfcePrintReceipt")
        if receipt.content_sha256 != artifact.content_sha256:
            raise NfcePrintContractError("printer receipt digest does not match submitted artifact")
        return receipt


def _required(value: str, field_name: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise FiscalValidationError(f"{field_name} must not be blank")
    if len(normalized) > max_length:
        raise FiscalValidationError(f"{field_name} exceeds max length {max_length}")
    return normalized


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64:
        raise FiscalValidationError(f"{field_name} must contain 64 hexadecimal characters")
    try:
        int(value, 16)
    except ValueError as exc:
        raise FiscalValidationError(f"{field_name} must be hexadecimal") from exc


def _format_decimal(value: Decimal) -> str:
    text = format(value, "f")
    return text.replace(".", ",")


def _format_money(value: Decimal) -> str:
    text = format(value, "f")
    if "." not in text:
        text = f"{text}.00"
    else:
        integer, fraction = text.split(".", 1)
        if len(fraction) < 2:
            fraction = fraction.ljust(2, "0")
        text = f"{integer}.{fraction}"
    return text.replace(".", ",")


def _payment_label(method: PaymentMethodKind) -> str:
    labels = {
        PaymentMethodKind.CASH: "Dinheiro",
        PaymentMethodKind.CREDIT_CARD: "Cartão de crédito",
        PaymentMethodKind.DEBIT_CARD: "Cartão de débito",
        PaymentMethodKind.PIX: "PIX",
        PaymentMethodKind.VOUCHER: "Voucher",
        PaymentMethodKind.OTHER: "Outros",
    }
    return labels[method]
