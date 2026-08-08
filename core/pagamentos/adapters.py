"""Contrato de provedor e sandbox deterministico, sem I/O externo."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from core.dominio.dinheiro import Dinheiro


@dataclass(frozen=True)
class CobrancaProvedor:
    id_externo: str
    status: str
    valor: Dinheiro
    payload_exibicao: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class WebhookNormalizado:
    provedor: str
    evento_externo: str
    id_externo: str
    tipo: str
    valor: Dinheiro
    timestamp: datetime
    assinatura_validada: bool
    idempotency_key: str


class AdapterProvedorPagamento(Protocol):
    def criar_cobranca(
        self, *, pagamento_id: str, valor: Dinheiro, idempotency_key: str
    ) -> CobrancaProvedor: ...
    def consultar_transacao(self, id_externo: str) -> CobrancaProvedor | None: ...
    def normalizar_webhook(self, payload: dict[str, Any]) -> WebhookNormalizado: ...
    def reconciliar(self) -> tuple[CobrancaProvedor, ...]: ...


class ProvedorPagamentoFake:
    nome = "sandbox"

    def __init__(self) -> None:
        self._cobrancas: dict[str, CobrancaProvedor] = {}

    def criar_cobranca(
        self, *, pagamento_id: str, valor: Dinheiro, idempotency_key: str
    ) -> CobrancaProvedor:
        cobranca = CobrancaProvedor(
            f"sandbox-{pagamento_id}-{idempotency_key}", "pendente", valor
        )
        self._cobrancas.setdefault(cobranca.id_externo, cobranca)
        return self._cobrancas[cobranca.id_externo]

    def definir_status(self, id_externo: str, status: str) -> None:
        atual = self._cobrancas[id_externo]
        self._cobrancas[id_externo] = CobrancaProvedor(
            atual.id_externo, status, atual.valor, atual.payload_exibicao
        )

    def consultar_transacao(self, id_externo: str) -> CobrancaProvedor | None:
        return self._cobrancas.get(id_externo)

    def normalizar_webhook(self, payload: dict[str, Any]) -> WebhookNormalizado:
        return WebhookNormalizado(
            self.nome,
            str(payload["evento_externo"]),
            str(payload["id_externo"]),
            str(payload["tipo"]),
            Dinheiro(payload["valor"]),
            payload["timestamp"],
            payload.get("assinatura_validada") is True,
            str(payload["idempotency_key"]),
        )

    def reconciliar(self) -> tuple[CobrancaProvedor, ...]:
        return tuple(sorted(self._cobrancas.values(), key=lambda c: c.id_externo))
