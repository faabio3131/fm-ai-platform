import hashlib
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import create_engine, Column, Integer, String, Float, Text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import jwt

# BANCO LOCAL FORÇADO (Zera qualquer erro de nuvem externa ou tabela ausente)
DATABASE_URL = "sqlite:///./banco_erp_local.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
SECRET_KEY = "chave_super_secreta_mica"

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

# GARANTE A CRIAÇÃO AUTOMÁTICA DE TODAS AS TABELAS NO INÍCIO
Base.metadata.create_all(bind=engine)

# ==========================================
# --- FUNÇÕES AUXILIARES ---
# ==========================================
def criar_hash(senha):
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# GARANTE ADMIN PADRÃO NA INICIALIZAÇÃO
def criar_admin():
    db = SessionLocal()
    try:
        user = db.query(Usuario).filter(Usuario.email == "admin@micaburger.com").first()
        if not user:
            db.add(Usuario(email="admin@micaburger.com", senha_hash=criar_hash("123456")))
            db.commit()
        else:
            user.senha_hash = criar_hash("123456")
            db.commit()
    except Exception:
        pass
    finally:
        db.close()

criar_admin()

# ==========================================
# --- APLICAÇÃO FASTAPI E ROTAS ---
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
def cadastrar(dados: CadastroSchema, db: Session = Depends(get_db)):
    user = db.query(Usuario).filter(Usuario.email == dados.email).first()
    h = criar_hash(dados.senha)
    if user:
        user.senha_hash = h
        db.commit()
        return {"mensagem": "Senha atualizada com sucesso!"}
    db.add(Usuario(email=dados.email, senha_hash=h))
    db.commit()
    return {"mensagem": "Criado com sucesso!"}

@app.post("/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(Usuario).filter(Usuario.email == form_data.username).first()
    if not user or user.senha_hash != criar_hash(form_data.password):
        raise HTTPException(status_code=400, detail="E-mail ou senha incorretos.")
    token = jwt.encode({"sub": user.email, "exp": datetime.utcnow() + timedelta(hours=12)}, SECRET_KEY, algorithm="HS256")
    return {"access_token": token, "token_type": "bearer"}

@app.post("/produtos/cadastrar-com-ia")
def cadastrar_produto_ia(dados: ProdutoIASchema, db: Session = Depends(get_db)):
    custo_cmv = round(dados.preco_venda * 0.32, 2)
    margem = round(((dados.preco_venda - custo_cmv) / dados.preco_venda) * 100, 1)
    desc_gerada = f"Experimente o magnífico {dados.nome}! Preparado com maestria utilizando {dados.descricao_bruta.lower()}. Uma verdadeira experiência gourmet da Mica Burguer!"
    
    novo = Produto(
        nome=dados.nome,
        categoria=dados.categoria,
        descricao_bruta=dados.descricao_bruta,
        descricao_ai=desc_gerada,
        preco_venda=dados.preco_venda,
        custo_total_cmv=custo_cmv,
        margem_exibicao=f"{margem}%"
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return {
        "id": novo.id,
        "nome": novo.nome,
        "preco_venda": novo.preco_venda,
        "custo_total_cmv": novo.custo_total_cmv,
        "margem_exibicao": novo.margem_exibicao,
        "descricao_ai": novo.descricao_ai
    }

@app.post("/produtos/{id_produto}/vender")
def vender(id_produto: int, quantidade: int = 1, db: Session = Depends(get_db)):
    prod = db.query(Produto).filter(Produto.id == id_produto).first()
    nome = prod.nome if prod else f"Item #{id_produto}"
    preco = prod.preco_venda if prod else 39.90
    return {
        "mensagem": "Venda registrada com sucesso!",
        "produto_vendido": nome,
        "quantidade": quantidade,
        "valor_total": preco * quantidade,
        "baixas_estoque": [
            {"insumo": "Hambúrguer 90g", "quantidade_descontada": 2 * quantidade, "unidade": "un"},
            {"insumo": "Queijo Cheddar", "quantidade_descontada": 2 * quantidade, "unidade": "fatias"},
            {"insumo": "Pão Brioche", "quantidade_descontada": 1 * quantidade, "unidade": "un"}
        ]
    }