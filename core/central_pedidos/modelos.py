"""Contratos imutaveis da projecao da Central de Pedidos V1."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, kw_only=True)
class FiltroCentralPedidos:
    status: tuple[str, ...] = ()
    canal: tuple[str, ...] = ()
    criado_de: datetime | None = None
    criado_ate: datetime | None = None
    pedido_id: str | None = None
    cliente_id: str | None = None
    busca: str | None = None
    somente_com_alertas: bool = False
    situacao_financeira: str | None = None
    pagina: int = 1
    tamanho_pagina: int = 25

    def __post_init__(self) -> None:
        if self.pagina < 1 or not 1 <= self.tamanho_pagina <= 100:
            raise ValueError("Paginacao invalida")
        for instante in (self.criado_de, self.criado_ate):
            if instante is not None and instante.utcoffset() is None:
                raise ValueError("Intervalos devem ser timezone-aware")
        if self.criado_de and self.criado_ate and self.criado_de > self.criado_ate:
            raise ValueError("Intervalo de criacao invalido")
        if self.busca is not None:
            busca = self.busca.strip()
            if len(busca) > 100:
                raise ValueError("Busca excede 100 caracteres")
            object.__setattr__(self, "busca", busca or None)


@dataclass(frozen=True)
class AlertaPedidoCentral:
    tipo: str
    severidade: str
    mensagem: str


@dataclass(frozen=True)
class ResumoFinanceiroCentral:
    situacao: str
    valor_previsto: Decimal
    valor_pago: Decimal
    pagamento_ids: tuple[str, ...] = ()
    venda_financeira_id: str | None = None
    venda_legada_id: str | None = None
    reconciliacao_id: str | None = None
    reconciliacao_status: str | None = None


@dataclass(frozen=True)
class ResumoPedidoCentral:
    pedido_id: str
    canal: str
    status: str
    criado_em: datetime
    atualizado_em: datetime
    total: Decimal
    quantidade_itens: int
    cliente_id: str | None
    financeiro: ResumoFinanceiroCentral
    possui_alerta: bool
    origem: str
    versao: int


@dataclass(frozen=True)
class ItemDetalheCentral:
    item_id: str
    nome: str
    quantidade: int
    preco_unitario: Decimal
    subtotal: Decimal
    observacao: str | None
    adicionais: tuple[tuple[str, int, Decimal, Decimal], ...] = ()


@dataclass(frozen=True)
class EventoTimelineCentral:
    evento_id: str
    tipo: str
    ocorrido_em: datetime
    versao: int
    correlation_id: str


@dataclass(frozen=True)
class DetalhePedidoCentral:
    resumo: ResumoPedidoCentral
    subtotal: Decimal
    descontos: Decimal
    taxas: Decimal
    itens: tuple[ItemDetalheCentral, ...]
    observacoes: tuple[str, ...]
    timeline: tuple[EventoTimelineCentral, ...]
    financeiro: ResumoFinanceiroCentral
    alertas: tuple[AlertaPedidoCentral, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PaginaPedidosCentral:
    itens: tuple[ResumoPedidoCentral, ...]
    pagina: int
    tamanho_pagina: int
    total: int
