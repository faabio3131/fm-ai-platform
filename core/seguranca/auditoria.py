"""Contrato de auditoria minimizada; persistencia somente in-memory."""

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Protocol

from core.dominio.serializacao import Serializavel, para_primitivo

from .erros import MetadataAuditoriaInvalida
from .permissoes import Papel

CAMPOS_PROIBIDOS = frozenset(
    {
        "senha",
        "password",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "cartao",
        "card_payload",
        "pix",
        "telefone",
        "secret",
        "segredo",
    }
)


def sanitizar_metadata(
    metadata: dict[str, Any] | None, *, rejeitar: bool = False
) -> tuple[tuple[str, Any], ...]:
    seguros: list[tuple[str, Any]] = []
    for chave, valor in (metadata or {}).items():
        normalizada = chave.lower().replace("-", "_")
        if any(proibido in normalizada for proibido in CAMPOS_PROIBIDOS):
            if rejeitar:
                raise MetadataAuditoriaInvalida("Metadata contem campo nao permitido")
            continue
        if isinstance(valor, (str, int, bool, float, type(None))):
            seguros.append((chave, valor))
    return tuple(sorted(seguros))


@dataclass(frozen=True)
class EventoAuditoria(Serializavel):
    audit_id: str
    tenant_id: str
    unidade_id: str
    usuario_id: str
    papel_efetivo: Papel | None
    acao: str
    recurso_tipo: str
    recurso_id: str | None
    resultado: str
    motivo: str
    correlation_id: str
    timestamp: datetime
    origem: str
    politica: str
    versao: int = 1
    causation_id: str | None = None
    antes_resumido: tuple[tuple[str, Any], ...] = field(default_factory=tuple)
    depois_resumido: tuple[tuple[str, Any], ...] = field(default_factory=tuple)
    metadata: tuple[tuple[str, Any], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.correlation_id.strip() or self.timestamp.tzinfo is None:
            raise MetadataAuditoriaInvalida(
                "Auditoria exige correlation e timestamp timezone-aware"
            )
        object.__setattr__(self, "timestamp", self.timestamp.astimezone(timezone.utc))

    def para_dict(self) -> dict[str, Any]:
        dados = {campo: getattr(self, campo) for campo in self.__dataclass_fields__}
        for campo in ("antes_resumido", "depois_resumido", "metadata"):
            dados[campo] = dict(dados[campo])
        return para_primitivo(dados)


class RepositorioAuditoria(Protocol):
    def adicionar(self, evento: EventoAuditoria) -> None: ...


class RepositorioAuditoriaEmMemoria:
    def __init__(self) -> None:
        self.eventos: list[EventoAuditoria] = []

    def adicionar(self, evento: EventoAuditoria) -> None:
        self.eventos.append(replace(evento))
