"""Porta de consulta da Central de Pedidos."""

from typing import Protocol

from core.seguranca.contexto import ContextoExecucao

from .modelos import DetalhePedidoCentral, FiltroCentralPedidos, PaginaPedidosCentral


class ConsultasCentralPedidos(Protocol):
    def listar(
        self, contexto: ContextoExecucao, filtros: FiltroCentralPedidos
    ) -> PaginaPedidosCentral: ...

    def detalhar(
        self, contexto: ContextoExecucao, pedido_id: str
    ) -> DetalhePedidoCentral | None: ...
