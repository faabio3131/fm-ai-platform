"""Contratos tipados do Gerente IA Operacional V1."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from json import dumps
from typing import Any

from .erros import ErroGerenteIA

ValorPrimitivo = str | int | float | bool | None


class ToolGerenteIA(StrEnum):
    CONSULTAR_PEDIDOS = "consultar_pedidos"
    CONSULTAR_ATRASOS = "consultar_atrasos"
    CONSULTAR_MESAS = "consultar_mesas"
    CONSULTAR_COZINHA = "consultar_cozinha"
    CONSULTAR_ENTREGAS = "consultar_entregas"
    CONSULTAR_ESTOQUE = "consultar_estoque"
    SUGERIR_COMPRA = "sugerir_compra"
    GERAR_RELATORIO = "gerar_relatorio"
    PREPARAR_CAMPANHA = "preparar_campanha"
    ACOMPANHAR_CONVERSAO = "acompanhar_conversao"
    PRIORIZAR_PEDIDO = "priorizar_pedido"
    PAUSAR_PRODUTO = "pausar_produto"


class NaturezaTool(StrEnum):
    CONSULTA = "consulta"
    RASCUNHO = "rascunho"
    ACAO_COM_CONFIRMAR = "acao_com_confirmar"


class StatusPreview(StrEnum):
    PENDENTE = "pendente"
    EXECUTANDO = "executando"
    EXECUTADO = "executado"
    EXPIRADO = "expirado"
    CANCELADO = "cancelado"


class StatusCampanha(StrEnum):
    RASCUNHO = "rascunho"
    APROVADA = "aprovada"
    PUBLICAVEL = "publicavel"


@dataclass(frozen=True)
class CampanhaRef:
    """Referência opaca e versionada para uma campanha humana já publicável."""

    valor: str

    def __post_init__(self) -> None:
        valor = self.valor.strip()
        prefixo = "campanha://v1/"
        if not valor.startswith(prefixo):
            raise ErroGerenteIA("campanha_ref_invalida")
        campanha_id, separador, fingerprint = valor[len(prefixo):].partition("/")
        if (
            not separador
            or not campanha_id
            or len(fingerprint) != 64
            or any(ch not in "0123456789abcdef" for ch in fingerprint)
        ):
            raise ErroGerenteIA("campanha_ref_invalida")
        object.__setattr__(self, "valor", valor)

    @classmethod
    def de_publicacao(cls, *, campanha_id: str, fingerprint: str) -> CampanhaRef:
        campanha = campanha_id.strip()
        digest = fingerprint.strip().casefold()
        if (
            not campanha
            or len(digest) != 64
            or any(ch not in "0123456789abcdef" for ch in digest)
        ):
            raise ErroGerenteIA("campanha_ref_invalida")
        return cls(f"campanha://v1/{campanha}/{digest}")

    def __str__(self) -> str:
        return self.valor


@dataclass(frozen=True)
class ChamadaTool:
    tool: ToolGerenteIA
    argumentos: tuple[tuple[str, ValorPrimitivo], ...] = field(default_factory=tuple)
    request_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tool, ToolGerenteIA):
            raise ErroGerenteIA("tool_nao_permitida")
        vistos: set[str] = set()
        normalizados: list[tuple[str, ValorPrimitivo]] = []
        for chave, valor in self.argumentos:
            if not isinstance(chave, str) or not chave.strip():
                raise ErroGerenteIA("argumento_invalido")
            chave = chave.strip()
            if chave in vistos:
                raise ErroGerenteIA("argumento_duplicado")
            if not isinstance(valor, (str, int, float, bool, type(None))):
                raise ErroGerenteIA("argumento_tipo_nao_suportado")
            vistos.add(chave)
            normalizados.append((chave, valor))
        object.__setattr__(self, "argumentos", tuple(sorted(normalizados)))
        if self.request_id is not None and not self.request_id.strip():
            raise ErroGerenteIA("request_id_invalido")

    @classmethod
    def de_dict(
        cls,
        tool: ToolGerenteIA | str,
        argumentos: dict[str, ValorPrimitivo] | None = None,
        *,
        request_id: str | None = None,
    ) -> ChamadaTool:
        try:
            tool_enum = tool if isinstance(tool, ToolGerenteIA) else ToolGerenteIA(tool)
        except ValueError as exc:
            raise ErroGerenteIA("tool_nao_permitida") from exc
        return cls(tool_enum, tuple((argumentos or {}).items()), request_id)

    def args(self) -> dict[str, ValorPrimitivo]:
        return dict(self.argumentos)


@dataclass(frozen=True)
class RegistroGerencial:
    tipo: str
    campos: tuple[tuple[str, ValorPrimitivo], ...]

    def __post_init__(self) -> None:
        if not self.tipo.strip():
            raise ErroGerenteIA("registro_tipo_obrigatorio")
        object.__setattr__(self, "campos", tuple(sorted(self.campos)))

    def para_dict(self) -> dict[str, ValorPrimitivo]:
        return dict(self.campos)


@dataclass(frozen=True)
class ResultadoTool:
    tool: ToolGerenteIA
    natureza: NaturezaTool
    registros: tuple[RegistroGerencial, ...]
    correlation_id: str
    conteudo_nao_confiavel: bool = True
    observacao: str | None = None


@dataclass(frozen=True)
class RascunhoCampanha:
    rascunho_id: str
    tenant_id: str
    unidade_id: str
    canal: str
    finalidade: str
    objetivo: str
    texto_base: str
    audiencia_elegivel: int
    criado_em: datetime
    criado_por: str
    status: str = "rascunho"

    def __post_init__(self) -> None:
        if self.status != "rascunho":
            raise ErroGerenteIA("campanha_deve_permanecer_rascunho")
        if self.audiencia_elegivel < 0:
            raise ErroGerenteIA("audiencia_invalida")
        if self.criado_em.tzinfo is None or self.criado_em.utcoffset() is None:
            raise ErroGerenteIA("timestamp_sem_timezone")
        object.__setattr__(self, "criado_em", self.criado_em.astimezone(timezone.utc))

    @property
    def fingerprint(self) -> str:
        return fingerprint_campanha(
            campanha_id=self.rascunho_id,
            tenant_id=self.tenant_id,
            unidade_id=self.unidade_id,
            canal=self.canal,
            finalidade=self.finalidade,
            objetivo=self.objetivo,
            texto_base=self.texto_base,
            audiencia_elegivel=self.audiencia_elegivel,
        )


def fingerprint_campanha(
    *,
    campanha_id: str,
    tenant_id: str,
    unidade_id: str,
    canal: str,
    finalidade: str,
    objetivo: str,
    texto_base: str,
    audiencia_elegivel: int,
) -> str:
    payload = {
        "campanha_id": campanha_id.strip(),
        "tenant_id": tenant_id.strip(),
        "unidade_id": unidade_id.strip(),
        "canal": canal.strip(),
        "finalidade": finalidade.strip(),
        "objetivo": objetivo.strip(),
        "texto_base": texto_base,
        "audiencia_elegivel": audiencia_elegivel,
    }
    if any(
        not str(payload[chave]).strip()
        for chave in (
            "campanha_id",
            "tenant_id",
            "unidade_id",
            "canal",
            "finalidade",
            "objetivo",
            "texto_base",
        )
    ):
        raise ErroGerenteIA("campanha_invalida")
    if audiencia_elegivel < 0:
        raise ErroGerenteIA("audiencia_invalida")
    serializado = dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return sha256(serializado.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CampanhaAprovada:
    campanha_id: str
    tenant_id: str
    unidade_id: str
    fingerprint: str
    aprovado_por: str
    aprovado_em: datetime
    idempotency_key: str
    idempotente: bool = False
    status: StatusCampanha = StatusCampanha.APROVADA

    def __post_init__(self) -> None:
        if any(
            not valor.strip()
            for valor in (
                self.campanha_id,
                self.tenant_id,
                self.unidade_id,
                self.aprovado_por,
                self.idempotency_key,
            )
        ):
            raise ErroGerenteIA("aprovacao_campanha_invalida")
        if len(self.fingerprint) != 64 or any(
            ch not in "0123456789abcdef" for ch in self.fingerprint
        ):
            raise ErroGerenteIA("fingerprint_campanha_invalido")
        if self.aprovado_em.tzinfo is None or self.aprovado_em.utcoffset() is None:
            raise ErroGerenteIA("timestamp_sem_timezone")
        object.__setattr__(
            self, "aprovado_em", self.aprovado_em.astimezone(timezone.utc)
        )


@dataclass(frozen=True)
class CampanhaPublicavel:
    campanha_id: str
    tenant_id: str
    unidade_id: str
    fingerprint: str
    campanha_ref: CampanhaRef
    publicado_por: str
    publicado_em: datetime
    idempotency_key: str
    idempotente: bool = False
    status: StatusCampanha = StatusCampanha.PUBLICAVEL

    def __post_init__(self) -> None:
        if any(
            not valor.strip()
            for valor in (
                self.campanha_id,
                self.tenant_id,
                self.unidade_id,
                self.publicado_por,
                self.idempotency_key,
            )
        ):
            raise ErroGerenteIA("publicacao_campanha_invalida")
        if len(self.fingerprint) != 64 or any(
            ch not in "0123456789abcdef" for ch in self.fingerprint
        ):
            raise ErroGerenteIA("fingerprint_campanha_invalido")
        if self.publicado_em.tzinfo is None or self.publicado_em.utcoffset() is None:
            raise ErroGerenteIA("timestamp_sem_timezone")
        object.__setattr__(
            self, "publicado_em", self.publicado_em.astimezone(timezone.utc)
        )


@dataclass(frozen=True)
class PreviewAcao:
    preview_id: str
    tenant_id: str
    unidade_id: str
    tool: ToolGerenteIA
    recurso_id: str
    argumentos: tuple[tuple[str, ValorPrimitivo], ...]
    impacto: RegistroGerencial
    motivo: str
    criado_por: str
    criado_em: datetime
    expira_em: datetime
    fingerprint: str
    status: StatusPreview = StatusPreview.PENDENTE

    def __post_init__(self) -> None:
        if self.tool not in {
            ToolGerenteIA.PRIORIZAR_PEDIDO,
            ToolGerenteIA.PAUSAR_PRODUTO,
        }:
            raise ErroGerenteIA("preview_tool_invalida")
        if not self.recurso_id.strip() or not self.motivo.strip():
            raise ErroGerenteIA("preview_invalido")
        if self.criado_em.tzinfo is None or self.expira_em.tzinfo is None:
            raise ErroGerenteIA("timestamp_sem_timezone")
        criado = self.criado_em.astimezone(timezone.utc)
        expira = self.expira_em.astimezone(timezone.utc)
        if expira <= criado:
            raise ErroGerenteIA("preview_expiracao_invalida")
        object.__setattr__(self, "criado_em", criado)
        object.__setattr__(self, "expira_em", expira)
        object.__setattr__(self, "argumentos", tuple(sorted(self.argumentos)))
        if self.fingerprint != fingerprint_preview(
            tenant_id=self.tenant_id,
            unidade_id=self.unidade_id,
            tool=self.tool,
            recurso_id=self.recurso_id,
            argumentos=self.argumentos,
            impacto=self.impacto,
            motivo=self.motivo,
            criado_por=self.criado_por,
        ):
            raise ErroGerenteIA("preview_fingerprint_invalido")


@dataclass(frozen=True)
class ResultadoAcao:
    preview_id: str
    tool: ToolGerenteIA
    recurso_id: str
    resultado: str
    executado_por: str
    executado_em: datetime
    idempotency_key: str
    idempotente: bool = False

    def __post_init__(self) -> None:
        if self.executado_em.tzinfo is None or self.executado_em.utcoffset() is None:
            raise ErroGerenteIA("timestamp_sem_timezone")
        object.__setattr__(self, "executado_em", self.executado_em.astimezone(timezone.utc))


def fingerprint_preview(
    *,
    tenant_id: str,
    unidade_id: str,
    tool: ToolGerenteIA,
    recurso_id: str,
    argumentos: tuple[tuple[str, ValorPrimitivo], ...],
    impacto: RegistroGerencial,
    motivo: str,
    criado_por: str,
) -> str:
    payload: dict[str, Any] = {
        "tenant_id": tenant_id,
        "unidade_id": unidade_id,
        "tool": tool.value,
        "recurso_id": recurso_id,
        "argumentos": sorted(argumentos),
        "impacto": {"tipo": impacto.tipo, "campos": list(impacto.campos)},
        "motivo": motivo,
        "criado_por": criado_por,
    }
    serializado = dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256(serializado.encode("utf-8")).hexdigest()
