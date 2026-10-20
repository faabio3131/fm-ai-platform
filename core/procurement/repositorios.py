"""Portas e implementação em memória da autoridade Procurement V1."""

from collections.abc import Callable
from threading import RLock
from typing import Protocol, TypeVar

from kordena_fiscal.domain import ExecutionScope

from .erros import ConflitoProcurement
from .modelos import (
    CustoAquisicao,
    Fornecedor,
    PedidoCompra,
    RecebimentoCompra,
    VinculoProdutoFornecedor,
)

T = TypeVar("T")


class RepositorioProcurement(Protocol):
    def atomicamente(self, operacao: Callable[[], T]) -> T: ...
    def salvar_fornecedor(self, fornecedor: Fornecedor) -> Fornecedor: ...
    def fornecedor_por_documento(
        self, scope: ExecutionScope, documento: str
    ) -> Fornecedor | None: ...
    def salvar_pedido(
        self, pedido: PedidoCompra, *, versao_esperada: int | None = None
    ) -> PedidoCompra: ...
    def obter_pedido(
        self, scope: ExecutionScope, pedido_id: str
    ) -> PedidoCompra | None: ...
    def salvar_recebimento(
        self, recebimento: RecebimentoCompra
    ) -> tuple[RecebimentoCompra, bool]: ...
    def recebimento_por_idempotencia(
        self, scope: ExecutionScope, chave: str
    ) -> RecebimentoCompra | None: ...
    def obter_recebimento(
        self, scope: ExecutionScope, recebimento_id: str
    ) -> RecebimentoCompra | None: ...
    def salvar_vinculo(
        self, vinculo: VinculoProdutoFornecedor
    ) -> VinculoProdutoFornecedor: ...
    def resolver_vinculo(
        self, scope: ExecutionScope, fornecedor_id: str, codigo_fornecedor: str
    ) -> VinculoProdutoFornecedor | None: ...
    def quantidade_recebida(
        self, scope: ExecutionScope, pedido_id: str, linha_pedido: int
    ) -> object: ...
    def registrar_custo(self, custo: CustoAquisicao) -> CustoAquisicao: ...


class RepositorioProcurementEmMemoria:
    def __init__(self) -> None:
        self._fornecedores: dict[tuple[str, str, str, str], Fornecedor] = {}
        self._pedidos: dict[tuple[str, str, str, str], PedidoCompra] = {}
        self._recebimentos: dict[tuple[str, str, str, str], RecebimentoCompra] = {}
        self._vinculos: dict[
            tuple[str, str, str, str, str], VinculoProdutoFornecedor
        ] = {}
        self._custos: dict[tuple[str, str, str, str, str], CustoAquisicao] = {}
        self._lock = RLock()

    @staticmethod
    def _scope(scope: ExecutionScope) -> tuple[str, str, str]:
        return scope.tenant_id, scope.unit_id, scope.environment.value

    def atomicamente(self, operacao: Callable[[], T]) -> T:
        with self._lock:
            snapshot = (
                dict(self._fornecedores),
                dict(self._pedidos),
                dict(self._recebimentos),
                dict(self._vinculos),
                dict(self._custos),
            )
            try:
                return operacao()
            except Exception:
                (
                    self._fornecedores,
                    self._pedidos,
                    self._recebimentos,
                    self._vinculos,
                    self._custos,
                ) = snapshot
                raise

    def salvar_fornecedor(self, fornecedor: Fornecedor) -> Fornecedor:
        chave = (*self._scope(fornecedor.scope), fornecedor.documento)
        atual = self._fornecedores.get(chave)
        if atual and atual.fornecedor_id != fornecedor.fornecedor_id:
            raise ConflitoProcurement("documento_fornecedor_duplicado")
        self._fornecedores[chave] = fornecedor
        return fornecedor

    def fornecedor_por_documento(
        self, scope: ExecutionScope, documento: str
    ) -> Fornecedor | None:
        return self._fornecedores.get((*self._scope(scope), documento))

    def salvar_pedido(
        self, pedido: PedidoCompra, *, versao_esperada: int | None = None
    ) -> PedidoCompra:
        chave = (*self._scope(pedido.scope), pedido.pedido_id)
        atual = self._pedidos.get(chave)
        if atual and versao_esperada is not None and atual.versao != versao_esperada:
            raise ConflitoProcurement("versao_pedido_divergente")
        self._pedidos[chave] = pedido
        return pedido

    def obter_pedido(
        self, scope: ExecutionScope, pedido_id: str
    ) -> PedidoCompra | None:
        return self._pedidos.get((*self._scope(scope), pedido_id))

    def salvar_recebimento(
        self, recebimento: RecebimentoCompra
    ) -> tuple[RecebimentoCompra, bool]:
        chave = (*self._scope(recebimento.scope), recebimento.idempotency_key)
        atual = self._recebimentos.get(chave)
        if atual:
            if atual.fingerprint != recebimento.fingerprint:
                raise ConflitoProcurement("conflito_idempotencia_recebimento")
            return atual, False
        self._recebimentos[chave] = recebimento
        return recebimento, True

    def recebimento_por_idempotencia(
        self, scope: ExecutionScope, chave: str
    ) -> RecebimentoCompra | None:
        return self._recebimentos.get((*self._scope(scope), chave))

    def obter_recebimento(
        self, scope: ExecutionScope, recebimento_id: str
    ) -> RecebimentoCompra | None:
        return next(
            (
                item
                for item in self._recebimentos.values()
                if item.scope.partition_key == scope.partition_key
                and item.recebimento_id == recebimento_id
            ),
            None,
        )

    def salvar_vinculo(
        self, vinculo: VinculoProdutoFornecedor
    ) -> VinculoProdutoFornecedor:
        chave = (
            *self._scope(vinculo.scope),
            vinculo.fornecedor_id,
            vinculo.codigo_fornecedor,
        )
        atual = self._vinculos.get(chave)
        if atual and atual.insumo_id != vinculo.insumo_id:
            raise ConflitoProcurement("vinculo_produto_divergente")
        self._vinculos[chave] = vinculo
        return vinculo

    def resolver_vinculo(
        self, scope: ExecutionScope, fornecedor_id: str, codigo_fornecedor: str
    ) -> VinculoProdutoFornecedor | None:
        return self._vinculos.get(
            (*self._scope(scope), fornecedor_id, codigo_fornecedor)
        )

    def quantidade_recebida(
        self, scope: ExecutionScope, pedido_id: str, linha_pedido: int
    ) -> object:
        from decimal import Decimal

        with self._lock:
            recebimentos = tuple(self._recebimentos.values())
        return sum(
            (
                item.quantidade
                for recebimento in recebimentos
                if recebimento.scope.partition_key == scope.partition_key
                and recebimento.pedido_id == pedido_id
                and recebimento.status
                in {recebimento.status.PARCIAL, recebimento.status.CONCLUIDO}
                for item in recebimento.itens
                if item.linha_pedido == linha_pedido and item.condicao_aceita
            ),
            Decimal(0),
        )

    def registrar_custo(self, custo: CustoAquisicao) -> CustoAquisicao:
        chave = (*self._scope(custo.scope), custo.recebimento_id, custo.insumo_id)
        atual = self._custos.get(chave)
        if atual and atual != custo:
            raise ConflitoProcurement("custo_recebimento_divergente")
        self._custos[chave] = custo
        return custo
