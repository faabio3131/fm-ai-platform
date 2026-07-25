from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel

# Importações do nosso sistema
from core.database import get_db, init_db, Loja
from core.security import gerar_hash_senha, verificar_senha, criar_token_jwt
from modulos.food.rotas_ai import router as food_router

# Inicializa as tabelas no banco de dados
init_db()

app = FastAPI(
    title="F&M AI FOOD - ERP Gastronômico",
    description="Sistema de Gestão com Inteligência Artificial e Segurança Corporativa",
    version="1.0.0"
)

# ==========================================
# --- SCHEMAS DE DADOS (PYDANTIC) ---
# ==========================================
class LojaCreate(BaseModel):
    nome_fantasia: str
    email: str
    senha: str

# ==========================================
# --- ROTAS DE SEGURANÇA E AUTENTICAÇÃO ---
# ==========================================

@app.post("/auth/cadastrar-loja", tags=["Segurança - Autenticação"], summary="Cadastrar um novo restaurante no ERP")
def cadastrar_loja(dados: LojaCreate, db: Session = Depends(get_db)):
    # 1. Verifica se o e-mail já está cadastrado no banco da nuvem
    loja_existente = db.query(Loja).filter(Loja.email == dados.email).first()
    if loja_existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este e-mail já está cadastrado em nossa plataforma."
        )
    
    # 2. Gera o hash seguro da senha
    senha_criptografada = gerar_hash_senha(dados.senha)
    
    # 3. Cria a nova loja e salva no Neon (AWS)
    nova_loja = Loja(
        nome_fantasia=dados.nome_fantasia,
        email=dados.email,
        senha_hash=senha_criptografada
    )
    db.add(nova_loja)
    db.commit()
    db.refresh(nova_loja)
    
    return {"mensagem": f"Restaurante '{nova_loja.nome_fantasia}' cadastrado com sucesso na nuvem!", "id": nova_loja.id}


@app.post("/auth/login", tags=["Segurança - Autenticação"], summary="Fazer login e gerar Token JWT")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # 1. Busca a loja pelo e-mail (que no Swagger fica no campo 'username')
    loja = db.query(Loja).filter(Loja.email == form_data.username).first()
    
    # 2. Se a loja não existir ou a senha não bater com o hash
    if not loja or not verificar_senha(form_data.password, loja.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 3. Gera o Token JWT blindado para a sessão
    token_acesso = criar_token_jwt({"sub": loja.email, "loja_id": loja.id})
    
    return {"access_token": token_acesso, "token_type": "bearer"}


# ==========================================
# --- INCLUSÃO DAS ROTAS DO ERP & I.A. ---
# ==========================================
app.include_router(food_router)