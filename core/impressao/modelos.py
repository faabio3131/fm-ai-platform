"""Contratos imutáveis da Impressão por Setor V1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum


class StatusImpressao(StrEnum):
    PENDENTE = "pendente"
    FALHOU = "falhou"
    IMPRESSO = "impresso"
    CONTINGENCIA = "contingencia"


@dataclass(frozen=True)
class DestinoImpressao:
    tenant_id: str
    unidade_id: str
    setor_id: str
    impressora_id: str
    ativo: bool = True
    max_tentativas: int = 3

    def __post_init__(self) -> None:
        if not all(
            valor.strip()
            for valor in (
                self.tenant_id,
                self.unidade_id,
                self.setor_id,
                self.impressora_id,
            )
        ):
            raise ValueError("destino_impressao_invalido")
        if self.max_tentativas < 1 or self.max_tentativas > 10:
            raise ValueError("max_tentativas_invalido")


@dataclass(frozen=True)
class JobImpressao:
    job_id: str
    tenant_id: str
    unidade_id: str
    setor_id: str
    producao_id: str
    pedido_id: str
    pedido_item_id: str
    impressora_id: str
    dedup_key: str
    documento_hash: str
    conteudo: str
    status: StatusImpressao
    tentativa: int
    max_tentativas: int
    versao: int
    criado_em: datetime
    atualizado_em: datetime
    ultimo_erro: str | None = None
    reimpressao_de: str | None = None
    motivo_reimpressao: str | None = None

    def __post_init__(self) -> None:
        if not all(
            valor.strip()
            for valor in (
                self.job_id,
                self.tenant_id,
                self.unidade_id,
                self.setor_id,
                self.producao_id,
                self.pedido_id,
                self.pedido_item_id,
                self.impressora_id,
                self.dedup_key,
                self.documento_hash,
                self.conteudo,
            )
        ):
            raise ValueError("job_impressao_invalido")
        if self.tentativa < 0 or self.max_tentativas < 1 or self.versao < 1:
            raise ValueError("job_impressao_invalido")
        if self.tentativa > self.max_tentativas:
            raise ValueError("tentativa_impressao_invalida")
        for campo in ("criado_em", "atualizado_em"):
            instante = getattr(self, campo)
            if instante.tzinfo is None or instante.utcoffset() is None:
                raise ValueError("timestamp_invalido")
            object.__setattr__(self, campo, instante.astimezone(timezone.utc))
        if self.reimpressao_de and not (
            self.motivo_reimpressao and self.motivo_reimpressao.strip()
        ):
            raise ValueError("motivo_reimpressao_obrigatorio")


@dataclass(frozen=True)
class ResultadoEnfileiramento:
    job: JobImpressao | None
    enfileirado: bool
    deduplicado: bool
    motivo: str


@dataclass(frozen=True)
class ResultadoProcessamento:
    job: JobImpressao
    impresso: bool
    contingencia: bool
