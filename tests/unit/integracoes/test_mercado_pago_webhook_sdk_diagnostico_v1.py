from __future__ import annotations

from enum import Enum

from scripts.mercado_pago_webhook_sdk_diagnostico_app import (
    _validar_kordena,
    _validar_sdk_oficial,
)


class _Reason(Enum):
    SIGNATURE_MISMATCH = "SignatureMismatch"


class _FakeInvalid(Exception):
    def __init__(self) -> None:
        super().__init__("nao deve ser logado")
        self.reason = _Reason.SIGNATURE_MISMATCH


class _ValidatorOk:
    InvalidWebhookSignatureError = _FakeInvalid

    @staticmethod
    def validate(*args, **kwargs) -> None:
        return None


class _ValidatorFail:
    InvalidWebhookSignatureError = _FakeInvalid

    @staticmethod
    def validate(*args, **kwargs) -> None:
        raise _FakeInvalid()


def test_wrapper_sdk_retorna_apenas_resultado_sanitizado() -> None:
    valido, motivo = _validar_sdk_oficial(
        x_signature="ts=1720000000,v1=" + "a" * 64,
        x_request_id="req-1",
        data_id="ORDTST01ABC",
        secret="segredo-apenas-de-teste",
        validator_cls=_ValidatorOk,
    )
    assert valido is True
    assert motivo == "ok"


def test_wrapper_sdk_expoe_motivo_enum_sem_expor_segredo() -> None:
    valido, motivo = _validar_sdk_oficial(
        x_signature="ts=1720000000,v1=" + "a" * 64,
        x_request_id="req-1",
        data_id="ORDTST01ABC",
        secret="segredo-apenas-de-teste",
        validator_cls=_ValidatorFail,
    )
    assert valido is False
    assert motivo == "SignatureMismatch"
    assert "segredo-apenas-de-teste" not in motivo


def test_validacao_kordena_aceita_manifesto_oficial() -> None:
    import hashlib
    import hmac

    secret = "segredo-apenas-de-teste"
    data_id = "ORDTST01ABC"
    request_id = "req-1"
    ts = "1720000000"
    manifesto = f"id:{data_id};request-id:{request_id};ts:{ts};"
    recebido = hmac.new(secret.encode(), manifesto.encode(), hashlib.sha256).hexdigest()

    assert _validar_kordena(
        data_id=data_id,
        request_id=request_id,
        ts=ts,
        recebido=recebido,
        secret=secret,
    ) is True
