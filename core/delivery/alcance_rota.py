"""Política determinística de alcance por percurso, nunca raio geográfico."""
from __future__ import annotations

from dataclasses import dataclass
from core.delivery.erros import ErroDelivery


@dataclass(frozen=True)
class AlcanceEntrega:
    tenant_id: str
    unidade_id: str
    limite_km: int

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.unidade_id or not 1 <= self.limite_km <= 200:
            raise ErroDelivery("alcance_entrega_invalido")

    def validar_rota(self, distancia_metros: int | None) -> None:
        if distancia_metros is None or distancia_metros < 0:
            raise ErroDelivery("rota_indisponivel_exige_gestor_entregador")
        if distancia_metros > self.limite_km * 1000:
            raise ErroDelivery("fora_do_alcance_entrega")
