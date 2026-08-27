"""Modelos imutáveis da autoridade de notificações internas."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CanalNotificacaoInterna(StrEnum):
    WHATSAPP = "whatsapp"


@dataclass(frozen=True)
class DestinatarioNotificacaoInterna:
    destinatario_id: str
    tenant_id: str
    unidade_id: str
    nome_exibicao: str
    cargo: str | None
    canal: CanalNotificacaoInterna
    referencia_contato: str
    contato_mascara: str
    receber_alertas_estoque: bool
    ativo: bool
    versao: int = 1

    def __post_init__(self) -> None:
        obrigatorios = {
            "destinatario_id": self.destinatario_id,
            "tenant_id": self.tenant_id,
            "unidade_id": self.unidade_id,
            "nome_exibicao": self.nome_exibicao,
            "referencia_contato": self.referencia_contato,
            "contato_mascara": self.contato_mascara,
        }
        for nome, valor in obrigatorios.items():
            if not isinstance(valor, str) or not valor.strip():
                raise ValueError(f"{nome} obrigatorio")
            object.__setattr__(self, nome, valor.strip())
        if not self.referencia_contato.startswith("internal-contact://"):
            raise ValueError("referencia de contato interno invalida")
        if self.versao < 1:
            raise ValueError("versao de destinatario invalida")
        if self.cargo is not None:
            cargo = self.cargo.strip()
            object.__setattr__(self, "cargo", cargo or None)
