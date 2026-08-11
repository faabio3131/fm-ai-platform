"""Contratos imutáveis do CRM e conversão consentida V1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum

from core.marketplaces.modelos import PlataformaMarketplace

from .erros import ErroCRM

CENTAVO = Decimal("0.01")


def moeda(valor: Decimal | str | int) -> Decimal:
    convertido = Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    if convertido < 0:
        raise ErroCRM("valor_monetario_negativo")
    return convertido


def utc(valor: datetime) -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ErroCRM("timestamp_sem_timezone")
    return valor.astimezone(timezone.utc)


def _hash_hex(valor: str, *, codigo: str) -> str:
    normalizado = valor.strip().lower()
    if len(normalizado) != 64 or any(ch not in "0123456789abcdef" for ch in normalizado):
        raise ErroCRM(codigo)
    return normalizado


class CanalMarketing(StrEnum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    SMS = "sms"


class FinalidadeMarketing(StrEnum):
    PROMOCOES = "promocoes"
    FIDELIDADE = "fidelidade"


class StatusConsentimento(StrEnum):
    CONCEDIDO = "concedido"
    REVOGADO = "revogado"


class BaseLegalMarketing(StrEnum):
    CONSENTIMENTO = "consentimento"


class OrigemClienteCRM(StrEnum):
    DELIVERY_PROPRIO = "delivery_proprio"
    MARKETPLACE_CONVERTIDO = "marketplace_convertido"
    LEGADO_REGULARIZADO = "legado_regularizado"
    MANUAL = "manual"


class EtapaFunilCRM(StrEnum):
    MARKETPLACE_RESTRITO = "marketplace_restrito"
    CONSENTIMENTO_CONCEDIDO = "consentimento_concedido"
    CONVERTIDO = "convertido"
    BENEFICIO_EMITIDO = "beneficio_emitido"
    OPT_OUT = "opt_out"


class TipoBeneficioCRM(StrEnum):
    CUPOM = "cupom"
    CASHBACK = "cashback"


@dataclass(frozen=True)
class ContatoCRM:
    canal: CanalMarketing
    referencia: str

    def __post_init__(self) -> None:
        referencia = self.referencia.strip()
        if not referencia.startswith(("contact://", "vault://")):
            raise ErroCRM("contato_deve_ser_referencia_segura")
        object.__setattr__(self, "referencia", referencia)


@dataclass(frozen=True)
class ClienteCRM:
    cliente_id: str
    tenant_id: str
    unidade_id: str
    origem: OrigemClienteCRM
    contatos: tuple[ContatoCRM, ...]
    criado_em: datetime
    marketplace_origem: PlataformaMarketplace | None = None
    versao: int = 1

    def __post_init__(self) -> None:
        if any(not valor.strip() for valor in (self.cliente_id, self.tenant_id, self.unidade_id)):
            raise ErroCRM("cliente_invalido")
        if self.versao < 1:
            raise ErroCRM("versao_cliente_invalida")
        if not self.contatos:
            raise ErroCRM("cliente_sem_contato_referenciado")
        canais = [contato.canal for contato in self.contatos]
        if len(set(canais)) != len(canais):
            raise ErroCRM("canal_contato_duplicado")
        object.__setattr__(self, "criado_em", utc(self.criado_em))

    def contato_para(self, canal: CanalMarketing) -> ContatoCRM | None:
        return next((contato for contato in self.contatos if contato.canal is canal), None)


@dataclass(frozen=True)
class ClienteMarketplaceRestrito:
    marketplace_cliente_id: str
    tenant_id: str
    unidade_id: str
    integracao_id: str
    plataforma: PlataformaMarketplace
    id_externo_hash: str
    criado_em: datetime
    expira_em: datetime
    apelido: str | None = None
    convertido_cliente_id: str | None = None
    versao: int = 1

    def __post_init__(self) -> None:
        if any(
            not valor.strip()
            for valor in (
                self.marketplace_cliente_id,
                self.tenant_id,
                self.unidade_id,
                self.integracao_id,
            )
        ):
            raise ErroCRM("cliente_marketplace_invalido")
        if self.versao < 1:
            raise ErroCRM("versao_cliente_marketplace_invalida")
        object.__setattr__(
            self,
            "id_externo_hash",
            _hash_hex(self.id_externo_hash, codigo="hash_identidade_marketplace_invalido"),
        )
        criado_em = utc(self.criado_em)
        expira_em = utc(self.expira_em)
        if expira_em <= criado_em:
            raise ErroCRM("expiracao_marketplace_invalida")
        object.__setattr__(self, "criado_em", criado_em)
        object.__setattr__(self, "expira_em", expira_em)
        if self.apelido is not None:
            apelido = " ".join(self.apelido.split())[:80]
            object.__setattr__(self, "apelido", apelido or None)


@dataclass(frozen=True)
class ConsentimentoMarketing:
    consentimento_id: str
    tenant_id: str
    unidade_id: str
    cliente_id: str
    canal: CanalMarketing
    finalidade: FinalidadeMarketing
    status: StatusConsentimento
    base_legal: BaseLegalMarketing
    texto_versao: str
    origem: str
    prova_hash: str
    ocorrido_em: datetime
    idempotency_key: str
    correlation_id: str
    concedido_em: datetime | None = None
    revogado_em: datetime | None = None

    def __post_init__(self) -> None:
        if any(
            not valor.strip()
            for valor in (
                self.consentimento_id,
                self.tenant_id,
                self.unidade_id,
                self.cliente_id,
                self.texto_versao,
                self.origem,
                self.idempotency_key,
                self.correlation_id,
            )
        ):
            raise ErroCRM("consentimento_invalido")
        if self.base_legal is not BaseLegalMarketing.CONSENTIMENTO:
            raise ErroCRM("base_legal_marketing_nao_suportada")
        object.__setattr__(
            self,
            "prova_hash",
            _hash_hex(self.prova_hash, codigo="prova_consentimento_invalida"),
        )
        ocorrido_em = utc(self.ocorrido_em)
        object.__setattr__(self, "ocorrido_em", ocorrido_em)
        if self.status is StatusConsentimento.CONCEDIDO:
            if self.concedido_em is None or self.revogado_em is not None:
                raise ErroCRM("consentimento_concedido_inconsistente")
            object.__setattr__(self, "concedido_em", utc(self.concedido_em))
        else:
            if self.revogado_em is None:
                raise ErroCRM("revogacao_sem_timestamp")
            object.__setattr__(self, "revogado_em", utc(self.revogado_em))


@dataclass(frozen=True)
class EventoFunilCRM:
    evento_id: str
    tenant_id: str
    unidade_id: str
    sujeito_ref: str
    etapa: EtapaFunilCRM
    ocorrido_em: datetime
    idempotency_key: str
    plataforma: PlataformaMarketplace | None = None
    cliente_id: str | None = None

    def __post_init__(self) -> None:
        if any(
            not valor.strip()
            for valor in (
                self.evento_id,
                self.tenant_id,
                self.unidade_id,
                self.sujeito_ref,
                self.idempotency_key,
            )
        ):
            raise ErroCRM("evento_funil_invalido")
        object.__setattr__(self, "ocorrido_em", utc(self.ocorrido_em))


@dataclass(frozen=True)
class BeneficioCRM:
    beneficio_id: str
    tenant_id: str
    unidade_id: str
    cliente_id: str
    tipo: TipoBeneficioCRM
    valor: Decimal
    referencia: str
    emitido_em: datetime
    idempotency_key: str

    def __post_init__(self) -> None:
        if any(
            not valor.strip()
            for valor in (
                self.beneficio_id,
                self.tenant_id,
                self.unidade_id,
                self.cliente_id,
                self.referencia,
                self.idempotency_key,
            )
        ):
            raise ErroCRM("beneficio_invalido")
        object.__setattr__(self, "valor", moeda(self.valor))
        object.__setattr__(self, "emitido_em", utc(self.emitido_em))


@dataclass(frozen=True)
class ResumoFunilCRM:
    marketplace_restritos: int
    consentimentos_concedidos: int
    convertidos: int
    beneficios_emitidos: int
    opt_outs: int


@dataclass(frozen=True)
class ResultadoConversaoCRM:
    cliente: ClienteCRM
    consentimento: ConsentimentoMarketing
    idempotente: bool = False


@dataclass(frozen=True)
class ResultadoDespachoMarketing:
    enviado: bool
    motivo: str
