from datetime import datetime
import os
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# Configuração do Banco de Dados SQLite Local
DB_PATH = "banco_erp_local.db"
engine = create_engine(
    f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# --- TABELA DE PRODUTOS (CARDÁPIO) ---
class Produto(Base):
    __tablename__ = "produtos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, unique=True, index=True, nullable=False)
    categoria = Column(String, nullable=False)
    preco_venda = Column(Float, nullable=False, default=0.0)
    custo_unitario = Column(Float, default=0.0)
    margem_lucro = Column(Float, default=0.0)
    imagem_path = Column(String, nullable=True)

    # Relacionamento com a Ficha Técnica (Receita do Prato - Fase 2)
    ingredientes = relationship(
        "FichaTecnica", back_populates="produto", cascade="all, delete-orphan"
    )
    vendas = relationship("Venda", back_populates="produto")


# --- TABELA DE INSUMOS (ESTOQUE) ---
class Insumo(Base):
    __tablename__ = "insumos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, unique=True, index=True, nullable=False)
    quantidade_atual = Column(Float, default=0.0)
    unidade_medida = Column(String, default="un")  # un, g, kg, fatias, ml, L
    alerta_minimo = Column(Float, default=10.0)
    custo_unitario = Column(Float, default=0.0)

    # Relacionamento reverso com a Ficha Técnica
    receitas_vinculadas = relationship(
        "FichaTecnica", back_populates="insumo", cascade="all, delete-orphan"
    )


# --- TABELA FICHA TÉCNICA (CAMADA DE INTELIGÊNCIA 2) ---
class FichaTecnica(Base):
    __tablename__ = "ficha_tecnica"

    id = Column(Integer, primary_key=True, index=True)
    produto_id = Column(Integer, ForeignKey("produtos.id"), nullable=False)
    insumo_id = Column(Integer, ForeignKey("insumos.id"), nullable=False)
    quantidade_gasta = Column(
        Float, nullable=False
    )  # Ex: 0.180 (180g de carne por lanche)

    # Conexões relacionais para o ORM navegar rapidamente no PDV
    produto = relationship("Produto", back_populates="ingredientes")
    insumo = relationship("Insumo", back_populates="receitas_vinculadas")


# --- TABELA DE VENDAS (PDV / FINANCEIRO) ---
class Venda(Base):
    __tablename__ = "vendas"

    id = Column(Integer, primary_key=True, index=True)
    produto_id = Column(Integer, ForeignKey("produtos.id"), nullable=False)
    quantidade = Column(Integer, nullable=False, default=1)
    valor_total = Column(Float, nullable=False, default=0.0)
    custo_total = Column(Float, default=0.0)
    data_venda = Column(DateTime, default=datetime.now)

    produto = relationship("Produto", back_populates="vendas")


# Cria automaticamente todas as tabelas no arquivo .db se elas não existirem
Base.metadata.create_all(bind=engine)