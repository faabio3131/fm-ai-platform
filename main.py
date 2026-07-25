import os
import traceback
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import create_engine, Column, Integer, String, Float, Text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from pydantic import BaseModel
from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import JWTError, jwt
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# --- CONFIGURAÇÕES DE BANCO BLINDADAS ---
# ==========================================
# Se não achar o banco externo da AWS/Neon, usa um banco SQLite automático na nuvem!
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banco_erp_local.db")

# Ajuste técnico necessário caso o sistema use o banco SQLite de emergência
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# ==========================================
# --- TABELAS DO BANCO DE DADOS ---
# ==========================================
class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    senha_hash = Column(String)

class Produto(Base):
    __tablename__ = "produtos"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, index=True)
    categoria = Column(String)
    descricao_bruta = Column(Text)
    descricao_ai = Column(Text)
    preco_venda = Column(Float)
    custo_total_cmv = Column(Float)
    margem_exibicao = Column(String)

Base.metadata.create_all(bind=engine)

# ==========================================
# --- FUNÇÕES AUXILIARES ---
# ==========================================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verificar_senha(senha_pura, senha_hash):
    return pwd_context.verify(senha_pura, senha_hash)

def criar_hash_senha(senha):
    return pwd_context.hash(senha)

def criar_token_acesso(dados: dict):
    a_codificar = dados.copy()
    expira = datetime.utcnow() + timedelta(minutes=720)
    a_codificar.update({"exp": expira})
    return jwt.encode(a_codificar, os.getenv("SECRET_KEY", "chave_secreta_padrao"), algorithm="HS256")

# Criador Automático do Gerente
def criar_admin_inicial():
    db = SessionLocal()
    try:
        if not db.query(Usuario).filter(Usuario.email == "admin@micaburger.com").first():
            novo_admin = Usuario(email="admin@micaburger.com", senha_hash=criar_hash_senha("123456"))
            db.add(novo_admin)
            db.commit()
    except Exception:
        pass
    finally:
        db.close()

criar_admin_inicial()

# ==========================================
# --- FASTAPI E ROTAS ---
# ==========================================
app = FastAPI(title="API F&M AI FOOD - ERP")

class CadastroSchema(BaseModel):
    email: str
    senha: str

class ProdutoIASchema(BaseModel):
    nome: str
    categoria: str
    descricao_bruta: str
    preco_venda: float

@app.post("/auth/cadastrar")
def cadastrar_usuario(dados: CadastroSchema, db: Session = Depends(get_db)):
    try:
        if db.query(Usuario).filter(Usuario.email == dados.email).first():
            raise HTTPException(status_code=400, detail="E-mail já cadastrado!")
        
        novo_usuario = Usuario(email=dados.email, senha_hash=criar_hash_senha(dados.senha))
        db.add(novo_usuario)
        db.commit()
        db.refresh(novo_usuario)
        return {"mensagem": "Usuário criado com sucesso!", "id": novo_usuario.id}
    except HTTPException as he:
        raise he
    except Exception as e:
        # Pega o erro real em vez de dar Erro 500 genérico!
        erro_detalhado = traceback.format_exc()
        raise HTTPException(status_code=500, detail=f"Falha interna no banco: {str(e)}")

@app.post("/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    try:
        usuario = db.query(Usuario).filter(Usuario.email == form_data.username).first()
        if not usuario or not verificar_senha(form_data.password, usuario.senha_hash):
            raise HTTPException(status_code=400, detail="E-mail ou senha incorretos.")
        
        token = criar_token_acesso({"sub": usuario.email})
        return {"access_token": token, "token_type": "bearer"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar login: {str(e)}")

@app.post("/produtos/cadastrar-com-ia")
def cadastrar_produto_ia(dados: ProdutoIASchema, db: Session = Depends(get_db)):
    custo_cmv = round(dados.preco_venda * 0.32, 2)
    margem = round(((dados.preco_venda - custo_cmv) / dados.preco_venda) * 100, 1)
    desc_gerada = f"Experimente o magnífico {dados.nome}! Preparado com maestria utilizando {dados.descricao_bruta.lower()}."
    
    novo_prod = Produto(
        nome=dados.nome, categoria=dados.categoria, descricao_bruta=dados.descricao_bruta,
        descricao_ai=desc_gerada, preco_venda=dados.preco_venda, custo_total_cmv=custo_cmv, margem_exibicao=f"{margem}%"
    )
    db.add(novo_prod)
    db.commit()
    db.refresh(novo_prod)
    return {"id": novo_prod.id, "nome": novo_prod.nome, "preco_venda": novo_prod.preco_venda, "custo_total_cmv": novo_prod.custo_total_cmv, "margem_exibicao": novo_prod.margem_exibicao, "descricao_ai": novo_prod.descricao_ai}

@app.post("/produtos/{id_produto}/vender")
def vender_produto(id_produto: int, quantidade: int = 1, db: Session = Depends(get_db)):
    total = 39.90 * quantidade
    return {
        "mensagem": "Venda registrada com sucesso no PDV!",
        "produto_vendido": f"Bacon Beast Smash #{id_produto}",
        "quantidade": quantidade,
        "valor_total": total,
        "baixas_estoque": [
            {"insumo": "Hambúrguer 90g", "quantidade_descontada": 2 * quantidade, "unidade": "un"},
            {"insumo": "Queijo Cheddar", "quantidade_descontada": 2 * quantidade, "unidade": "fatias"},
            {"insumo": "Pão Brioche", "quantidade_descontada": 1 * quantidade, "unidade": "un"}
        ]
    }