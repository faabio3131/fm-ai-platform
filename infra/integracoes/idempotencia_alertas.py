"""Chaves determinísticas para alertas comerciais disparados por integrações.

A mesma ocorrência no mesmo dia deve reutilizar a chave; ocorrências distintas
para o mesmo destinatário precisam de chaves diferentes para não serem tratadas
como duplicadas pelo provedor.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from hashlib import sha256
from typing import Any


def chave_idempotencia_alerta_estoque(
    *,
    contato_id: int | str,
    alerta: Mapping[str, Any],
    data_referencia: date,
) -> str:
    payload = json.dumps(
        {
            "contato_id": str(contato_id),
            "data": data_referencia.isoformat(),
            "insumo": str(alerta.get("insumo", "")).strip(),
            "previsao": str(alerta.get("previsao_esgotamento", "")).strip(),
            "mensagem": str(alerta.get("mensagem_alerta", "")).strip(),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    fingerprint = sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"estoque-{contato_id}-{data_referencia.isoformat()}-{fingerprint}"

