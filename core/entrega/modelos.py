"""Contratos puros da Expedição e Entrega V1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

from .erros import ErroEntrega


def _utc(valor: datetime | None) -> datetime | None:
    if valor is None:
        return None
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ErroEntrega("timestamp_invalido")
    return valor.astimezone(timezone.utc)


class StatusEntrega(StrEnum):
    AGUARDANDO_PRODUCAO = "aguardando_producao"
    AGUARDANDO_EXPEDICAO = "aguardando_expedicao"
    AGUARDANDO_ENTREGADOR = "aguardando_entregador"
    ATRIBUIDA = "atribuida"
    COLETADA = "coletada"
    EM_ROTA = "em_rota"
    TENTATIVA_FALHOU = "tentativa_falhou"
    ENTREGUE = "entregue"
    CANCELADA = "cancelada"


class ModalidadeEntrega(StrEnum):
    PROPRIA = "propria"
    PARCEIRO = "parceiro"
    RETIRADA = "retirada"


@dataclass(frozen=True)
class ChecklistExpedicao:
    itens_conferidos: bool
    embalagem_conferida: bool
    identificacao_conferida: bool
    observacao_operacional: str | None = None

    @property
    def completo(self) -> bool:
        return (
            self.itens_conferidos
            and self.embalagem_conferida
            and self.identificacao_conferida
        )

    def __post_init__(self) -> None:
        if self.observacao_operacional is not None:
            texto = self.observacao_operacional.strip()
            if not texto:
                raise ErroEntrega("observacao_vazia")
            if len(texto) > 500:
                raise ErroEntrega("observacao_excede_limite")
            object.__setattr__(self, "observacao_operacional", texto)


@dataclass(frozen=True)
class ProvaEntrega:
    referencia: str
    tipo: str
    registrada_em: datetime

    def __post_init__(self) -> None:
        referencia = self.referencia.strip()
        tipo = self.tipo.strip()
        if not referencia or len(referencia) > 255:
            raise ErroEntrega("prova_referencia_invalida")
        if not tipo or len(tipo) > 40:
            raise ErroEntrega("prova_tipo_invalido")
        object.__setattr__(self, "referencia", referencia)
        object.__setattr__(self, "tipo", tipo)
        object.__setattr__(self, "registrada_em", _utc(self.registrada_em))


@dataclass(frozen=True)
class TentativaEntrega:
    numero: int
    motivo: str
    registrada_em: datetime

    def __post_init__(self) -> None:
        motivo = self.motivo.strip()
        if self.numero < 1:
            raise ErroEntrega("tentativa_invalida")
        if not motivo or len(motivo) > 200:
            raise ErroEntrega("motivo_tentativa_invalido")
        object.__setattr__(self, "motivo", motivo)
        object.__setattr__(self, "registrada_em", _utc(self.registrada_em))


@dataclass(frozen=True)
class Entrega:
    entrega_id: str
    tenant_id: str
    unidade_id: str
    pedido_id: str
    endereco_id: str
    modalidade: ModalidadeEntrega
    status: StatusEntrega
    versao: int
    tentativa: int = 1
    entregador_id: str | None = None
    producao_pronta_em: datetime | None = None
    checklist_concluido_em: datetime | None = None
    atribuida_em: datetime | None = None
    coletada_em: datetime | None = None
    saiu_em: datetime | None = None
    entregue_em: datetime | None = None
    prova_entrega_ref: str | None = None

    def __post_init__(self) -> None:
        identificadores = (
            self.entrega_id,
            self.tenant_id,
            self.unidade_id,
            self.pedido_id,
            self.endereco_id,
        )
        if any(not valor.strip() for valor in identificadores):
            raise ErroEntrega("identificador_invalido")
        if self.versao < 1 or self.tentativa < 1:
            raise ErroEntrega("versao_ou_tentativa_invalida")
        if self.prova_entrega_ref is not None:
            prova = self.prova_entrega_ref.strip()
            if not prova or len(prova) > 255:
                raise ErroEntrega("prova_referencia_invalida")
            object.__setattr__(self, "prova_entrega_ref", prova)
        for campo in (
            "producao_pronta_em",
            "checklist_concluido_em",
            "atribuida_em",
            "coletada_em",
            "saiu_em",
            "entregue_em",
        ):
            object.__setattr__(self, campo, _utc(getattr(self, campo)))

        if self.status in {StatusEntrega.COLETADA, StatusEntrega.EM_ROTA, StatusEntrega.ENTREGUE}:
            if self.producao_pronta_em is None or self.checklist_concluido_em is None:
                raise ErroEntrega("custodia_sem_conferencia")
        if self.status is StatusEntrega.ENTREGUE:
            if self.entregue_em is None or not self.prova_entrega_ref:
                raise ErroEntrega("entrega_sem_prova")
