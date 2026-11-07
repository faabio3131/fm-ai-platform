"""Adapter REST Asaas v3: transport is isolated from financial state authority.

The caller owns tenant/unit scope, the immutable payment binding and persistence.
No browser redirect or webhook body alone is evidence of settlement.
API contract: https://docs.asaas.com/reference/criar-nova-cobranca
"""
from __future__ import annotations

import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

import httpx

from core.dominio.dinheiro import Dinheiro
from core.pagamentos.adapters import CobrancaProvedor

_BASES = {
    "sandbox": "https://api-sandbox.asaas.com/v3",
    "production": "https://api.asaas.com/v3",
}
_EXTERNAL_ID = re.compile(r"^[a-zA-Z0-9_:-]{1,100}$")
_PAID = frozenset({"CONFIRMED", "RECEIVED"})
_NO_PAYMENT = frozenset({"PENDING", "AWAITING_RISK_ANALYSIS", "OVERDUE",
                         "AUTHORIZED", "REFUND_REQUESTED", "REFUND_IN_PROGRESS"})
_REFUNDED = frozenset({"REFUNDED", "REFUND_CONFIRMED"})
_FINAL_NEGATIVE = frozenset({"CHARGEBACK_REQUESTED",
                             "CHARGEBACK_DISPUTE", "AWAITING_CHARGEBACK_REVERSAL",
                             "DUNNING_REQUESTED", "DUNNING_RECEIVED",
                             "DELETED", "RESTORED"})


class ErroAsaas(RuntimeError):
    """Sanitized error without credential, response body, PII, or tokens."""


@dataclass(frozen=True)
class ConfiguracaoAsaas:
    api_key: str
    ambiente: str = "sandbox"
    webhook_token: str | None = None
    timeout_seconds: float = 15.0

    def __post_init__(self) -> None:
        if self.ambiente not in _BASES or not self.api_key.strip():
            raise ErroAsaas("asaas_configuracao_invalida")
        if not 0 < self.timeout_seconds <= 60:
            raise ErroAsaas("asaas_timeout_invalido")
        if self.webhook_token is not None and not 32 <= len(self.webhook_token) <= 255:
            raise ErroAsaas("asaas_webhook_token_invalido")


@dataclass(frozen=True)
class PagadorAsaas:
    nome: str
    email: str
    documento: str

    def validar(self) -> None:
        digits = re.sub(r"\D", "", self.documento)
        if len(self.nome.strip()) < 2 or "@" not in self.email or len(digits) not in (11, 14):
            raise ErroAsaas("asaas_pagador_invalido")


@dataclass(frozen=True)
class CheckoutAsaas:
    id_externo: str
    status: str
    valor: Dinheiro
    metodo: str
    url_fatura: str | None = None
    pix_copia_cola: str | None = None
    pix_qr_base64: str | None = None

    def como_cobranca(self) -> CobrancaProvedor:
        exibicao = []
        if self.url_fatura:
            exibicao.append(("pagamento_url", self.url_fatura))
        if self.pix_copia_cola:
            exibicao.append(("pix_copia_cola", self.pix_copia_cola))
        if self.pix_qr_base64:
            exibicao.append(("qr_code_base64", self.pix_qr_base64))
        return CobrancaProvedor(self.id_externo, self.status, self.valor, tuple(exibicao))


@dataclass(frozen=True)
class EventoAsaas:
    id_evento: str
    pagamento_externo: str
    referencia: str
    evento: str
    valor: Dinheiro
    status: str


class AdapterAsaas:
    nome = "asaas"

    def __init__(
        self,
        configuracao: ConfiguracaoAsaas,
        *,
        transporte: httpx.Client | None = None,
    ) -> None:
        self.config = configuracao
        self.http = transporte or httpx.Client()

    def _request(
        self,
        method: str,
        route: str,
        *,
        params: Mapping[str, str] | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        try:
            response = self.http.request(
                method,
                _BASES[self.config.ambiente] + route,
                headers={
                    "access_token": self.config.api_key,
                    "User-Agent": "Kordena/1.0",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                params=params,
                json=dict(payload) if payload is not None else None,
                timeout=self.config.timeout_seconds,
                follow_redirects=False,
            )
        except httpx.TimeoutException as exc:
            raise ErroAsaas("asaas_timeout_consultar_antes_de_repetir") from exc
        except httpx.RequestError as exc:
            raise ErroAsaas("asaas_rede_indisponivel") from exc
        if response.status_code >= 400:
            raise ErroAsaas(f"asaas_http_{response.status_code}")
        try:
            result = response.json()
        except (TypeError, ValueError) as exc:
            raise ErroAsaas("asaas_resposta_invalida") from exc
        if not isinstance(result, Mapping):
            raise ErroAsaas("asaas_resposta_invalida")
        return result

    @staticmethod
    def _external(external_reference: str) -> str:
        if not _EXTERNAL_ID.fullmatch(external_reference):
            raise ErroAsaas("asaas_referencia_externa_invalida")
        return external_reference

    @staticmethod
    def _dinheiro(amount: object) -> Dinheiro:
        try:
            raw = Decimal(str(amount))
            if not raw.is_finite() or raw <= 0:
                raise ValueError()
            return Dinheiro(raw)
        except (ValueError, TypeError, ArithmeticError) as exc:
            raise ErroAsaas("asaas_valor_invalido") from exc

    def _list_unique(self, endpoint: str, reference: str) -> Mapping[str, Any] | None:
        result = self._request("GET", endpoint, params={
            "externalReference": reference, "limit": "2",
        })
        items = result.get("data")
        if not isinstance(items, list) or len(items) > 1:
            raise ErroAsaas("asaas_referencia_ambigua")
        if not items:
            return None
        item = items[0]
        if not isinstance(item, Mapping) or item.get("externalReference") != reference:
            raise ErroAsaas("asaas_referencia_divergente")
        return item

    def obter_ou_criar_cliente(self, pagador: PagadorAsaas, *, reference: str) -> str:
        pagador.validar()
        reference = self._external(reference)
        existing = self._list_unique("/customers", reference)
        if existing is None:
            try:
                existing = self._request("POST", "/customers", payload={
                    "name": pagador.nome.strip(),
                    "email": pagador.email.strip(),
                    "cpfCnpj": re.sub(r"\D", "", pagador.documento),
                    "externalReference": reference,
                    "notificationDisabled": True,
                })
            except ErroAsaas:
                # POST outcome may be ambiguous: never auto-POST a second time.
                existing = self._list_unique("/customers", reference)
                if existing is None:
                    raise
        customer_id = existing.get("id")
        if not isinstance(customer_id, str) or not customer_id.startswith("cus_"):
            raise ErroAsaas("asaas_cliente_invalido")
        if existing.get("cpfCnpj") is not None and (
            re.sub(r"\D", "", str(existing["cpfCnpj"]))
            != re.sub(r"\D", "", pagador.documento)
        ):
            raise ErroAsaas("asaas_cliente_documento_divergente")
        return customer_id

    @staticmethod
    def _parse_payment(data: Mapping[str, Any], reference: str, metodo: str, valor: Dinheiro) -> CheckoutAsaas:
        if data.get("externalReference") != reference:
            raise ErroAsaas("asaas_cobranca_referencia_divergente")
        if data.get("billingType") != metodo:
            raise ErroAsaas("asaas_cobranca_metodo_divergente")
        if AdapterAsaas._dinheiro(data.get("value")) != valor:
            raise ErroAsaas("asaas_cobranca_valor_divergente")
        id_externo = data.get("id")
        if not isinstance(id_externo, str) or not id_externo.startswith("pay_"):
            raise ErroAsaas("asaas_cobranca_id_invalido")
        raw_status = str(data.get("status", "")).upper()
        if raw_status in _PAID:
            status = "pago"
        elif raw_status in _REFUNDED:
            status = "estornado"
        elif raw_status in _FINAL_NEGATIVE:
            status = "cancelado"
        elif raw_status in _NO_PAYMENT:
            status = "pendente"
        else:
            raise ErroAsaas("asaas_status_desconhecido")
        url = data.get("invoiceUrl")
        if url is not None:
            if not isinstance(url, str):
                raise ErroAsaas("asaas_url_invalida")
            parsed = urlsplit(url)
            if parsed.scheme != "https" or parsed.username or parsed.password or (
                parsed.hostname not in {"www.asaas.com", "asaas.com", "sandbox.asaas.com"}
            ):
                raise ErroAsaas("asaas_url_nao_confiavel")
        return CheckoutAsaas(id_externo, status, valor, metodo, url_fatura=url)

    def criar_cobranca(
        self, *,
        reference: str,
        customer_id: str,
        valor: Dinheiro,
        metodo: str,
        vencimento: date,
    ) -> CheckoutAsaas:
        reference = self._external(reference)
        if metodo not in {"PIX", "CREDIT_CARD"} or not customer_id.startswith("cus_"):
            raise ErroAsaas("asaas_metodo_ou_cliente_invalido")
        if valor.valor <= 0:
            raise ErroAsaas("asaas_valor_invalido")
        existing = self._list_unique("/payments", reference)
        if existing is None:
            try:
                existing = self._request("POST", "/payments", payload={
                    "customer": customer_id,
                    "billingType": metodo,
                    "value": float(valor.valor),
                    "dueDate": vencimento.isoformat(),
                    "externalReference": reference,
                })
            except ErroAsaas:
                existing = self._list_unique("/payments", reference)
                if existing is None:
                    raise
        result = self._parse_payment(existing, reference, metodo, valor)
        if metodo == "PIX" and result.status == "pendente":
            qrcode = self._request("GET", f"/payments/{result.id_externo}/pixQrCode")
            text = qrcode.get("payload")
            image = qrcode.get("encodedImage")
            if not isinstance(text, str) or not text:
                raise ErroAsaas("asaas_pix_payload_ausente")
            result = CheckoutAsaas(
                result.id_externo, result.status, result.valor, result.metodo,
                result.url_fatura, text, image if isinstance(image, str) else None,
            )
        return result

    def consultar_cobranca(
        self, *, id_externo: str, reference: str, metodo: str, valor: Dinheiro,
    ) -> CheckoutAsaas:
        if not re.fullmatch(r"pay_[A-Za-z0-9]+", id_externo):
            raise ErroAsaas("asaas_cobranca_id_invalido")
        response = self._request("GET", f"/payments/{id_externo}")
        if response.get("id") != id_externo:
            raise ErroAsaas("asaas_cobranca_id_divergente")
        return self._parse_payment(response, self._external(reference), metodo, valor)

    def autenticar_webhook(
        self, *, recebido: str | None, payload: Mapping[str, Any],
    ) -> EventoAsaas:
        token = self.config.webhook_token
        if not token or not recebido or not hmac.compare_digest(token, recebido):
            raise ErroAsaas("asaas_webhook_nao_autenticado")
        eid, event = payload.get("id"), payload.get("event")
        payment = payload.get("payment")
        if not isinstance(eid, str) or not eid.startswith("evt_") or not isinstance(payment, Mapping):
            raise ErroAsaas("asaas_webhook_invalido")
        pid, reference = payment.get("id"), payment.get("externalReference")
        if not isinstance(pid, str) or not pid.startswith("pay_") or not isinstance(reference, str):
            raise ErroAsaas("asaas_webhook_vinculo_invalido")
        return EventoAsaas(
            eid, pid, self._external(reference), str(event),
            self._dinheiro(payment.get("value")), str(payment.get("status", "")).upper(),
        )

    def solicitar_estorno(self, *, id_externo: str, valor: Dinheiro | None = None) -> str:
        if not re.fullmatch(r"pay_[A-Za-z0-9]+", id_externo):
            raise ErroAsaas("asaas_cobranca_id_invalido")
        payload = {} if valor is None else {"value": float(valor.valor)}
        resposta = self._request("POST", f"/payments/{id_externo}/refund", payload=payload)
        # Request accepted is not the same as refund confirmed; reconcile GET/events.
        return str(resposta.get("status", "PROCESSING"))
