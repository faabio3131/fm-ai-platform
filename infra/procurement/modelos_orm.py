"""Persistência aditiva da autoridade Procurement V1."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ProcurementBase(DeclarativeBase):
    pass


class FornecedorORM(ProcurementBase):
    __tablename__ = "procurement_suppliers_v1"
    fornecedor_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    unit_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    environment: Mapped[str] = mapped_column(String(32), primary_key=True)
    documento: Mapped[str] = mapped_column(String(32), nullable=False)
    nome: Mapped[str] = mapped_column(String(256), nullable=False)
    ativo: Mapped[bool] = mapped_column(nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    versao: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unit_id",
            "environment",
            "documento",
            name="uq_procurement_supplier_document_v1",
        ),
        Index(
            "ix_procurement_supplier_partition_v1",
            "tenant_id",
            "unit_id",
            "environment",
        ),
    )


class PedidoCompraORM(ProcurementBase):
    __tablename__ = "procurement_purchase_orders_v1"
    pedido_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    unit_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    environment: Mapped[str] = mapped_column(String(32), primary_key=True)
    fornecedor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    criado_por: Mapped[str] = mapped_column(String(128), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    versao: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unit_id",
            "environment",
            "pedido_id",
            name="uq_procurement_order_partition_v1",
        ),
        Index(
            "ix_procurement_order_partition_status_v1",
            "tenant_id",
            "unit_id",
            "environment",
            "status",
        ),
    )


class RecebimentoCompraORM(ProcurementBase):
    __tablename__ = "procurement_receipts_v1"
    recebimento_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    unit_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    environment: Mapped[str] = mapped_column(String(32), primary_key=True)
    pedido_id: Mapped[str] = mapped_column(String(64), nullable=False)
    inbound_id: Mapped[str] = mapped_column(String(64), nullable=False)
    chave_acesso: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    confirmado_por: Mapped[str] = mapped_column(String(128), nullable=False)
    confirmado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    versao: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unit_id",
            "environment",
            "idempotency_key",
            name="uq_procurement_receipt_idempotency_v1",
        ),
        UniqueConstraint(
            "tenant_id",
            "unit_id",
            "environment",
            "inbound_id",
            "recebimento_id",
            name="uq_procurement_receipt_inbound_v1",
        ),
        Index(
            "ix_procurement_receipt_order_v1",
            "tenant_id",
            "unit_id",
            "environment",
            "pedido_id",
            "status",
        ),
    )


class VinculoProdutoFornecedorORM(ProcurementBase):
    __tablename__ = "procurement_product_bindings_v1"
    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    unit_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    environment: Mapped[str] = mapped_column(String(32), primary_key=True)
    fornecedor_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    codigo_fornecedor: Mapped[str] = mapped_column(String(128), primary_key=True)
    insumo_id: Mapped[str] = mapped_column(String(64), nullable=False)
    valido_desde: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    criado_por: Mapped[str] = mapped_column(String(128), nullable=False)


class CustoAquisicaoORM(ProcurementBase):
    __tablename__ = "procurement_acquisition_costs_v1"
    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    unit_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    environment: Mapped[str] = mapped_column(String(32), primary_key=True)
    recebimento_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    insumo_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    valor_unitario: Mapped[object] = mapped_column(Numeric(20, 6), nullable=False)
    unidade_medida: Mapped[str] = mapped_column(String(16), nullable=False)
    politica: Mapped[str] = mapped_column(String(64), nullable=False)
    registrado_por: Mapped[str] = mapped_column(String(128), nullable=False)
    registrado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    __table_args__ = (
        Index(
            "ix_procurement_cost_history_v1",
            "tenant_id",
            "unit_id",
            "environment",
            "insumo_id",
            "registrado_em",
        ),
    )
