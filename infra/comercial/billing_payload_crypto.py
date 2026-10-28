"""Cifra de payloads de webhook comercial — KCA-10.

O corpo bruto de webhook nunca é persistido em claro. A chave mestra permanece
na infraestrutura e usa o mesmo contrato operacional já adotado pelo Secret Vault.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken


class BillingWebhookPayloadCipher:
    def __init__(self, *, master_key: str | None = None) -> None:
        raw_value = (
            master_key
            if master_key is not None
            else os.getenv("FM_AI_SECRET_MASTER_KEY", "")
        )
        raw = (raw_value or "").strip()
        if not raw:
            raise RuntimeError(
                "FM_AI_SECRET_MASTER_KEY ausente para billing webhook payload"
            )
        try:
            self._fernet = Fernet(raw.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise RuntimeError("FM_AI_SECRET_MASTER_KEY invalida") from exc

    def encrypt(self, payload: bytes) -> str:
        if not payload:
            raise ValueError("billing_webhook_payload_vazio")
        return self._fernet.encrypt(payload).decode("ascii")

    def decrypt(self, ciphertext: str) -> bytes:
        encoded = ciphertext.strip()
        if not encoded:
            raise ValueError("billing_webhook_ciphertext_vazio")
        try:
            return self._fernet.decrypt(encoded.encode("ascii"))
        except (InvalidToken, UnicodeEncodeError) as exc:
            raise ValueError("billing_webhook_ciphertext_invalido") from exc
