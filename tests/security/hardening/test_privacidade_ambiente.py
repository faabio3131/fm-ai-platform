from __future__ import annotations

import pytest

from core.hardening import (
    ErroHardening,
    encontrar_campos_sensiveis,
    exigir_destino_nao_producao,
    exigir_payload_minimizado,
)


def test_payload_de_auditoria_rejeita_pii_e_segredo_mesmo_aninhados() -> None:
    payload = {
        "tenant_id": "t1",
        "pedido_id": "p1",
        "detalhes": [
            {"cliente_ref": "hash"},
            {"authorization": "Bearer abc"},
            {"contato": {"email": "cliente@example.com"}},
        ],
    }
    encontrados = encontrar_campos_sensiveis(payload)
    assert "$.detalhes[1].authorization" in encontrados
    assert "$.detalhes[2].contato.email" in encontrados
    with pytest.raises(ValueError, match="payload_contem_pii_ou_segredo"):
        exigir_payload_minimizado(payload)


def test_payload_com_referencias_hash_e_ids_opacos_e_permitido() -> None:
    exigir_payload_minimizado(
        {
            "tenant_id": "tenant-1",
            "unidade_id": "unidade-1",
            "pedido_id": "pedido-1",
            "cliente_ref": "opaque-123",
            "telefone_hash": "a" * 64,
            "segredo_ref": "vault://ifood/producao",
            "payload_hash": "b" * 64,
        }
    )


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://database.prod.internal/fm_ai",
        "postgresql://db.example.net/fm_ai",
        "mysql://cluster.rds.amazonaws.com/fm_ai",
        "postgresql://instance.database.windows.net/fm_ai",
    ],
)
def test_restore_e_migracao_nao_apontam_para_destino_remoto_por_padrao(url: str) -> None:
    with pytest.raises(ErroHardening, match="destino_banco_bloqueado"):
        exigir_destino_nao_producao(url)
