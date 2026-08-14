"""Modelos puros para configuração segura de serviços por cliente/unidade."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import TypeAlias

ValorParametro: TypeAlias = str | int | float | bool | None

_IDENTIFICADOR = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")
_CAMPOS_SECRETOS = (
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "client_secret",
    "password",
    "private_key",
    "refresh_token",
    "senha",
    "segredo",
    "token",
)


class ErroConfiguracaoServico(ValueError):
    """Erro seguro e estável da configuração de integrações."""


class AmbienteIntegracao(StrEnum):
    SANDBOX = "sandbox"
    HOMOLOGACAO = "homologacao"
    PRODUCAO = "producao"


class EstadoProntidaoServico(StrEnum):
    DESATIVADO = "desativado"
    BLOQUEADO = "bloqueado"
    CONFIGURADO = "configurado"
    PRONTO = "pronto"


def normalizar_identificador(valor: str, nome: str) -> str:
    normalizado = valor.strip().casefold()
    if not _IDENTIFICADOR.fullmatch(normalizado):
        raise ErroConfiguracaoServico(f"{nome}_invalido")
    return normalizado


def normalizar_parametros(
    parametros: Mapping[str, ValorParametro],
) -> tuple[tuple[str, ValorParametro], ...]:
    if len(parametros) > 64:
        raise ErroConfiguracaoServico("parametros_excedem_limite")
    resultado: list[tuple[str, ValorParametro]] = []
    for chave, valor in parametros.items():
        nome = normalizar_identificador(chave, "parametro")
        if any(marcador in nome for marcador in _CAMPOS_SECRETOS):
            raise ErroConfiguracaoServico("segredo_em_parametro_publico")
        if not isinstance(valor, (str, int, float, bool, type(None))):
            raise ErroConfiguracaoServico("valor_parametro_invalido")
        if isinstance(valor, str) and len(valor) > 2048:
            raise ErroConfiguracaoServico("valor_parametro_excede_limite")
        resultado.append((nome, valor.strip() if isinstance(valor, str) else valor))
    return tuple(sorted(resultado))


def normalizar_credenciais(
    credenciais: Mapping[str, str],
) -> tuple[tuple[str, str], ...]:
    if len(credenciais) > 16:
        raise ErroConfiguracaoServico("credenciais_excedem_limite")
    return tuple(
        sorted(
            (
                normalizar_identificador(papel, "papel_credencial"),
                normalizar_identificador(finalidade, "finalidade_credencial"),
            )
            for papel, finalidade in credenciais.items()
        )
    )


@dataclass(frozen=True, kw_only=True)
class ConfiguracaoServicoExterno:
    configuracao_id: str
    tenant_id: str
    unidade_id: str
    servico: str
    provedor: str
    conta_externa: str
    ambiente: AmbienteIntegracao
    parametros_publicos: tuple[tuple[str, ValorParametro], ...]
    finalidades_credenciais: tuple[tuple[str, str], ...]
    habilitada: bool
    homologada: bool
    evidencia_homologacao_ref: str | None
    versao: int
    atualizado_por: str
    correlation_id: str
    atualizado_em: datetime

    def __post_init__(self) -> None:
        for campo in (
            "configuracao_id",
            "tenant_id",
            "unidade_id",
            "servico",
            "provedor",
            "conta_externa",
            "atualizado_por",
            "correlation_id",
        ):
            valor = getattr(self, campo)
            if not isinstance(valor, str) or not valor.strip():
                raise ErroConfiguracaoServico(f"{campo}_obrigatorio")
        object.__setattr__(
            self, "servico", normalizar_identificador(self.servico, "servico")
        )
        object.__setattr__(
            self, "provedor", normalizar_identificador(self.provedor, "provedor")
        )
        if self.versao < 1:
            raise ErroConfiguracaoServico("versao_invalida")
        if self.atualizado_em.tzinfo is None or self.atualizado_em.utcoffset() is None:
            raise ErroConfiguracaoServico("timestamp_sem_timezone")
        object.__setattr__(
            self, "atualizado_em", self.atualizado_em.astimezone(timezone.utc)
        )
        if self.homologada and not (
            self.evidencia_homologacao_ref
            and self.evidencia_homologacao_ref.strip()
        ):
            raise ErroConfiguracaoServico("homologacao_sem_evidencia")

    @property
    def parametros(self) -> dict[str, ValorParametro]:
        return dict(self.parametros_publicos)

    @property
    def credenciais(self) -> dict[str, str]:
        return dict(self.finalidades_credenciais)


@dataclass(frozen=True, kw_only=True)
class ProntidaoServicoExterno:
    estado: EstadoProntidaoServico
    faltam_parametros: tuple[str, ...] = ()
    faltam_finalidades: tuple[str, ...] = ()
    faltam_credenciais: tuple[str, ...] = ()

    @property
    def pronto(self) -> bool:
        return self.estado is EstadoProntidaoServico.PRONTO
