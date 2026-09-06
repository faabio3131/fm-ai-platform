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
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from core.crm.cashback import ServicoCashback
from core.dominio.dinheiro import Dinheiro
from core.estoque.modelos_orm import StockBase
from core.pagamentos.modelos_orm import PaymentsBase
from core.pdv.modelos import EntradaPDV
from core.pdv.modelos_orm import PDVBase
from core.pedidos.modelos_orm import OrdersBase
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel
from infra.crm.cashback_sqlalchemy import RepositorioCashbackSQLAlchemy
from infra.eventos.modelos_orm import EventBusBase
from infra.gerente_ia.modelos_orm import CoreRuntimeBase
from infra.seguranca.modelos_orm import SecurityBase
from migrations.crm_cashback_ledger_v1 import upgrade_crm_cashback_ledger_v1
from migrations.crm_cliente_legado_mapping_v1 import (
    upgrade_crm_cliente_legado_mapping_v1,
)
from migrations.crm_clientes_persistencia_v1 import upgrade_crm_clientes_persistencia_v1
from migrations.legacy_store_baseline_v1 import (
    upgrade_legacy_store_baseline_v1,
)
from migrations.unit_legacy_store_mapping_v1 import (
    upgrade_unit_legacy_store_mapping_v1,
)

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
    loja_id = Column(Integer, nullable=False)


class InsumoTeste(LegacyBase):  # type: ignore[misc, valid-type]
    __tablename__ = "insumos"
    id = Column(Integer, primary_key=True)
    saldo_atual = Column(Float)
    loja_id = Column(Integer, nullable=False)


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
    with engine.begin() as connection:
        upgrade_legacy_store_baseline_v1(connection)
        upgrade_unit_legacy_store_mapping_v1(connection)
        upgrade_crm_clientes_persistencia_v1(connection)
        upgrade_crm_cliente_legado_mapping_v1(connection)
        upgrade_crm_cashback_ledger_v1(connection)
        connection.execute(
            text(
                "INSERT INTO lojas (id, nome_fantasia) "
                "VALUES (7, 'Loja PDV Teste')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO fm_unidade_loja_legacy_v1 "
                "(tenant_id, unidade_id, loja_id, ativo) "
                "VALUES ('tenant-teste', 'unidade-teste', 7, TRUE)"
            )
        )
    OrdersBase.metadata.create_all(engine)
    PaymentsBase.metadata.create_all(engine)
    StockBase.metadata.create_all(engine)
    EventBusBase.metadata.create_all(engine)
    CoreRuntimeBase.metadata.create_all(engine)
    SecurityBase.metadata.create_all(engine)
    PDVBase.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    agora = datetime.now(timezone.utc)
    with factory() as session:
        session.add_all(
            [
                ClienteTeste(
                    id=1, saldo_cashback=Decimal(10), total_gasto=0, status="Inativo"
                ),
                ProdutoTeste(
                    id=1,
                    nome="Burger",
                    preco_venda=29.9,
                    custo_total_cmv=9,
                    loja_id=7,
                ),
                InsumoTeste(id=1, saldo_atual=10, loja_id=7),
                FichaTeste(id=1, produto_id=1, insumo_id=1, quantidade_utilizada=1),
            ]
        )
        session.flush()
        session.execute(
            text(
                """
                INSERT INTO crm_clientes_v1
                    (tenant_id, unidade_id, cliente_id, origem, marketplace_origem,
                     criado_em, versao)
                VALUES
                    ('tenant-teste', 'unidade-teste', 'cliente-crm-pdv-1',
                     'regularizacao_legado', NULL, :criado_em, 1)
                """
            ),
            {"criado_em": agora.replace(tzinfo=None)},
        )
        session.execute(
            text(
                """
                INSERT INTO crm_cliente_legado_v1
                    (tenant_id, unidade_id, legacy_cliente_id, cliente_id,
                     criado_por, correlation_id, criado_em)
                VALUES
                    ('tenant-teste', 'unidade-teste', 1, 'cliente-crm-pdv-1',
                     'fixture-f13b', 'fixture-pdv-f13b', :criado_em)
                """
            ),
            {"criado_em": agora.replace(tzinfo=None)},
        )
        ServicoCashback(RepositorioCashbackSQLAlchemy(session)).creditar(
            tenant_id="tenant-teste",
            unidade_id="unidade-teste",
            cliente_id="cliente-crm-pdv-1",
            valor=Decimal("10.00"),
            origem="regularizacao_governada",
            referencia="fixture://pdv/f13b",
            idempotency_key="fixture-pdv-f13b:regularizacao-cashback",
            ocorrido_em=agora,
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
        custo_total=Dinheiro(Decimal(9)),
        forma_pagamento="Dinheiro Em Espécie",
        terminal_id="caixa-1",
        checkout_id="atendimento-1",
        cliente_id=1,
        valor_recebido=Dinheiro(Decimal(50)),
        usar_cashback=True,
        desconto_cashback=Dinheiro(Decimal(5)),
        confirmacao_presencial=True,
    )
