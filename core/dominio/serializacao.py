"""Serialização canônica sem perda de precisão."""

from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any


def para_primitivo(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return format(valor, "f")
    if isinstance(valor, datetime):
        return valor.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(valor, Enum):
        return valor.value
    if is_dataclass(valor):
        return {f.name: para_primitivo(getattr(valor, f.name)) for f in fields(valor)}
    if hasattr(valor, "para_dict"):
        return para_primitivo(valor.para_dict())
    if isinstance(valor, dict):
        return {str(k): para_primitivo(v) for k, v in sorted(valor.items())}
    if isinstance(valor, (list, tuple)):
        return [para_primitivo(v) for v in valor]
    return valor


class Serializavel:
    def para_dict(self) -> dict[str, Any]:
        return para_primitivo(self)
