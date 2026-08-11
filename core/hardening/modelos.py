"""Contratos puros do Gate E / hardening transversal da V1."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum


class ErroHardening(ValueError):
    """Erro de contrato do hardening com código estável."""


class NivelEvidencia(StrEnum):
    SINTETICA = "sintetica"
    HOMOLOGACAO = "homologacao"
    PRODUCAO = "producao"


class TipoEvidenciaGateE(StrEnum):
    TESTES = "testes"
    CARGA = "carga"
    CAOS_OFFLINE = "caos_offline"
    SEGURANCA = "seguranca"
    PRIVACIDADE = "privacidade"
    ACESSIBILIDADE = "acessibilidade"
    RESTORE = "restore"
    ROLLBACK = "rollback"
    SLO = "slo"
    RUNBOOK = "runbook"
    MIGRACAO_DRY_RUN = "migracao_dry_run"


TIPOS_OBRIGATORIOS_GATE_E: tuple[TipoEvidenciaGateE, ...] = tuple(TipoEvidenciaGateE)


class ModoDegradacao(StrEnum):
    FAIL_CLOSED = "fail_closed"
    DEGRADADO_SEGURO = "degradado_seguro"


@dataclass(frozen=True)
class EvidenciaGateE:
    evidencia_id: str
    tipo: TipoEvidenciaGateE
    nivel: NivelEvidencia
    aprovado: bool
    coletado_em: datetime
    artefato_ref: str
    artefato_sha256: str
    valido_ate: datetime | None = None
    observacao: str = ""

    def __post_init__(self) -> None:
        if not self.evidencia_id.strip() or not self.artefato_ref.strip():
            raise ErroHardening("evidencia_identificacao_invalida")
        if self.coletado_em.tzinfo is None or self.coletado_em.utcoffset() is None:
            raise ErroHardening("evidencia_timestamp_sem_timezone")
        object.__setattr__(self, "coletado_em", self.coletado_em.astimezone(timezone.utc))
        if self.valido_ate is not None:
            if self.valido_ate.tzinfo is None or self.valido_ate.utcoffset() is None:
                raise ErroHardening("evidencia_validade_sem_timezone")
            validade = self.valido_ate.astimezone(timezone.utc)
            if validade <= self.coletado_em:
                raise ErroHardening("evidencia_validade_invalida")
            object.__setattr__(self, "valido_ate", validade)
        sha = self.artefato_sha256.strip().lower()
        if len(sha) != 64 or any(ch not in "0123456789abcdef" for ch in sha):
            raise ErroHardening("evidencia_sha256_invalido")
        object.__setattr__(self, "artefato_sha256", sha)

    def expirada(self, agora: datetime) -> bool:
        if agora.tzinfo is None or agora.utcoffset() is None:
            raise ErroHardening("agora_sem_timezone")
        return self.valido_ate is not None and agora.astimezone(timezone.utc) > self.valido_ate


@dataclass(frozen=True)
class MetasSloV1:
    """Baseline inicial de homologação; produção requer aceite humano explícito."""

    disponibilidade_min_pct: float = 99.5
    latencia_p95_max_ms: int = 1500
    taxa_erro_max_pct: float = 1.0
    dlq_backlog_max: int = 0
    dlq_idade_max_segundos: int = 900
    rto_max_segundos: int = 1800
    rpo_max_segundos: int = 300

    def __post_init__(self) -> None:
        if not 0 < self.disponibilidade_min_pct <= 100:
            raise ErroHardening("slo_disponibilidade_invalida")
        if not 0 <= self.taxa_erro_max_pct <= 100:
            raise ErroHardening("slo_taxa_erro_invalida")
        inteiros = (
            self.latencia_p95_max_ms,
            self.dlq_backlog_max,
            self.dlq_idade_max_segundos,
            self.rto_max_segundos,
            self.rpo_max_segundos,
        )
        if any(valor < 0 for valor in inteiros):
            raise ErroHardening("slo_limite_negativo")


@dataclass(frozen=True)
class AmostraSlo:
    disponibilidade_pct: float
    latencia_p95_ms: int
    taxa_erro_pct: float
    dlq_backlog: int
    dlq_idade_segundos: int
    rto_segundos: int
    rpo_segundos: int

    def __post_init__(self) -> None:
        if not 0 <= self.disponibilidade_pct <= 100:
            raise ErroHardening("amostra_disponibilidade_invalida")
        if not 0 <= self.taxa_erro_pct <= 100:
            raise ErroHardening("amostra_taxa_erro_invalida")
        inteiros = (
            self.latencia_p95_ms,
            self.dlq_backlog,
            self.dlq_idade_segundos,
            self.rto_segundos,
            self.rpo_segundos,
        )
        if any(valor < 0 for valor in inteiros):
            raise ErroHardening("amostra_slo_negativa")


@dataclass(frozen=True)
class ResultadoSlo:
    aprovado: bool
    violacoes: tuple[str, ...]


@dataclass(frozen=True)
class SnapshotIntegridade:
    """Baseline mínimo para restore/reconciliação sem transportar PII."""

    contagens: Mapping[str, int]
    somas_centavos: Mapping[str, int]
    checksums: Mapping[str, str]

    def __post_init__(self) -> None:
        if not self.contagens or not self.checksums:
            raise ErroHardening("snapshot_integridade_incompleto")
        if any(valor < 0 for valor in self.contagens.values()):
            raise ErroHardening("snapshot_contagem_negativa")
        for nome, checksum in self.checksums.items():
            if not nome.strip() or len(checksum.strip()) < 8:
                raise ErroHardening("snapshot_checksum_invalido")


@dataclass(frozen=True)
class ResultadoRestore:
    aprovado: bool
    divergencias: tuple[str, ...]


@dataclass(frozen=True)
class ResultadoCaos:
    cenario: str
    modo_esperado: ModoDegradacao
    falha_injetada: bool
    recuperou: bool
    recuperacao_segundos: int
    limite_recuperacao_segundos: int
    perda_dados: bool = False
    efeitos_duplicados: bool = False

    def __post_init__(self) -> None:
        if not self.cenario.strip():
            raise ErroHardening("cenario_caos_invalido")
        if self.recuperacao_segundos < 0 or self.limite_recuperacao_segundos < 0:
            raise ErroHardening("tempo_caos_invalido")

    @property
    def aprovado(self) -> bool:
        return (
            self.falha_injetada
            and self.recuperou
            and not self.perda_dados
            and not self.efeitos_duplicados
            and self.recuperacao_segundos <= self.limite_recuperacao_segundos
        )


@dataclass(frozen=True)
class DecisaoGateE:
    aprovado: bool
    bloqueios: tuple[str, ...]
    avisos: tuple[str, ...]
    evidencias_validas: tuple[TipoEvidenciaGateE, ...]
