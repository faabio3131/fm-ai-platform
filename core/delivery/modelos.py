"""Contratos puros do canal Delivery Próprio V1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from core.dominio.enums import PagamentoStatus, PedidoStatus
from core.entrega.modelos import StatusEntrega
from core.pagamentos.modelos import MetodoPagamento

from .erros import ErroDelivery

CENTAVO = Decimal("0.01")


def moeda(valor: Decimal | str | int) -> Decimal:
    convertido = Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    if convertido < 0:
        raise ErroDelivery("valor_monetario_negativo")
    return convertido


def utc(valor: datetime) -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ErroDelivery("timestamp_sem_timezone")
    return valor.astimezone(timezone.utc)


def cep_normalizado(valor: str) -> str:
    digits = "".join(ch for ch in valor if ch.isdigit())
    if len(digits) != 8:
        raise ErroDelivery("cep_invalido")
    return digits


class StatusCarrinhoDelivery(StrEnum):
    ABERTO = "aberto"
    CONFIRMACAO_EM_ANDAMENTO = "confirmacao_em_andamento"
    CONFIRMADO = "confirmado"
    CANCELADO = "cancelado"


class TipoCupom(StrEnum):
    FIXO = "fixo"
    PERCENTUAL = "percentual"


class EstagioCancelamento(StrEnum):
    ANTES_PRODUCAO = "antes_producao"
    EM_PRODUCAO = "em_producao"
    PRONTO_EXPEDICAO = "pronto_expedicao"
    EM_ROTA = "em_rota"
    ENTREGUE = "entregue"


@dataclass(frozen=True)
class ProdutoDelivery:
    produto_id: str
    tenant_id: str
    unidade_id: str
    nome: str
    preco: Decimal
    estoque_disponivel: Decimal
    custo_estimado: Decimal = Decimal(0)
    ativo: bool = True
    versao: int = 1

    def __post_init__(self) -> None:
        if any(
            not valor.strip()
            for valor in (self.produto_id, self.tenant_id, self.unidade_id, self.nome)
        ):
            raise ErroDelivery("produto_invalido")
        if self.versao < 1:
            raise ErroDelivery("versao_produto_invalida")
        object.__setattr__(self, "preco", moeda(self.preco))
        object.__setattr__(self, "custo_estimado", moeda(self.custo_estimado))
        estoque = Decimal(self.estoque_disponivel)
        if estoque < 0:
            raise ErroDelivery("estoque_invalido")
        object.__setattr__(self, "estoque_disponivel", estoque)


@dataclass(frozen=True)
class ItemCarrinhoDelivery:
    produto_id: str
    nome: str
    quantidade: int
    preco_unitario: Decimal
    custo_estimado_unitario: Decimal
    produto_versao: int

    def __post_init__(self) -> None:
        if not self.produto_id.strip() or not self.nome.strip():
            raise ErroDelivery("item_invalido")
        if self.quantidade < 1 or self.quantidade > 100:
            raise ErroDelivery("quantidade_invalida")
        if self.produto_versao < 1:
            raise ErroDelivery("versao_produto_invalida")
        object.__setattr__(self, "preco_unitario", moeda(self.preco_unitario))
        object.__setattr__(
            self, "custo_estimado_unitario", moeda(self.custo_estimado_unitario)
        )

    @property
    def subtotal(self) -> Decimal:
        return moeda(self.preco_unitario * self.quantidade)

    @property
    def custo_estimado(self) -> Decimal:
        return moeda(self.custo_estimado_unitario * self.quantidade)


@dataclass(frozen=True)
class EnderecoDelivery:
    endereco_id: str
    cliente_ref: str
    cep: str
    logradouro: str
    numero: str
    bairro: str
    cidade: str
    uf: str
    validado: bool = True

    def __post_init__(self) -> None:
        if any(
            not valor.strip()
            for valor in (
                self.endereco_id,
                self.cliente_ref,
                self.logradouro,
                self.numero,
                self.bairro,
                self.cidade,
                self.uf,
            )
        ):
            raise ErroDelivery("endereco_invalido")
        object.__setattr__(self, "cep", cep_normalizado(self.cep))
        uf = self.uf.strip().upper()
        if len(uf) != 2:
            raise ErroDelivery("uf_invalida")
        object.__setattr__(self, "uf", uf)


@dataclass(frozen=True)
class AreaEntrega:
    area_id: str
    tenant_id: str
    unidade_id: str
    nome: str
    prefixos_cep: tuple[str, ...]
    taxa: Decimal
    sla_minutos: int
    sla_maxutos: int
    versao: int
    ativa: bool = True

    def __post_init__(self) -> None:
        if any(
            not valor.strip()
            for valor in (self.area_id, self.tenant_id, self.unidade_id, self.nome)
        ):
            raise ErroDelivery("area_invalida")
        if not self.prefixos_cep:
            raise ErroDelivery("area_sem_cep")
        prefixos = tuple("".join(ch for ch in p if ch.isdigit()) for p in self.prefixos_cep)
        if any(len(p) < 3 or len(p) > 8 for p in prefixos):
            raise ErroDelivery("prefixo_cep_invalido")
        if self.sla_minutos < 1 or self.sla_maxutos < self.sla_minutos:
            raise ErroDelivery("sla_invalido")
        if self.versao < 1:
            raise ErroDelivery("versao_area_invalida")
        object.__setattr__(self, "prefixos_cep", prefixos)
        object.__setattr__(self, "taxa", moeda(self.taxa))


@dataclass(frozen=True)
class CotacaoEntrega:
    area_id: str
    nome_area: str
    taxa: Decimal
    sla_minutos: int
    sla_maxutos: int
    versao_area: int

    def __post_init__(self) -> None:
        if not self.area_id.strip() or not self.nome_area.strip():
            raise ErroDelivery("cotacao_invalida")
        object.__setattr__(self, "taxa", moeda(self.taxa))


@dataclass(frozen=True)
class CupomDelivery:
    codigo: str
    tenant_id: str
    unidade_id: str
    tipo: TipoCupom
    valor: Decimal
    minimo_pedido: Decimal
    inicio: datetime
    fim: datetime
    limite_total: int | None = None
    limite_cliente: int | None = None
    ativo: bool = True

    def __post_init__(self) -> None:
        codigo = self.codigo.strip().upper()
        if not codigo or not self.tenant_id.strip() or not self.unidade_id.strip():
            raise ErroDelivery("cupom_invalido")
        object.__setattr__(self, "codigo", codigo)
        object.__setattr__(self, "valor", moeda(self.valor))
        object.__setattr__(self, "minimo_pedido", moeda(self.minimo_pedido))
        object.__setattr__(self, "inicio", utc(self.inicio))
        object.__setattr__(self, "fim", utc(self.fim))
        if self.fim <= self.inicio:
            raise ErroDelivery("vigencia_cupom_invalida")
        if self.tipo is TipoCupom.PERCENTUAL and self.valor > Decimal(100):
            raise ErroDelivery("percentual_cupom_invalido")
        if self.limite_total is not None and self.limite_total < 1:
            raise ErroDelivery("limite_cupom_invalido")
        if self.limite_cliente is not None and self.limite_cliente < 1:
            raise ErroDelivery("limite_cupom_invalido")

    def calcular_desconto(self, subtotal: Decimal) -> Decimal:
        subtotal = moeda(subtotal)
        if subtotal < self.minimo_pedido:
            raise ErroDelivery("cupom_minimo_nao_atingido")
        if self.tipo is TipoCupom.FIXO:
            return min(self.valor, subtotal)
        return min(moeda(subtotal * self.valor / Decimal(100)), subtotal)


@dataclass(frozen=True)
class CarrinhoDelivery:
    carrinho_id: str
    tenant_id: str
    unidade_id: str
    cliente_ref: str
    versao: int
    status: StatusCarrinhoDelivery
    itens: tuple[ItemCarrinhoDelivery, ...] = ()
    endereco: EnderecoDelivery | None = None
    cotacao: CotacaoEntrega | None = None
    cupom_codigo: str | None = None
    desconto_cupom: Decimal = Decimal(0)
    cashback_reservado: Decimal = Decimal(0)
    pedido_id: str | None = None
    idempotency_confirmacao: str | None = None

    def __post_init__(self) -> None:
        if any(
            not valor.strip()
            for valor in (
                self.carrinho_id,
                self.tenant_id,
                self.unidade_id,
                self.cliente_ref,
            )
        ):
            raise ErroDelivery("carrinho_invalido")
        if self.versao < 1:
            raise ErroDelivery("versao_carrinho_invalida")
        object.__setattr__(self, "desconto_cupom", moeda(self.desconto_cupom))
        object.__setattr__(self, "cashback_reservado", moeda(self.cashback_reservado))
        if self.endereco is not None and self.endereco.cliente_ref != self.cliente_ref:
            raise ErroDelivery("endereco_de_outro_cliente")
        if self.status in {
            StatusCarrinhoDelivery.CONFIRMACAO_EM_ANDAMENTO,
            StatusCarrinhoDelivery.CONFIRMADO,
        } and (not self.pedido_id or not self.idempotency_confirmacao):
            raise ErroDelivery("carrinho_confirmacao_inconsistente")

    @property
    def subtotal(self) -> Decimal:
        return moeda(sum((item.subtotal for item in self.itens), start=Decimal(0)))

    @property
    def taxa_entrega(self) -> Decimal:
        return self.cotacao.taxa if self.cotacao else Decimal("0.00")

    @property
    def total(self) -> Decimal:
        base = self.subtotal + self.taxa_entrega - self.desconto_cupom
        return moeda(max(Decimal(0), base - self.cashback_reservado))

    @property
    def custo_estimado_itens(self) -> Decimal:
        return moeda(
            sum((item.custo_estimado for item in self.itens), start=Decimal(0))
        )


@dataclass(frozen=True)
class PagamentoDeliveryRef:
    pagamento_id: str
    status: PagamentoStatus
    metodo: MetodoPagamento


@dataclass(frozen=True)
class PedidoDelivery:
    pedido_id: str
    tenant_id: str
    unidade_id: str
    cliente_ref: str
    carrinho_id: str
    itens: tuple[ItemCarrinhoDelivery, ...]
    endereco: EnderecoDelivery
    cotacao: CotacaoEntrega
    desconto_cupom: Decimal
    cashback_usado: Decimal
    total: Decimal
    pagamento: PagamentoDeliveryRef
    entrega_id: str
    status: PedidoStatus = PedidoStatus.CONFIRMADO
    versao: int = 1
    cancelado_em: datetime | None = None

    def __post_init__(self) -> None:
        if any(
            not valor.strip()
            for valor in (
                self.pedido_id,
                self.tenant_id,
                self.unidade_id,
                self.cliente_ref,
                self.carrinho_id,
                self.entrega_id,
            )
        ):
            raise ErroDelivery("pedido_delivery_invalido")
        if not self.itens:
            raise ErroDelivery("pedido_sem_itens")
        if self.versao < 1:
            raise ErroDelivery("versao_pedido_invalida")
        object.__setattr__(self, "desconto_cupom", moeda(self.desconto_cupom))
        object.__setattr__(self, "cashback_usado", moeda(self.cashback_usado))
        object.__setattr__(self, "total", moeda(self.total))
        if self.cancelado_em is not None:
            object.__setattr__(self, "cancelado_em", utc(self.cancelado_em))


@dataclass(frozen=True)
class EventoTracking:
    entrega_id: str
    status: StatusEntrega
    mensagem: str
    ocorrido_em: datetime

    def __post_init__(self) -> None:
        if not self.entrega_id.strip() or not self.mensagem.strip():
            raise ErroDelivery("tracking_invalido")
        object.__setattr__(self, "ocorrido_em", utc(self.ocorrido_em))


@dataclass(frozen=True)
class ResultadoConfirmacaoDelivery:
    pedido: PedidoDelivery
    idempotente: bool = False


@dataclass(frozen=True)
class ResultadoCancelamentoDelivery:
    pedido: PedidoDelivery
    estagio: EstagioCancelamento
    estorno_previsto: Decimal
    desperdicio_estimado: Decimal
    cashback_restaurado: Decimal
    cupom_liberado: bool
    idempotente: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "estorno_previsto", moeda(self.estorno_previsto))
        object.__setattr__(
            self, "desperdicio_estimado", moeda(self.desperdicio_estimado)
        )
        object.__setattr__(
            self, "cashback_restaurado", moeda(self.cashback_restaurado)
        )
