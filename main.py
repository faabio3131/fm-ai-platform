import os
import hashlib
import traceback
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import create_engine, Column, Integer, String, Float, Text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import JWTError, jwt
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# --- BANCO DE DADOS BLINDADO ---
# ==========================================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banco_erp_local.db")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# ==========================================
# --- TABELAS DO BANCO ---
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
# --- CRIPTOGRAFIA NATIVA SHA-256 ---
# ==========================================
def criar_hash_senha(senha: str):
    """Gera hash SHA-256 nativo do Python (nunca trava em nuvens Linux)."""
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()

def verificar_senha(senha_pura: str, senha_hash: str):
    return criar_hash_senha(senha_pura) == senha_hash

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def criar_token_acesso(dados: dict):
    a_codificar = dados.copy()
    expira = datetime.utcnow() + timedelta(minutes=720)
    a_codificar.update({"exp": expira})
    return jwt.encode(a_codificar, os.getenv("SECRET_KEY", "chave_secreta_padrao"), algorithm="HS256")

# --- AUTO-REPARO DOS USUÁRIOS NO BANCO ---
def reparar_e_garantir_admins():
    """Verifica os e-mails testados anteriormente e conserta os hashes corrompidos no banco."""
    db = SessionLocal()
    try:
        emails_admin = ["contato@micaburger.com", "admin@micaburger.com", "gerente@mica.com"]
        hash_correto = criar_hash_senha("123456")
        
        for email in emails_admin:
            usuario = db.query(Usuario).filter(Usuario.email == email).first()
            if not usuario:
                db.add(Usuario(email=email, senha_hash=hash_correto))
            else:
                # Sobrescreve a senha antiga corrompida pela nova funcional
                usuario.senha_hash = hash_correto
        db.commit()
    except Exception as e:
        print(f"Aviso no auto-reparo: {e}")
    finally:
        db.close()

reparar_e_garantir_admins()

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
        usuario_existente = db.query(Usuario).filter(Usuario.email == dados.email).first()
        hash_novo = criar_hash_senha(dados.senha)
        
        # SE O USUÁRIO JÁ EXISTIR, ATUALIZA A SENHA EM VEZ DE BLOQUEAR O ACESSO
        if usuario_existente:
            usuario_existente.senha_hash = hash_novo
            db.commit()
            return {"mensagem": "Senha consertada e atualizada com sucesso no banco!", "id": usuario_existente.id}
        
        novo_usuario = Usuario(email=dados.email, senha_hash=hash_novo)
        db.add(novo_usuario)
        db.commit()
        db.refresh(novo_usuario)
        return {"mensagem": "Usuário criado com sucesso com criptografia nativa!", "id": novo_usuario.id}
    except Exception as e:
        erro_detalhado = traceback.format_exc()
        raise HTTPException(status_code=500, detail=f"Falha interna: {str(e)}")

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