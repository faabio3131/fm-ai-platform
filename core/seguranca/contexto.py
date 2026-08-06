"""Contexto imutavel derivado de identidade autenticada."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.dominio.serializacao import Serializavel, para_primitivo

from .erros import ContextoAusente, IdentidadeSistemaInvalida
from .permissoes import Papel, Permissao


def _obrigatorio(valor: str, nome: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ContextoAusente(f"{nome} obrigatorio")
    return valor.strip()


@dataclass(frozen=True)
class ContextoExecucao(Serializavel):
    tenant_id: str
    unidade_id: str
    usuario_id: str
    papeis: frozenset[Papel]
    permissoes: frozenset[Permissao]
    correlation_id: str
    solicitado_em: datetime
    origem: str
    causation_id: str | None = None
    request_id: str | None = None
    ip_protegido: str | None = None
    metadata: tuple[tuple[str, Any], ...] = field(default_factory=tuple)
    unidades_permitidas: frozenset[str] = field(default_factory=frozenset)
    identidade_sistema: bool = False
    motivo_sistema: str | None = None

    def __post_init__(self) -> None:
        for nome in (
            "tenant_id",
            "unidade_id",
            "usuario_id",
            "correlation_id",
            "origem",
        ):
            object.__setattr__(self, nome, _obrigatorio(getattr(self, nome), nome))
        if self.solicitado_em.tzinfo is None or self.solicitado_em.utcoffset() is None:
            raise ContextoAusente("solicitado_em deve conter timezone")
        object.__setattr__(
            self, "solicitado_em", self.solicitado_em.astimezone(timezone.utc)
        )
        if self.identidade_sistema and not (
            self.motivo_sistema and self.motivo_sistema.strip()
        ):
            raise IdentidadeSistemaInvalida("Identidade tecnica exige motivo auditavel")

    @classmethod
    def sistema(
        cls,
        *,
        identidade: str,
        motivo: str,
        tenant_id: str,
        unidade_id: str,
        correlation_id: str,
        solicitado_em: datetime,
    ) -> "ContextoExecucao":
        if not identidade.strip() or not motivo.strip():
            raise IdentidadeSistemaInvalida(
                "Identidade tecnica e motivo sao obrigatorios"
            )
        return cls(
            tenant_id,
            unidade_id,
            identidade,
            frozenset(),
            frozenset(),
            correlation_id,
            solicitado_em,
            "sistema",
            unidades_permitidas=frozenset({unidade_id}),
            identidade_sistema=True,
            motivo_sistema=motivo,
        )

    def para_dict(self) -> dict[str, Any]:
        return para_primitivo(
            {
                "tenant_id": self.tenant_id,
                "unidade_id": self.unidade_id,
                "usuario_id": self.usuario_id,
                "papeis": sorted(self.papeis),
                "permissoes": sorted(self.permissoes),
                "correlation_id": self.correlation_id,
                "causation_id": self.causation_id,
                "solicitado_em": self.solicitado_em,
                "origem": self.origem,
                "request_id": self.request_id,
                "ip_protegido": self.ip_protegido,
                "metadata": dict(self.metadata),
            }
        )
