"""Adapter PagBank Order/PIX com fronteira explícita de confiança.

O token é injetado já resolvido pelo SecretStore e nunca é persistido ou incluído
em mensagens de erro. Webhooks só são marcados como confiáveis após validar
SHA-256 de ``token + '-' + payload_bruto`` contra ``x-authenticity-token``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol

import requests

from core.dominio.dinheiro import Dinheiro

from .adapters import CobrancaProvedor, WebhookNormalizado


class ErroPagBank(RuntimeError):
    """Erro sanitizado da integração; nunca inclui token ou corpo completo."""


class RespostaHTTP(Protocol):
    status_code: int

    def json(self) -> Any: ...


class TransporteHTTP(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        json: Mapping[str, Any] | None = None,
        timeout: float,
    ) -> RespostaHTTP: ...


@dataclass(frozen=True, kw_only=True)
class ClientePagBank:
    nome: str
    email: str
    tax_id: str

    def para_payload(self) -> dict[str, str]:
        nome = self.nome.strip()
        email = self.email.strip()
        tax_id = "".join(caractere for caractere in self.tax_id if caractere.isdigit())
        if not nome or not email or not tax_id:
            raise ValueError("cliente PagBank incompleto")
        if len(tax_id) not in {11, 14}:
            raise ValueError("CPF/CNPJ do cliente deve conter 11 ou 14 dígitos")
        return {
            "name": nome,
            "email": email,
            "tax_id": tax_id,
        }


@dataclass(frozen=True, kw_only=True)
class ConfiguracaoPagBank:
    token: str
    ambiente: str = "sandbox"
    notification_url: str | None = None
    timeout_seconds: float = 10.0

    @property
    def base_url(self) -> str:
        if self.ambiente == "sandbox":
            return "https://sandbox.api.pagseguro.com"
        if self.ambiente == "production":
            return "https://api.pagseguro.com"
        raise ValueError("ambiente PagBank inválido")

    def validar(self) -> None:
        if not self.token.strip():
            raise ValueError("token PagBank ausente")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 60:
            raise ValueError("timeout PagBank inválido")


def _centavos(valor: Dinheiro) -> int:
    centavos = (valor.valor * Decimal(100)).quantize(Decimal(1))
    if centavos <= 0:
        raise ValueError("valor PagBank deve ser positivo")
    return int(centavos)


def _dinheiro_centavos(valor: object) -> Dinheiro:
    return Dinheiro(Decimal(str(valor)) / Decimal(100))


def _parse_datetime(valor: object | None) -> datetime:
    if not valor:
        return datetime.now(timezone.utc)
    texto = str(valor).replace("Z", "+00:00")
    instante = datetime.fromisoformat(texto)
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    return instante.astimezone(timezone.utc)


def _charges(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    bruto = payload.get("charges")
    if not isinstance(bruto, list):
        return []
    return [item for item in bruto if isinstance(item, Mapping)]


def _status_order(payload: Mapping[str, Any]) -> str:
    charges = _charges(payload)
    statuses = {str(charge.get("status", "")).upper() for charge in charges}
    if "PAID" in statuses:
        return "pago"
    if "CANCELED" in statuses:
        return "cancelado"
    if "DECLINED" in statuses:
        return "falhou"
    if "AUTHORIZED" in statuses:
        return "autorizado"
    return "pendente"


def _valor_payload(payload: Mapping[str, Any]) -> Dinheiro:
    for charge in _charges(payload):
        amount = charge.get("amount")
        if isinstance(amount, Mapping) and amount.get("value") is not None:
            return _dinheiro_centavos(amount["value"])
    qr_codes = payload.get("qr_codes")
    if isinstance(qr_codes, list) and qr_codes and isinstance(qr_codes[0], Mapping):
        amount = qr_codes[0].get("amount")
        if isinstance(amount, Mapping) and amount.get("value") is not None:
            return _dinheiro_centavos(amount["value"])
    raise ErroPagBank("resposta PagBank sem valor reconhecível")


def _payload_exibicao(payload: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    itens: list[tuple[str, str]] = []
    qr_codes = payload.get("qr_codes")
    if isinstance(qr_codes, list) and qr_codes and isinstance(qr_codes[0], Mapping):
        qr = qr_codes[0]
        if qr.get("text"):
            itens.append(("pix_copia_cola", str(qr["text"])))
        links = qr.get("links")
        if isinstance(links, list):
            for link in links:
                if not isinstance(link, Mapping):
                    continue
                if link.get("media") == "image/png" and link.get("href"):
                    itens.append(("qr_code_png_url", str(link["href"])))
                    break
    return tuple(itens)


def _detalhes_seguros_erro_http(resposta: RespostaHTTP) -> str:
    """Extrai somente código e parâmetro; nunca descrição nem valores recebidos."""

    try:
        dados = resposta.json()
    except (ValueError, TypeError):
        return ""
    if not isinstance(dados, Mapping):
        return ""
    mensagens = dados.get("error_messages")
    if not isinstance(mensagens, list):
        return ""

    detalhes: list[str] = []
    for mensagem in mensagens[:5]:
        if not isinstance(mensagem, Mapping):
            continue
        codigo = str(mensagem.get("code", "")).strip()
        parametro = str(mensagem.get("parameter_name", "")).strip()
        partes: list[str] = []
        if codigo:
            partes.append(f"code={codigo[:80]}")
        if parametro:
            partes.append(f"parameter={parametro[:120]}")
        if partes:
            detalhes.append(",".join(partes))
    return "; ".join(detalhes)


class AdapterPagBank:
    nome = "pagbank"

    def __init__(
        self,
        configuracao: ConfiguracaoPagBank,
        *,
        transporte: TransporteHTTP | None = None,
    ) -> None:
        configuracao.validar()
        self._config = configuracao
        self._http: TransporteHTTP = transporte or requests.Session()
        self._conhecidas: set[str] = set()

    def _headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._config.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["x-idempotency-key"] = idempotency_key
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        idempotency_key: str | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        try:
            resposta = self._http.request(
                method,
                f"{self._config.base_url}{path}",
                headers=self._headers(idempotency_key),
                json=payload,
                timeout=self._config.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise ErroPagBank("falha de transporte PagBank") from exc
        if resposta.status_code < 200 or resposta.status_code >= 300:
            mensagem = f"PagBank respondeu HTTP {resposta.status_code}"
            detalhes = _detalhes_seguros_erro_http(resposta)
            if detalhes:
                mensagem = f"{mensagem} ({detalhes})"
            raise ErroPagBank(mensagem)
        try:
            dados = resposta.json()
        except (ValueError, TypeError) as exc:
            raise ErroPagBank("PagBank retornou JSON inválido") from exc
        if not isinstance(dados, Mapping):
            raise ErroPagBank("PagBank retornou payload inválido")
        return dados

    def criar_pix(
        self,
        *,
        pagamento_id: str,
        valor: Dinheiro,
        idempotency_key: str,
        cliente: ClientePagBank,
        descricao: str = "Pedido Gerente AI",
    ) -> CobrancaProvedor:
        cents = _centavos(valor)
        payload: dict[str, Any] = {
            "reference_id": pagamento_id[:64],
            "customer": cliente.para_payload(),
            "items": [
                {
                    "reference_id": pagamento_id[:64],
                    "name": descricao[:100],
                    "quantity": 1,
                    "unit_amount": cents,
                }
            ],
            "qr_codes": [{"amount": {"value": cents}}],
        }
        if self._config.notification_url:
            payload["notification_urls"] = [self._config.notification_url]
        dados = self._request(
            "POST", "/orders", idempotency_key=idempotency_key, payload=payload
        )
        order_id = str(dados.get("id", ""))
        if not order_id.startswith("ORDE_"):
            raise ErroPagBank("PagBank não retornou identificador de pedido")
        self._conhecidas.add(order_id)
        return CobrancaProvedor(
            order_id,
            _status_order(dados),
            _valor_payload(dados),
            _payload_exibicao(dados),
        )

    def criar_cobranca(
        self, *, pagamento_id: str, valor: Dinheiro, idempotency_key: str
    ) -> CobrancaProvedor:
        raise ErroPagBank(
            "PagBank PIX exige dados explícitos do cliente; use criar_pix"
        )

    def consultar_transacao(self, id_externo: str) -> CobrancaProvedor | None:
        if not id_externo.startswith("ORDE_"):
            return None
        dados = self._request("GET", f"/orders/{id_externo}")
        return CobrancaProvedor(
            id_externo,
            _status_order(dados),
            _valor_payload(dados),
            _payload_exibicao(dados),
        )

    def validar_assinatura(self, payload_bruto: bytes, assinatura: str) -> bool:
        esperado = hashlib.sha256(
            self._config.token.encode("utf-8") + b"-" + payload_bruto
        ).hexdigest()
        return hmac.compare_digest(esperado, assinatura.strip().lower())

    def normalizar_webhook_assinado(
        self, *, payload_bruto: bytes, assinatura: str
    ) -> WebhookNormalizado:
        assinatura_validada = self.validar_assinatura(payload_bruto, assinatura)
        try:
            dados = json.loads(payload_bruto.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ErroPagBank("webhook PagBank inválido") from exc
        if not isinstance(dados, Mapping):
            raise ErroPagBank("webhook PagBank inválido")
        return self._normalizar(dados, assinatura_validada)

    def normalizar_webhook(self, payload: dict[str, Any]) -> WebhookNormalizado:
        # Um dict já parseado perdeu a representação byte-a-byte necessária para
        # validar a assinatura. Portanto nunca é considerado confiável.
        return self._normalizar(payload, False)

    def _normalizar(
        self, payload: Mapping[str, Any], assinatura_validada: bool
    ) -> WebhookNormalizado:
        order_id = str(payload.get("id", ""))
        charges = _charges(payload)
        charge = charges[0] if charges else {}
        status = str(charge.get("status", "")).upper()
        tipo = "confirmado" if status == "PAID" else status.casefold() or "pendente"
        charge_id = str(charge.get("id", "")) or order_id
        timestamp = _parse_datetime(charge.get("paid_at") or charge.get("created_at"))
        valor = _valor_payload(payload)
        return WebhookNormalizado(
            self.nome,
            charge_id,
            order_id,
            tipo,
            valor,
            timestamp,
            assinatura_validada,
            f"pagbank:{order_id}:{charge_id}:{status or 'PENDING'}",
        )

    def reconciliar(self) -> tuple[CobrancaProvedor, ...]:
        atualizadas = []
        for order_id in sorted(self._conhecidas):
            cobranca = self.consultar_transacao(order_id)
            if cobranca is not None:
                atualizadas.append(cobranca)
        return tuple(atualizadas)
