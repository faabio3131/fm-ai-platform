"""Adapter SQLAlchemy da autoridade Procurement V1."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol, TypeVar, cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.procurement.erros import ConflitoProcurement
from core.procurement.modelos import (
    CustoAquisicao,
    Divergencia,
    Fornecedor,
    ItemPedidoCompra,
    ItemRecebido,
    PedidoCompra,
    RecebimentoCompra,
    StatusPedidoCompra,
    StatusRecebimento,
    TipoDivergencia,
    VinculoProdutoFornecedor,
)
from kordena_fiscal.domain import ExecutionScope, FiscalEnvironment

from .modelos_orm import (
    CustoAquisicaoORM,
    FornecedorORM,
    PedidoCompraORM,
    RecebimentoCompraORM,
    VinculoProdutoFornecedorORM,
)

T = TypeVar("T")


class _ScopedRow(Protocol):
    tenant_id: str
    unit_id: str
    environment: str


def _aware(valor: datetime) -> datetime:
    return (
        valor.replace(tzinfo=timezone.utc)
        if valor.tzinfo is None
        else valor.astimezone(timezone.utc)
    )


def _scope(
    row: _ScopedRow, correlation_id: str = "procurement-persisted"
) -> ExecutionScope:
    return ExecutionScope(
        tenant_id=str(row.tenant_id),
        unit_id=str(row.unit_id),
        environment=FiscalEnvironment(str(row.environment)),
        correlation_id=correlation_id,
    )


def _partition(scope: ExecutionScope) -> tuple[str, str, str]:
    return scope.tenant_id, scope.unit_id, scope.environment.value


def _pedido_payload(pedido: PedidoCompra) -> str:
    return json.dumps(
        {
            "frete": str(pedido.frete),
            "desconto": str(pedido.desconto),
            "total": str(pedido.total),
            "itens": [
                {
                    "linha": item.linha,
                    "insumo_id": item.insumo_id,
                    "codigo_fornecedor": item.codigo_fornecedor,
                    "descricao": item.descricao,
                    "unidade_medida": item.unidade_medida,
                    "quantidade": str(item.quantidade),
                    "valor_unitario": str(item.valor_unitario),
                }
                for item in pedido.itens
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _pedido(row: PedidoCompraORM) -> PedidoCompra:
    payload = json.loads(row.payload_json)
    return PedidoCompra(
        row.pedido_id,
        _scope(row),
        row.fornecedor_id,
        tuple(
            ItemPedidoCompra(
                int(item["linha"]),
                str(item["insumo_id"]),
                str(item["codigo_fornecedor"]),
                str(item["descricao"]),
                str(item["unidade_medida"]),
                Decimal(str(item["quantidade"])),
                Decimal(str(item["valor_unitario"])),
            )
            for item in payload["itens"]
        ),
        Decimal(str(payload["frete"])),
        Decimal(str(payload["desconto"])),
        Decimal(str(payload["total"])),
        StatusPedidoCompra(row.status),
        row.criado_por,
        _aware(row.criado_em),
        _aware(row.atualizado_em),
        row.versao,
    )


def _recebimento_payload(recebimento: RecebimentoCompra) -> str:
    return json.dumps(
        {
            "itens": [
                {
                    "linha_pedido": item.linha_pedido,
                    "linha_fiscal": item.linha_fiscal,
                    "insumo_id": item.insumo_id,
                    "quantidade": str(item.quantidade),
                    "unidade_medida": item.unidade_medida,
                    "valor_unitario": str(item.valor_unitario),
                    "condicao_aceita": item.condicao_aceita,
                }
                for item in recebimento.itens
            ],
            "divergencias": [
                {
                    "tipo": item.tipo.value,
                    "linha_pedido": item.linha_pedido,
                    "esperado": item.esperado,
                    "encontrado": item.encontrado,
                }
                for item in recebimento.divergencias
            ],
            "metadata": dict(recebimento.metadata),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _recebimento(row: RecebimentoCompraORM) -> RecebimentoCompra:
    payload = json.loads(row.payload_json)
    return RecebimentoCompra(
        row.recebimento_id,
        _scope(row),
        row.pedido_id,
        row.inbound_id,
        row.chave_acesso,
        row.idempotency_key,
        tuple(
            ItemRecebido(
                int(item["linha_pedido"]),
                int(item["linha_fiscal"]),
                str(item["insumo_id"]),
                Decimal(str(item["quantidade"])),
                str(item["unidade_medida"]),
                Decimal(str(item["valor_unitario"])),
                bool(item["condicao_aceita"]),
            )
            for item in payload["itens"]
        ),
        tuple(
            Divergencia(
                TipoDivergencia(item["tipo"]),
                cast(int | None, item["linha_pedido"]),
                str(item["esperado"]),
                str(item["encontrado"]),
            )
            for item in payload["divergencias"]
        ),
        StatusRecebimento(row.status),
        row.confirmado_por,
        _aware(row.confirmado_em),
        row.versao,
        dict(payload.get("metadata", {})),
    )


class RepositorioProcurementSQLAlchemy:
    """Participa da mesma Session/UoW usada pelo ledger de estoque."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def unit_of_work_token(self) -> object:
        return self._session

    def atomicamente(self, operacao: Callable[[], T]) -> T:
        return operacao()

    def salvar_fornecedor(self, fornecedor: Fornecedor) -> Fornecedor:
        existente = self.fornecedor_por_documento(
            fornecedor.scope, fornecedor.documento
        )
        if existente:
            if existente.fornecedor_id != fornecedor.fornecedor_id:
                raise ConflitoProcurement("documento_fornecedor_duplicado")
            return existente
        self._session.add(
            FornecedorORM(
                fornecedor_id=fornecedor.fornecedor_id,
                tenant_id=fornecedor.scope.tenant_id,
                unit_id=fornecedor.scope.unit_id,
                environment=fornecedor.scope.environment.value,
                documento=fornecedor.documento,
                nome=fornecedor.nome,
                ativo=fornecedor.ativo,
                criado_em=fornecedor.criado_em,
                atualizado_em=fornecedor.atualizado_em,
                versao=fornecedor.versao,
            )
        )
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise ConflitoProcurement("fornecedor_duplicado") from exc
        return fornecedor

    def fornecedor_por_documento(
        self, scope: ExecutionScope, documento: str
    ) -> Fornecedor | None:
        row = self._session.scalar(
            select(FornecedorORM).where(
                FornecedorORM.tenant_id == scope.tenant_id,
                FornecedorORM.unit_id == scope.unit_id,
                FornecedorORM.environment == scope.environment.value,
                FornecedorORM.documento == documento,
            )
        )
        return (
            None
            if row is None
            else Fornecedor(
                row.fornecedor_id,
                scope,
                row.documento,
                row.nome,
                row.ativo,
                _aware(row.criado_em),
                _aware(row.atualizado_em),
                row.versao,
            )
        )

    def salvar_pedido(
        self, pedido: PedidoCompra, *, versao_esperada: int | None = None
    ) -> PedidoCompra:
        row = self._session.scalar(
            select(PedidoCompraORM).where(
                PedidoCompraORM.tenant_id == pedido.scope.tenant_id,
                PedidoCompraORM.unit_id == pedido.scope.unit_id,
                PedidoCompraORM.environment == pedido.scope.environment.value,
                PedidoCompraORM.pedido_id == pedido.pedido_id,
            )
        )
        if row is None:
            self._session.add(
                PedidoCompraORM(
                    pedido_id=pedido.pedido_id,
                    tenant_id=pedido.scope.tenant_id,
                    unit_id=pedido.scope.unit_id,
                    environment=pedido.scope.environment.value,
                    fornecedor_id=pedido.fornecedor_id,
                    status=pedido.status.value,
                    payload_json=_pedido_payload(pedido),
                    criado_por=pedido.criado_por,
                    criado_em=pedido.criado_em,
                    atualizado_em=pedido.atualizado_em,
                    versao=pedido.versao,
                )
            )
        else:
            if versao_esperada is not None and row.versao != versao_esperada:
                raise ConflitoProcurement("versao_pedido_divergente")
            row.status = pedido.status.value
            row.payload_json = _pedido_payload(pedido)
            row.atualizado_em = pedido.atualizado_em
            row.versao = pedido.versao
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise ConflitoProcurement("pedido_duplicado") from exc
        return pedido

    def obter_pedido(
        self, scope: ExecutionScope, pedido_id: str
    ) -> PedidoCompra | None:
        row = self._session.scalar(
            select(PedidoCompraORM).where(
                PedidoCompraORM.tenant_id == scope.tenant_id,
                PedidoCompraORM.unit_id == scope.unit_id,
                PedidoCompraORM.environment == scope.environment.value,
                PedidoCompraORM.pedido_id == pedido_id,
            )
        )
        return None if row is None else _pedido(row)

    def salvar_recebimento(
        self, recebimento: RecebimentoCompra
    ) -> tuple[RecebimentoCompra, bool]:
        atual = self.recebimento_por_idempotencia(
            recebimento.scope, recebimento.idempotency_key
        )
        if atual:
            if atual.fingerprint != recebimento.fingerprint:
                raise ConflitoProcurement("conflito_idempotencia_recebimento")
            return atual, False
        self._session.add(
            RecebimentoCompraORM(
                recebimento_id=recebimento.recebimento_id,
                tenant_id=recebimento.scope.tenant_id,
                unit_id=recebimento.scope.unit_id,
                environment=recebimento.scope.environment.value,
                pedido_id=recebimento.pedido_id,
                inbound_id=recebimento.inbound_id,
                chave_acesso=recebimento.chave_acesso,
                idempotency_key=recebimento.idempotency_key,
                fingerprint=recebimento.fingerprint,
                status=recebimento.status.value,
                payload_json=_recebimento_payload(recebimento),
                confirmado_por=recebimento.confirmado_por,
                confirmado_em=recebimento.confirmado_em,
                versao=recebimento.versao,
            )
        )
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise ConflitoProcurement("recebimento_duplicado") from exc
        return recebimento, True

    def recebimento_por_idempotencia(
        self, scope: ExecutionScope, chave: str
    ) -> RecebimentoCompra | None:
        row = self._session.scalar(
            select(RecebimentoCompraORM).where(
                RecebimentoCompraORM.tenant_id == scope.tenant_id,
                RecebimentoCompraORM.unit_id == scope.unit_id,
                RecebimentoCompraORM.environment == scope.environment.value,
                RecebimentoCompraORM.idempotency_key == chave,
            )
        )
        return None if row is None else _recebimento(row)

    def obter_recebimento(
        self, scope: ExecutionScope, recebimento_id: str
    ) -> RecebimentoCompra | None:
        row = self._session.scalar(
            select(RecebimentoCompraORM).where(
                RecebimentoCompraORM.tenant_id == scope.tenant_id,
                RecebimentoCompraORM.unit_id == scope.unit_id,
                RecebimentoCompraORM.environment == scope.environment.value,
                RecebimentoCompraORM.recebimento_id == recebimento_id,
            )
        )
        return None if row is None else _recebimento(row)

    def salvar_vinculo(
        self, vinculo: VinculoProdutoFornecedor
    ) -> VinculoProdutoFornecedor:
        row = self._session.get(
            VinculoProdutoFornecedorORM,
            (
                *_partition(vinculo.scope),
                vinculo.fornecedor_id,
                vinculo.codigo_fornecedor,
            ),
        )
        if row:
            if row.insumo_id != vinculo.insumo_id:
                raise ConflitoProcurement("vinculo_produto_divergente")
            return vinculo
        self._session.add(
            VinculoProdutoFornecedorORM(
                tenant_id=vinculo.scope.tenant_id,
                unit_id=vinculo.scope.unit_id,
                environment=vinculo.scope.environment.value,
                fornecedor_id=vinculo.fornecedor_id,
                codigo_fornecedor=vinculo.codigo_fornecedor,
                insumo_id=vinculo.insumo_id,
                valido_desde=vinculo.valido_desde,
                criado_por=vinculo.criado_por,
            )
        )
        self._session.flush()
        return vinculo

    def resolver_vinculo(
        self, scope: ExecutionScope, fornecedor_id: str, codigo_fornecedor: str
    ) -> VinculoProdutoFornecedor | None:
        row = self._session.get(
            VinculoProdutoFornecedorORM,
            (*_partition(scope), fornecedor_id, codigo_fornecedor),
        )
        return (
            None
            if row is None
            else VinculoProdutoFornecedor(
                scope,
                row.fornecedor_id,
                row.codigo_fornecedor,
                row.insumo_id,
                _aware(row.valido_desde),
                row.criado_por,
            )
        )

    def quantidade_recebida(
        self, scope: ExecutionScope, pedido_id: str, linha_pedido: int
    ) -> object:
        rows = self._session.scalars(
            select(RecebimentoCompraORM).where(
                RecebimentoCompraORM.tenant_id == scope.tenant_id,
                RecebimentoCompraORM.unit_id == scope.unit_id,
                RecebimentoCompraORM.environment == scope.environment.value,
                RecebimentoCompraORM.pedido_id == pedido_id,
                RecebimentoCompraORM.status.in_(
                    (StatusRecebimento.PARCIAL.value, StatusRecebimento.CONCLUIDO.value)
                ),
            )
        ).all()
        return sum(
            (
                item.quantidade
                for row in rows
                for item in _recebimento(row).itens
                if item.linha_pedido == linha_pedido and item.condicao_aceita
            ),
            Decimal(0),
        )

    def registrar_custo(self, custo: CustoAquisicao) -> CustoAquisicao:
        chave = (*_partition(custo.scope), custo.recebimento_id, custo.insumo_id)
        row = self._session.get(CustoAquisicaoORM, chave)
        if row:
            if (
                Decimal(str(row.valor_unitario)) != custo.valor_unitario
                or row.unidade_medida != custo.unidade_medida
            ):
                raise ConflitoProcurement("custo_recebimento_divergente")
            return custo
        self._session.add(
            CustoAquisicaoORM(
                tenant_id=custo.scope.tenant_id,
                unit_id=custo.scope.unit_id,
                environment=custo.scope.environment.value,
                recebimento_id=custo.recebimento_id,
                insumo_id=custo.insumo_id,
                valor_unitario=custo.valor_unitario,
                unidade_medida=custo.unidade_medida,
                politica=custo.politica,
                registrado_por=custo.registrado_por,
                registrado_em=custo.registrado_em,
            )
        )
        self._session.flush()
        return custo
