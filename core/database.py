import os
from sqlalchemy import Column, Integer, String, Float, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from dotenv import load_dotenv

# 1. Carrega as variáveis do seu arquivo .env
load_dotenv()

# 2. Busca a URL do banco (com fallback para SQLite local se necessário)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fm_food.db")

# 3. Configuração inteligente do engine (PostgreSQL com Pool ou SQLite)
if DATABASE_URL.startswith("postgresql"):
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True
    )
else:
    engine = create_engine(
        DATABASE_URL, 
        connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==========================================
# --- MODELOS / TABELAS DO BANCO DE DADOS ---
# ==========================================

class Loja(Base):
    __tablename__ = "lojas"

    id = Column(Integer, primary_key=True, index=True)
    nome_fantasia = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    senha_hash = Column(String, nullable=False)

    produtos = relationship("Produto", back_populates="loja")
    insumos = relationship("Insumo", back_populates="loja")


class Produto(Base):
    __tablename__ = "produtos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    preco_venda = Column(Float, nullable=False)
    loja_id = Column(Integer, ForeignKey("lojas.id"), nullable=False)

    loja = relationship("Loja", back_populates="produtos")


class Insumo(Base):
    __tablename__ = "insumos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    unidade_medida = Column(String, nullable=False) # ex: kg, un, litros
    custo_unitario = Column(Float, nullable=False)
    loja_id = Column(Integer, ForeignKey("lojas.id"), nullable=False)

    loja = relationship("Loja", back_populates="insumos")


class FichaTecnica(Base):
    __tablename__ = "fichas_tecnicas"

    id = Column(Integer, primary_key=True, index=True)
    produto_id = Column(Integer, ForeignKey("produtos.id"), nullable=False)
    insumo_id = Column(Integer, ForeignKey("insumos.id"), nullable=False)
    quantidade_usada = Column(Float, nullable=False)
    loja_id = Column(Integer, ForeignKey("lojas.id"), nullable=False)


# Função auxiliar de inicialização
def init_db():
    Base.metadata.create_all(bind=engine)


# 4. Gerador de sessões (Injeção de Dependência)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()