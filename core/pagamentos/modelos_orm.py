"""Persistencia aditiva financeira V1; legado permanece intocado."""

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class PaymentsBase(DeclarativeBase):
    pass


class ObrigacaoPagamentoORM(PaymentsBase):
    __tablename__ = "obrigacoes_pagamento_v1"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pedido_id: Mapped[str] = mapped_column(String(64), nullable=False)
    comanda_id: Mapped[str | None] = mapped_column(String(64))
    valor_previsto: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    moeda: Mapped[str] = mapped_column(String(3), nullable=False)
    criado_em: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    versao: Mapped[int] = mapped_column(Integer, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "idempotency_key",
            name="uq_obrigacao_idempotencia_escopo",
        ),
        CheckConstraint("valor_previsto > 0", name="ck_obrigacao_valor"),
        CheckConstraint("versao >= 1", name="ck_obrigacao_versao"),
        Index("ix_obrigacao_escopo_pedido", "tenant_id", "unidade_id", "pedido_id"),
    )


class PagamentoORM(PaymentsBase):
    __tablename__ = "pagamentos_v1"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pedido_id: Mapped[str] = mapped_column(String(64), nullable=False)
    comanda_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    metodo: Mapped[str] = mapped_column(String(40), nullable=False)
    valor_previsto: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    valor_pago: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    valor_estornado: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    saldo: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    moeda: Mapped[str] = mapped_column(String(3), nullable=False)
    recebimento_posterior: Mapped[bool] = mapped_column(Boolean, nullable=False)
    provedor: Mapped[str | None] = mapped_column(String(80))
    criado_em: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    atualizado_em: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    versao: Mapped[int] = mapped_column(Integer, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "unidade_id", "id"],
            [
                "obrigacoes_pagamento_v1.tenant_id",
                "obrigacoes_pagamento_v1.unidade_id",
                "obrigacoes_pagamento_v1.id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "idempotency_key",
            name="uq_pagamento_idempotencia_escopo",
        ),
        CheckConstraint(
            "valor_previsto > 0 AND valor_pago >= 0 AND valor_estornado >= 0 AND saldo >= 0",
            name="ck_pagamento_valores",
        ),
        CheckConstraint("versao >= 1", name="ck_pagamento_versao"),
        Index("ix_pagamento_escopo_pedido", "tenant_id", "unidade_id", "pedido_id"),
    )


class TransacaoPagamentoORM(PaymentsBase):
    __tablename__ = "transacoes_pagamento_v1"
    transacao_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pagamento_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    valor: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    metodo: Mapped[str] = mapped_column(String(40), nullable=False)
    provedor: Mapped[str | None] = mapped_column(String(80))
    id_externo: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    processada_em: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    causation_id: Mapped[str | None] = mapped_column(String(64))
    payload_resumo: Mapped[dict] = mapped_column(JSON, nullable=False)
    erro_normalizado: Mapped[str | None] = mapped_column(String(120))
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "unidade_id", "pagamento_id"],
            ["pagamentos_v1.tenant_id", "pagamentos_v1.unidade_id", "pagamentos_v1.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "idempotency_key",
            name="uq_transacao_pagamento_idempotencia",
        ),
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "provedor",
            "id_externo",
            "tipo",
            name="uq_transacao_externa_tipo",
        ),
        CheckConstraint("valor >= 0", name="ck_transacao_valor"),
        Index(
            "ix_transacao_escopo_pagamento", "tenant_id", "unidade_id", "pagamento_id"
        ),
    )


class CriterioFinanceiroORM(PaymentsBase):
    __tablename__ = "criterios_financeiros_v1"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pedido_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pagamento_id: Mapped[str | None] = mapped_column(String(64))
    comanda_id: Mapped[str | None] = mapped_column(String(64))
    elegivel: Mapped[bool] = mapped_column(Boolean, nullable=False)
    codigo: Mapped[str] = mapped_column(String(60), nullable=False)
    motivo: Mapped[str] = mapped_column(String(255), nullable=False)
    valor_reconhecivel: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    policy: Mapped[str] = mapped_column(String(80), nullable=False)
    versao: Mapped[int] = mapped_column(Integer, nullable=False)
    ator: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_segura: Mapped[dict] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "idempotency_key",
            name="uq_criterio_idempotencia",
        ),
        Index("ix_criterio_escopo_pedido", "tenant_id", "unidade_id", "pedido_id"),
    )


class VendaFinanceiraORM(PaymentsBase):
    __tablename__ = "vendas_financeiras_v1"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pedido_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pagamento_id: Mapped[str | None] = mapped_column(String(64))
    comanda_id: Mapped[str | None] = mapped_column(String(64))
    criterio_codigo: Mapped[str] = mapped_column(String(60), nullable=False)
    criterio_versao: Mapped[int] = mapped_column(Integer, nullable=False)
    valor: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    moeda: Mapped[str] = mapped_column(String(3), nullable=False)
    metodo: Mapped[str] = mapped_column(String(40), nullable=False)
    reconhecida_em: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "pedido_id",
            "criterio_versao",
            name="uq_venda_financeira_equivalente",
        ),
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "idempotency_key",
            name="uq_venda_financeira_idempotencia",
        ),
        CheckConstraint("valor > 0", name="ck_venda_financeira_valor"),
    )


class ObrigacaoCompraFiscalORM(PaymentsBase):
    __tablename__ = "obrigacoes_compra_fiscal_v1"
    obrigacao_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    environment: Mapped[str] = mapped_column(String(20), primary_key=True)
    fornecedor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pedido_id: Mapped[str] = mapped_column(String(64), nullable=False)
    recebimento_id: Mapped[str] = mapped_column(String(64), nullable=False)
    inbound_id: Mapped[str] = mapped_column(String(64), nullable=False)
    chave_acesso: Mapped[str] = mapped_column(String(64), nullable=False)
    valor_original: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    valor_ajustado: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    saldo: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    moeda: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    reconciliacao: Mapped[str] = mapped_column(String(30), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    criado_por: Mapped[str] = mapped_column(String(128), nullable=False)
    criado_em: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    versao: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "environment",
            "recebimento_id",
            name="uq_obrigacao_compra_recebimento",
        ),
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "environment",
            "idempotency_key",
            name="uq_obrigacao_compra_idempotencia",
        ),
        CheckConstraint(
            "valor_original > 0 AND valor_ajustado >= 0 AND saldo >= 0",
            name="ck_obrigacao_compra_valores",
        ),
        CheckConstraint("versao >= 1", name="ck_obrigacao_compra_versao"),
        Index(
            "ix_obrigacao_compra_escopo_pedido",
            "tenant_id",
            "unidade_id",
            "environment",
            "pedido_id",
        ),
    )


class AjusteObrigacaoCompraORM(PaymentsBase):
    __tablename__ = "ajustes_obrigacao_compra_v1"
    ajuste_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    environment: Mapped[str] = mapped_column(String(20), primary_key=True)
    obrigacao_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    valor: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    motivo: Mapped[str] = mapped_column(String(512), nullable=False)
    origem_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    criado_por: Mapped[str] = mapped_column(String(128), nullable=False)
    criado_em: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "unidade_id", "environment", "obrigacao_id"],
            [
                "obrigacoes_compra_fiscal_v1.tenant_id",
                "obrigacoes_compra_fiscal_v1.unidade_id",
                "obrigacoes_compra_fiscal_v1.environment",
                "obrigacoes_compra_fiscal_v1.obrigacao_id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "environment",
            "idempotency_key",
            name="uq_ajuste_obrigacao_compra_idempotencia",
        ),
        CheckConstraint("valor > 0", name="ck_ajuste_obrigacao_compra_valor"),
    )


class DecisaoCreditoTributarioORM(PaymentsBase):
    __tablename__ = "decisoes_credito_tributario_v1"
    decisao_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    environment: Mapped[str] = mapped_column(String(20), primary_key=True)
    obrigacao_id: Mapped[str] = mapped_column(String(64), nullable=False)
    obrigacao_versao: Mapped[int] = mapped_column(Integer, nullable=False)
    tributo: Mapped[str] = mapped_column(String(30), nullable=False)
    resultado: Mapped[str] = mapped_column(String(30), nullable=False)
    base_calculo: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    valor_destacado: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    valor_credito: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    cfop: Mapped[str] = mapped_column(String(10), nullable=False)
    cst: Mapped[str] = mapped_column(String(10), nullable=False)
    regra_id: Mapped[str | None] = mapped_column(String(128))
    regra_versao: Mapped[int | None] = mapped_column(Integer)
    motivo: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decidido_por: Mapped[str] = mapped_column(String(128), nullable=False)
    decidido_em: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "unidade_id", "environment", "obrigacao_id"],
            [
                "obrigacoes_compra_fiscal_v1.tenant_id",
                "obrigacoes_compra_fiscal_v1.unidade_id",
                "obrigacoes_compra_fiscal_v1.environment",
                "obrigacoes_compra_fiscal_v1.obrigacao_id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "environment",
            "idempotency_key",
            name="uq_decisao_credito_idempotencia",
        ),
        CheckConstraint(
            "base_calculo >= 0 AND valor_destacado >= 0 AND valor_credito >= 0",
            name="ck_decisao_credito_valores",
        ),
        CheckConstraint(
            "obrigacao_versao >= 1", name="ck_decisao_credito_obrigacao_versao"
        ),
        Index(
            "ix_decisao_credito_escopo_obrigacao",
            "tenant_id",
            "unidade_id",
            "environment",
            "obrigacao_id",
        ),
    )
