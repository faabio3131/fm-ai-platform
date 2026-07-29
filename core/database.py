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
    inspect,
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
    unidade_medida = Column(String, default="un")
    alerta_minimo = Column(Float, default=10.0)
    custo_unitario = Column(Float, default=0.0)

    receitas_vinculadas = relationship(
        "FichaTecnica", back_populates="insumo", cascade="all, delete-orphan"
    )


# --- TABELA FICHA TÉCNICA ---
class FichaTecnica(Base):
  __tablename__ = "ficha_tecnica"

  id = Column(Integer, primary_key=True, index=True)
  produto_id = Column(Integer, ForeignKey("produtos.id"), nullable=False)
  insumo_id = Column(Integer, ForeignKey("insumos.id"), nullable=False)
  quantidade_gasta = Column(Float, nullable=False)

  # --- Propriedade de Compatibilidade ---
  @property
  def quantidade_necessaria(self):
    return self.quantidade_gasta

  @quantidade_necessaria.setter
  def quantidade_necessaria(self, valor):
    self.quantidade_gasta = valor

  produto = relationship("Produto", back_populates="ingredientes")
  insumo = relationship("Insumo", back_populates="receitas_vinculadas")
# --- TABELA DE VENDAS ---
class Venda(Base):
    __tablename__ = "vendas"

    id = Column(Integer, primary_key=True, index=True)
    produto_id = Column(Integer, ForeignKey("produtos.id"), nullable=False)
    quantidade = Column(Integer, nullable=False, default=1)
    valor_total = Column(Float, nullable=False, default=0.0)
    custo_total = Column(Float, default=0.0)
    data_venda = Column(DateTime, default=datetime.now)

    produto = relationship("Produto", back_populates="vendas")


# --- AUTO-CURA DE ESQUEMA ---
precisa_recriar = False
if os.path.exists(DB_PATH):
    try:
        inspector = inspect(engine)
        tabelas = inspector.get_table_names()
        required_tables = ["produtos", "insumos", "ficha_tecnica", "vendas"]

        if not all(t in tabelas for t in required_tables):
            precisa_recriar = True
        else:
            colunas_produtos = [
                c["name"] for c in inspector.get_columns("produtos")
            ]
            colunas_obrigatorias = [
                "custo_unitario",
                "margem_lucro",
                "imagem_path",
            ]
            if not all(
                col in colunas_produtos for col in colunas_obrigatorias
            ):
                precisa_recriar = True
    except Exception:
        precisa_recriar = True

    if precisa_recriar:
        engine.dispose()
        try:
            os.remove(DB_PATH)
        except Exception:
            pass

Base.metadata.create_all(bind=engine)