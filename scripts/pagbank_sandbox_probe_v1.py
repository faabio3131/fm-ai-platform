"""Diagnóstico seguro do PagBank Sandbox para PAY-002.

Envia um payload mínimo baseado no exemplo oficial de Order/PIX e imprime apenas
informações sanitizadas da resposta. O token nunca é exibido nem persistido.

Uso:
    python -m scripts.pagbank_sandbox_probe_v1
"""

from __future__ import annotations

import json
import os
import re
from uuid import uuid4

import requests


_SANDBOX_URL = "https://sandbox.api.pagseguro.com/orders"


def _sanitize(value: object) -> str:
    text = str(value)
    text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[email-redacted]", text)
    text = re.sub(r"\b\d{8,}\b", "[number-redacted]", text)
    text = re.sub(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
        "[id-redacted]",
        text,
    )
    return text[:300]


def _safe_error_lines(response: requests.Response) -> list[str]:
    try:
        body = response.json()
    except (ValueError, json.JSONDecodeError):
        body = None

    lines: list[str] = []
    if isinstance(body, dict):
        messages = body.get("error_messages")
        if isinstance(messages, list):
            for message in messages[:5]:
                if not isinstance(message, dict):
                    continue
                parts = []
                for key in ("code", "error", "description", "parameter_name"):
                    value = message.get(key)
                    if value not in (None, ""):
                        parts.append(f"{key}={_sanitize(value)}")
                if parts:
                    lines.append(" | ".join(parts))
        elif body:
            for key in ("code", "error", "description", "message"):
                value = body.get(key)
                if value not in (None, ""):
                    lines.append(f"{key}={_sanitize(value)}")
    if not lines:
        content_type = response.headers.get("content-type", "unknown")
        lines.append(f"content_type={_sanitize(content_type)}")
        if response.text:
            lines.append(f"text={_sanitize(response.text)}")
    return lines


def main() -> int:
    if os.getenv("FM_AI_PAGBANK_ENV", "sandbox").strip().lower() != "sandbox":
        raise RuntimeError("este probe só pode ser executado com FM_AI_PAGBANK_ENV=sandbox")

    token = os.getenv("PAGBANK_TOKEN", "").strip()
    if not token:
        raise RuntimeError("PAGBANK_TOKEN não está carregado nesta sessão do PowerShell")

    buyer_email = input("E-mail do comprador de teste do Sandbox: ").strip()
    if not buyer_email.endswith("@sandbox.pagseguro.com.br"):
        raise RuntimeError("use o e-mail do comprador de teste terminado em @sandbox.pagseguro.com.br")

    reference = f"probe-{uuid4()}"
    payload = {
        "reference_id": reference,
        "customer": {
            "name": "Jose da Silva",
            "email": buyer_email,
            "tax_id": "12345678909",
            "phones": [
                {
                    "country": "55",
                    "area": "11",
                    "number": "999999999",
                    "type": "MOBILE",
                }
            ],
        },
        "items": [
            {
                "reference_id": reference,
                "name": "Homologacao Gerente AI",
                "quantity": 1,
                "unit_amount": 100,
            }
        ],
        "qr_codes": [{"amount": {"value": 100}}],
    }

    response = requests.post(
        _SANDBOX_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-idempotency-key": f"probe:{reference}",
        },
        json=payload,
        timeout=15,
    )

    print(f"HTTP_STATUS={response.status_code}")
    if response.status_code == 201:
        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError("PagBank retornou 201 sem JSON válido") from exc
        order_id = str(body.get("id", "")) if isinstance(body, dict) else ""
        has_qr = bool(body.get("qr_codes")) if isinstance(body, dict) else False
        print(f"ORDER_ID={order_id if order_id.startswith('ORDE_') else '[invalid]'}")
        print(f"HAS_QR={has_qr}")
        return 0

    print("SAFE_ERROR_BEGIN")
    for line in _safe_error_lines(response):
        print(line)
    print("SAFE_ERROR_END")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
