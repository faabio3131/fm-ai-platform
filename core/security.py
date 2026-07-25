import os
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "chave_fallback_secreta")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 720))

# Motor de criptografia de senhas (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def gerar_hash_senha(senha: str) -> str:
    """Transforma 'senha123' em algo como '$2b$12$e9k/1u...'"""
    return pwd_context.hash(senha)

def verificar_senha(senha_pura: str, senha_hash: str) -> bool:
    """Compara a senha digitada no login com o hash do banco"""
    return pwd_context.verify(senha_pura, senha_hash)

def criar_token_jwt(dados: dict) -> str:
    """Gera o Token Bearer que a loja usará nas requisições"""
    a_codificar = dados.copy()
    expiracao = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    a_codificar.update({"exp": expiracao})
    
    token_codificado = jwt.encode(a_codificar, SECRET_KEY, algorithm=ALGORITHM)
    return token_codificado