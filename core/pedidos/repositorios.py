from typing import Protocol

from core.dominio.eventos import EventoDominio
from core.dominio.ids import IdempotencyKey, PedidoId, TenantId, UnidadeId
from core.dominio.pedidos import Pedido


class RepositorioPedidos(Protocol):
    def buscar(
        self, tenant_id: TenantId, unidade_id: UnidadeId, pedido_id: PedidoId
    ) -> Pedido | None: ...

    def listar(self, tenant_id: TenantId, unidade_id: UnidadeId) -> tuple[Pedido, ...]: ...

    def buscar_por_idempotencia(
        self, tenant_id: TenantId, unidade_id: UnidadeId, chave: IdempotencyKey
    ) -> Pedido | None: ...

    def obter_versao(
        self, tenant_id: TenantId, unidade_id: UnidadeId, pedido_id: PedidoId
    ) -> int | None: ...

    def salvar(
        self, pedido: Pedido, *, versao_esperada: int | None = None
    ) -> Pedido: ...

    def salvar_eventos(
        self,
        tenant_id: TenantId,
        unidade_id: UnidadeId,
        pedido_id: PedidoId,
        eventos: tuple[EventoDominio, ...],
    ) -> None: ...
