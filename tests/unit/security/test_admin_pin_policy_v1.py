from __future__ import annotations

import pytest

from core.seguranca.autenticacao import hash_admin_pin, validate_admin_pin, verify_admin_pin


def test_pin_admin_aceita_seis_a_oito_digitos_e_hash_nao_revela_valor() -> None:
    encoded = hash_admin_pin("483726")
    assert "483726" not in encoded
    assert verify_admin_pin("483726", encoded) is True
    assert verify_admin_pin("483727", encoded) is False


def test_pin_admin_rejeita_formato_fraco_ou_invalido() -> None:
    for invalid in ("12345", "123456789", "abcdef", "111111", "12 3456", ""):
        with pytest.raises(ValueError):
            validate_admin_pin(invalid)


def test_pin_admin_sem_hash_configurado_falha_fechado() -> None:
    assert verify_admin_pin("483726", None) is False
