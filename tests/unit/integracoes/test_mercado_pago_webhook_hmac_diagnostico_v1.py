from __future__ import annotations

from scripts.mercado_pago_webhook_hmac_diagnostico_app import (
    _diagnosticar_variantes,
    _estrutura_hmac,
    _hmac_hex,
    _parse_x_signature,
)


def test_parser_preserva_estrutura_sem_expor_valores() -> None:
    ts, v1, chaves, ts_count, v1_count = _parse_x_signature(
        "ts=1720000000000, v1=abcdef012345"
    )
    assert ts == "1720000000000"
    assert v1 == "abcdef012345"
    assert chaves == ("ts", "v1")
    assert ts_count == 1
    assert v1_count == 1


def test_diagnostico_detecta_manifesto_exato() -> None:
    secret = "segredo-apenas-de-teste"
    data_id = "ORDTST01ABCDEF"
    request_id = "0f2e48e3-7be9-4da6-91e4-2f2e2a2a2a2a"
    ts = "1720000000000"
    manifesto = f"id:{data_id};request-id:{request_id};ts:{ts};"
    recebido = _hmac_hex(secret, manifesto)

    matches = _diagnosticar_variantes(
        secret=secret,
        data_id=data_id,
        request_id=request_id,
        ts=ts,
        recebido=recebido,
    )
    estrutura = _estrutura_hmac(
        secret=secret,
        data_id=data_id,
        request_id=request_id,
        ts=ts,
        recebido=recebido,
    )

    assert "full_exact_exact" in matches
    assert estrutura["v1_len"] == 64
    assert estrutura["v1_hex"] is True
    assert estrutura["ts_so_digitos"] is True
    assert estrutura["v1_recebido_fp"] == estrutura["hmac_exato_fp"]
    assert secret not in str(estrutura)
    assert data_id not in str(estrutura)
    assert request_id not in str(estrutura)
    assert ts not in str(estrutura)


def test_diagnostico_fingerprints_divergem_quando_hmac_nao_bate() -> None:
    estrutura = _estrutura_hmac(
        secret="segredo-apenas-de-teste",
        data_id="ORDTST01ABCDEF",
        request_id="0f2e48e3-7be9-4da6-91e4-2f2e2a2a2a2a",
        ts="1720000000000",
        recebido="0" * 64,
    )
    assert estrutura["v1_recebido_fp"] != estrutura["hmac_exato_fp"]
