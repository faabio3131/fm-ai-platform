"""Entrada multimodal normalizada do Agente Inteligente de Atendimento."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ModalidadeEntrada(StrEnum):
    TEXTO = "texto"
    AUDIO = "audio"


@dataclass(frozen=True, kw_only=True)
class EntradaAtendimento:
    mensagem_id: str
    modalidade: ModalidadeEntrada
    texto_original: str | None = None
    transcricao: str | None = None

    def __post_init__(self) -> None:
        if not self.mensagem_id.strip():
            raise ValueError("mensagem_id_obrigatorio")

        if self.modalidade is ModalidadeEntrada.TEXTO:
            if self.texto_original is None or not self.texto_original.strip():
                raise ValueError("texto_obrigatorio")

        if self.modalidade is ModalidadeEntrada.AUDIO:
            if self.transcricao is None or not self.transcricao.strip():
                raise ValueError("audio_exige_transcricao")

    @property
    def texto_para_interpretacao(self) -> str:
        if self.modalidade is ModalidadeEntrada.AUDIO:
            assert self.transcricao is not None
            return self.transcricao.strip()

        assert self.texto_original is not None
        return self.texto_original.strip()
