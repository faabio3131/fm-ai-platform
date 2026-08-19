"""Migra o adapter Mercado Pago da Payments API legada para Orders API.

Patch idempotente e fail-closed: somente substitui o bloco conhecido do adapter.
Nao toca em credenciais, banco ou configuracoes do provedor.
"""

from __future__ import annotations

from pathlib import Path

TARGET = Path("core/integracoes/provedores.py")
START = "class MercadoPagoAdapter(_ClienteResiliente):\n"
END = "\n\nclass PortaGeminiTenant(Protocol):\n"

NEW = '''class MercadoPagoAdapter(_ClienteResiliente):
    """Pix via Checkout Transparente / Orders API do Mercado Pago."""

    BASE_URL = "https://api.mercadopago.com"

    def __init__(
        self,
        *,
        configuracao: ConfiguracaoMercadoPago,
        http: PortaHTTPProvedor,
        sleep: Callable[[float], None] = lambda _: None,
    ) -> None:
        super().__init__(
            http=http,
            timeout_seconds=configuracao.timeout_seconds,
            max_attempts=configuracao.max_attempts,
            sleep=sleep,
            nome="Mercado Pago",
        )
        self._config = configuracao

    def _headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._config.access_token}",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["X-Idempotency-Key"] = _idempotency_key(idempotency_key)
        return headers

    @staticmethod
    def _primeiro_pagamento(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        transacoes = payload.get("transactions")
        if not isinstance(transacoes, Mapping):
            return {}
        pagamentos = transacoes.get("payments")
        if not isinstance(pagamentos, list) or not pagamentos:
            return {}
        primeiro = pagamentos[0]
        return primeiro if isinstance(primeiro, Mapping) else {}

    @staticmethod
    def _status_runtime(payload: Mapping[str, Any], pagamento: Mapping[str, Any]) -> str:
        status = str(payload.get("status", "")).strip().casefold()
        detalhe = str(payload.get("status_detail", "")).strip().casefold()
        if not detalhe:
            detalhe = str(pagamento.get("status_detail", "")).strip().casefold()
        if status == "processed" and detalhe == "accredited":
            return "paid"
        return status

    @classmethod
    def _normalizar(cls, payload: Mapping[str, Any]) -> CobrancaMercadoPago:
        identificador = str(payload.get("id", "")).strip()
        try:
            valor = Decimal(str(payload["total_amount"])).quantize(Decimal("0.01"))
        except (KeyError, InvalidOperation, ValueError) as exc:
            raise ErroProvedorExterno("Mercado Pago retornou valor invalido") from exc
        if not identificador or valor <= 0:
            raise ErroProvedorExterno("Mercado Pago retornou order incompleta")
        pagamento = cls._primeiro_pagamento(payload)
        metodo = pagamento.get("payment_method")
        metodo = metodo if isinstance(metodo, Mapping) else {}
        return CobrancaMercadoPago(
            pagamento_id=identificador,
            status=cls._status_runtime(payload, pagamento),
            valor=valor,
            referencia_externa=str(payload.get("external_reference", "")).strip(),
            pix_copia_cola=(str(metodo["qr_code"]) if metodo.get("qr_code") else None),
            qr_code_base64=(str(metodo["qr_code_base64"]) if metodo.get("qr_code_base64") else None),
            ticket_url=(str(metodo["ticket_url"]) if metodo.get("ticket_url") else None),
        )

    def criar_pix(self, *, valor: Decimal, email_pagador: str, referencia_externa: str, idempotency_key: str) -> CobrancaMercadoPago:
        if valor <= 0 or not email_pagador.strip() or not referencia_externa.strip():
            raise ErroProvedorExterno("pagamento Mercado Pago incompleto")
        quantizado = str(valor.quantize(Decimal("0.01")))
        payload = self._request(
            retry_safe=True,
            method="POST",
            url=f"{self.BASE_URL}/v1/orders",
            headers=self._headers(idempotency_key),
            json_body={
                "type": "online",
                "total_amount": quantizado,
                "external_reference": referencia_externa.strip(),
                "processing_mode": "automatic",
                "transactions": {"payments": [{"amount": quantizado, "payment_method": {"id": "pix", "type": "bank_transfer"}}]},
                "payer": {"email": email_pagador.strip()},
            },
        )
        return self._normalizar(payload)

    def consultar_pagamento(self, pagamento_id: str) -> CobrancaMercadoPago:
        identificador = pagamento_id.strip()
        if not identificador:
            raise ErroProvedorExterno("order Mercado Pago ausente")
        payload = self._request(retry_safe=True, method="GET", url=f"{self.BASE_URL}/v1/orders/{identificador}", headers=self._headers(), json_body=None)
        return self._normalizar(payload)

    def validar_webhook(self, *, data_id: str, request_id: str, x_signature: str) -> bool:
        partes = dict(item.split("=", 1) for item in x_signature.split(",") if "=" in item)
        ts = partes.get("ts", "").strip()
        recebido = partes.get("v1", "").strip().casefold()
        if not ts or not recebido or not data_id or not request_id:
            return False
        manifesto = f"id:{data_id};request-id:{request_id};ts:{ts};"
        esperado = hmac.new(self._config.webhook_secret.encode(), manifesto.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(esperado, recebido)

    def normalizar_webhook(self, *, payload: Mapping[str, Any], data_id: str, request_id: str, x_signature: str) -> EventoWebhookProvedor:
        if not self.validar_webhook(data_id=data_id, request_id=request_id, x_signature=x_signature):
            raise ErroProvedorExterno("assinatura Mercado Pago invalida")
        tipo = str(payload.get("type") or "").strip().casefold()
        if tipo and tipo != "order":
            raise ErroProvedorExterno("webhook Mercado Pago nao e de order")
        data = payload.get("data")
        body_id = ""
        if isinstance(data, Mapping):
            body_id = str(data.get("id") or "").strip()
        if body_id and body_id.casefold() != data_id.strip().casefold():
            raise ErroProvedorExterno("webhook Mercado Pago com recurso divergente")
        action = str(payload.get("action") or "order.updated").strip()
        evento_id = str(payload.get("id") or request_id).strip()
        if not evento_id or not data_id:
            raise ErroProvedorExterno("webhook Mercado Pago incompleto")
        return EventoWebhookProvedor(
            provedor="mercado_pago",
            evento_id=evento_id,
            recurso_id=data_id.strip(),
            tipo=action,
            assinatura_validada=True,
            idempotency_key=f"mercado_pago:{evento_id}:{data_id.strip()}:{action}",
        )
'''


def apply(text: str) -> str:
    # Corrige branches que ja usam Orders mas ainda normalizam data.id para lower-case,
    # o que invalida HMAC de IDs alfanumericos reais como ORDTST... .
    if "data_id.lower()" in text:
        text = text.replace(
            'manifesto = f"id:{data_id.lower()};request-id:{request_id};ts:{ts};"',
            'manifesto = f"id:{data_id};request-id:{request_id};ts:{ts};"',
            1,
        )
    if 'url=f"{self.BASE_URL}/v1/orders"' in text and "order Mercado Pago ausente" in text:
        return text
    inicio = text.find(START)
    fim = text.find(END, inicio + len(START)) if inicio >= 0 else -1
    if inicio < 0 or fim < 0:
        raise RuntimeError("bloco MercadoPagoAdapter conhecido nao encontrado; patch abortado")
    return text[:inicio] + NEW + text[fim:]


def main() -> None:
    original = TARGET.read_text(encoding="utf-8")
    atualizado = apply(original)
    if atualizado == original:
        print("MercadoPagoAdapter ja usa Orders API com assinatura correta; nenhuma alteracao necessaria.")
        return
    TARGET.write_text(atualizado, encoding="utf-8")
    print("MercadoPagoAdapter atualizado: Orders API e HMAC preservando data.id exato.")


if __name__ == "__main__":
    main()
