"""Contratos imutaveis do nucleo financeiro V1."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import PagamentoStatus
from core.eventos.modelos import EnvelopeMensagem
from core.seguranca.auditoria import EventoAuditoria

from .erros import ValorPagamentoInvalido


class MetodoPagamento(StrEnum):
    DINHEIRO = "dinheiro"
    PIX = "pix"
    CARTAO_CREDITO = "cartao_credito"
    CARTAO_DEBITO = "cartao_debito"
    VOUCHER = "voucher"
    OUTRO = "outro"
    PAGAMENTO_NA_ENTREGA = "pagamento_na_entrega"
    RECEBIMENTO_POSTERIOR = "recebimento_posterior"


class TipoTransacao(StrEnum):
    INICIACAO = "iniciacao"
    CONFIRMACAO = "confirmacao"
    FALHA = "falha"
    CANCELAMENTO = "cancelamento"
    ESTORNO = "estorno"
    REVERSAO_ESTORNO = "reversao_estorno"


class StatusTransacao(StrEnum):
    PENDENTE = "pendente"
    CONFIRMADA = "confirmada"
    FALHOU = "falhou"
    CANCELADA = "cancelada"


class CodigoCriterioFinanceiro(StrEnum):
    PAGAMENTO_CONFIRMADO = "PAGAMENTO_CONFIRMADO"
    COMANDA_FECHADA = "COMANDA_FECHADA"
    RECEBIMENTO_POSTERIOR_AUTORIZADO = "RECEBIMENTO_POSTERIOR_AUTORIZADO"
    NAO_ELEGIVEL = "NAO_ELEGIVEL"


def _utc(valor: datetime) -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ValorPagamentoInvalido("timestamp deve conter timezone")
    return valor.astimezone(timezone.utc)


@dataclass(frozen=True)
class ObrigacaoPagamento:
    id: str
    tenant_id: str
    unidade_id: str
    pedido_id: str
    valor_previsto: Dinheiro
    criado_em: datetime
    versao: int
    correlation_id: str
    comanda_id: str | None = None

    def __post_init__(self) -> None:
        if self.valor_previsto.valor <= 0 or self.versao < 1:
            raise ValorPagamentoInvalido("obrigacao deve ter valor e versao positivos")
        object.__setattr__(self, "criado_em", _utc(self.criado_em))


@dataclass(frozen=True)
class Pagamento:
    id: str
    tenant_id: str
    unidade_id: str
    pedido_id: str
    status: PagamentoStatus
    metodo: MetodoPagamento
    valor_previsto: Dinheiro
    valor_pago: Dinheiro
    valor_estornado: Dinheiro
    saldo: Dinheiro
    moeda: str
    recebimento_posterior: bool
    criado_em: datetime
    atualizado_em: datetime
    versao: int
    correlation_id: str
    comanda_id: str | None = None
    provedor: str | None = None

    def __post_init__(self) -> None:
        moedas = {
            v.moeda
            for v in (
                self.valor_previsto,
                self.valor_pago,
                self.valor_estornado,
                self.saldo,
            )
        }
        if (
            moedas != {self.moeda.upper()}
            or min(self.valor_pago.valor, self.valor_estornado.valor, self.saldo.valor)
            < 0
        ):
            raise ValorPagamentoInvalido("valores/moeda inconsistentes")
        if (
            self.valor_pago.valor - self.valor_estornado.valor + self.saldo.valor
            != self.valor_previsto.valor
        ):
            raise ValorPagamentoInvalido("saldo financeiro inconsistente")
        object.__setattr__(self, "criado_em", _utc(self.criado_em))
        object.__setattr__(self, "atualizado_em", _utc(self.atualizado_em))


@dataclass(frozen=True)
class TransacaoPagamento:
    transacao_id: str
    pagamento_id: str
    tenant_id: str
    unidade_id: str
    tipo: TipoTransacao
    status: StatusTransacao
    valor: Dinheiro
    metodo: MetodoPagamento
    provedor: str | None
    id_externo: str | None
    idempotency_key: str
    occurred_at: datetime
    processada_em: datetime | None
    correlation_id: str
    causation_id: str | None
    payload_resumo: tuple[tuple[str, Any], ...] = ()
    erro_normalizado: str | None = None

    def __post_init__(self) -> None:
        if self.valor.valor < 0:
            raise ValorPagamentoInvalido("transacao nao aceita valor negativo")
        object.__setattr__(self, "occurred_at", _utc(self.occurred_at))
        if self.processada_em:
            object.__setattr__(self, "processada_em", _utc(self.processada_em))


@dataclass(frozen=True)
class ConfirmacaoPagamento:
    pagamento_id: str
    valor_financeiro: Dinheiro
    valor_recebido: Dinheiro
    troco: Dinheiro
    metodo: MetodoPagamento
    referencia_externa: str | None
    timestamp: datetime


@dataclass(frozen=True)
class EstornoPagamento:
    pagamento_id: str
    valor: Dinheiro
    motivo: str
    solicitado_por: str
    timestamp: datetime
    integral: bool


@dataclass(frozen=True)
class CriterioFinanceiro:
    elegivel: bool
    codigo: CodigoCriterioFinanceiro
    motivo: str
    pedido_id: str
    valor_reconhecivel: Dinheiro
    policy: str
    versao: int
    ator: str
    timestamp: datetime
    correlation_id: str
    pagamento_id: str | None = None
    comanda_id: str | None = None
    metadata: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class VendaFinanceira:
    id: str
    tenant_id: str
    unidade_id: str
    pedido_id: str
    pagamento_id: str | None
    comanda_id: str | None
    criterio_codigo: CodigoCriterioFinanceiro
    criterio_versao: int
    valor: Dinheiro
    metodo: MetodoPagamento
    reconhecida_em: datetime
    correlation_id: str
    idempotency_key: str


@dataclass(frozen=True)
class ResultadoPagamento:
    pagamento: Pagamento
    transacao: TransacaoPagamento
    confirmacao: ConfirmacaoPagamento | None
    eventos: tuple[EnvelopeMensagem, ...]
    auditorias: tuple[EventoAuditoria, ...]
    idempotente: bool = False


@dataclass(frozen=True)
class ResultadoReconhecimentoVenda:
    venda: VendaFinanceira
    representacao_legada: dict[str, Any]
    evento: EnvelopeMensagem
    auditoria: EventoAuditoria
    idempotente: bool = False


@dataclass(frozen=True)
class DivergenciaReconciliacao:
    codigo: str
    severidade: str
    mensagem: str
    pagamento_id: str | None = None


@dataclass(frozen=True)
class ResultadoReconciliacao:
    tenant_id: str
    unidade_id: str
    executada_em: datetime
    divergencias: tuple[DivergenciaReconciliacao, ...]
    correlation_id: str
    auditorias: tuple[EventoAuditoria, ...] = field(default_factory=tuple)
