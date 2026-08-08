from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from core.dominio.dinheiro import Dinheiro
from core.pagamentos.modelos_orm import PaymentsBase
from core.pdv.modelos import EntradaPDV
from core.pdv.modelos_orm import PDVBase
from core.pedidos.modelos_orm import OrdersBase
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel

LegacyBase = declarative_base()


class ClienteTeste(LegacyBase):  # type: ignore[misc, valid-type]
    __tablename__ = "clientes"
    id = Column(Integer, primary_key=True)
    saldo_cashback = Column(Float, default=0)
    total_gasto = Column(Float, default=0)
    ultima_compra = Column(DateTime)
    status = Column(String)


class ProdutoTeste(LegacyBase):  # type: ignore[misc, valid-type]
    __tablename__ = "produtos"
    id = Column(Integer, primary_key=True)
    nome = Column(String)
    preco_venda = Column(Float)
    custo_total_cmv = Column(Float)


class InsumoTeste(LegacyBase):  # type: ignore[misc, valid-type]
    __tablename__ = "insumos"
    id = Column(Integer, primary_key=True)
    saldo_atual = Column(Float)


class FichaTeste(LegacyBase):  # type: ignore[misc, valid-type]
    __tablename__ = "fichas_tecnicas"
    id = Column(Integer, primary_key=True)
    produto_id = Column(Integer, ForeignKey("produtos.id"))
    insumo_id = Column(Integer, ForeignKey("insumos.id"))
    quantidade_utilizada = Column(Float)


class VendaTeste(LegacyBase):  # type: ignore[misc, valid-type]
    __tablename__ = "vendas"
    id = Column(Integer, primary_key=True)
    produto_id = Column(Integer)
    cliente_id = Column(Integer)
    quantidade = Column(Integer)
    valor_total = Column(Float)
    custo_total = Column(Float)
    forma_pagamento = Column(String)
    status_pagamento = Column(String)
    data_venda = Column(DateTime)


@pytest.fixture
def fabrica(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'pdv_test.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    LegacyBase.metadata.create_all(engine)
    OrdersBase.metadata.create_all(engine)
    PaymentsBase.metadata.create_all(engine)
    PDVBase.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        session.add_all(
            [
                ClienteTeste(
                    id=1, saldo_cashback=Decimal("10"), total_gasto=0, status="Inativo"
                ),
                ProdutoTeste(id=1, nome="Burger", preco_venda=29.9, custo_total_cmv=9),
                InsumoTeste(id=1, saldo_atual=10),
                FichaTeste(id=1, produto_id=1, insumo_id=1, quantidade_utilizada=1),
            ]
        )
        session.commit()
    return factory


@pytest.fixture
def contexto() -> ContextoExecucao:
    return ContextoExecucao(
        "tenant-teste",
        "unidade-teste",
        "caixa",
        frozenset({Papel.CAIXA}),
        MATRIZ_PADRAO[Papel.CAIXA],
        "corr-pdv",
        datetime.now(timezone.utc),
        "test",
        unidades_permitidas=frozenset({"unidade-teste"}),
    )


@pytest.fixture
def entrada() -> EntradaPDV:
    return EntradaPDV(
        produto_id=1,
        produto_nome="Burger",
        quantidade=1,
        preco_unitario=Dinheiro(Decimal("29.90")),
        custo_total=Dinheiro(Decimal("9")),
        forma_pagamento="Dinheiro Em Espécie",
        terminal_id="caixa-1",
        checkout_id="atendimento-1",
        cliente_id=1,
        valor_recebido=Dinheiro(Decimal("50")),
        usar_cashback=True,
        desconto_cashback=Dinheiro(Decimal("5")),
        confirmacao_presencial=True,
    )
