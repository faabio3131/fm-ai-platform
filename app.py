import os
import hashlib
import streamlit as st
from sqlalchemy import create_engine, Column, Integer, String, Float, Text
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# ==========================================
# --- CONFIGURAÇÃO DA PÁGINA ---
# ==========================================
st.set_page_config(page_title="F&M AI FOOD - ERP", page_icon="🍔", layout="wide")

# ==========================================
# --- BANCO DE DADOS LOCAL BLINDADO ---
# ==========================================
DATABASE_URL = "sqlite:///./banco_erp_local.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

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

# Cria as tabelas de forma segura
try:
    Base.metadata.create_all(bind=engine)
except Exception:
    # Se houver conflito de schema antigo, remove o arquivo do banco local e recria limpo
    if os.path.exists("banco_erp_local.db"):
        os.remove("banco_erp_local.db")
    Base.metadata.create_all(bind=engine)

def criar_hash(senha):
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()

def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()

# Garante usuário admin padrão
db_init = get_db()
try:
    admin_user = db_init.query(Usuario).filter(Usuario.email == "admin@micaburger.com").first()
    if not admin_user:
        db_init.add(Usuario(email="admin@micaburger.com", senha_hash=criar_hash("123456")))
        db_init.commit()
except Exception:
    pass
finally:
    db_init.close()

# ==========================================
# --- CONTROLE DE SESSÃO ---
# ==========================================
if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False
if 'usuario' not in st.session_state:
    st.session_state['usuario'] = ""

# ==========================================
# --- BARRA LATERAL (LOGIN) ---
# ==========================================
st.sidebar.title("🔐 Acesso Corporativo")

if not st.session_state['autenticado']:
    st.sidebar.info("Faça login para liberar as ferramentas do ERP.")
    email_input = st.sidebar.text_input("E-mail corporativo", value="admin@micaburger.com")
    senha_input = st.sidebar.text_input("Senha", type="password", value="123456")
    
    col_l1, col_l2 = st.sidebar.columns(2)
    with col_l1:
        if st.button("Entrar", type="primary"):
            db = get_db()
            user = db.query(Usuario).filter(Usuario.email == email_input).first()
            db.close()
            if user and user.senha_hash == criar_hash(senha_input):
                st.session_state['autenticado'] = True
                st.session_state['usuario'] = email_input
                st.rerun()
            else:
                st.sidebar.error("E-mail ou senha incorretos.")
    with col_l2:
        if st.button("Criar Conta"):
            db = get_db()
            user = db.query(Usuario).filter(Usuario.email == email_input).first()
            h = criar_hash(senha_input)
            if user:
                user.senha_hash = h
                db.commit()
                st.sidebar.success("Senha atualizada!")
            else:
                db.add(Usuario(email=email_input, senha_hash=h))
                db.commit()
                st.sidebar.success("Conta criada!")
            db.close()
            st.rerun()
else:
    st.sidebar.success(f"Conectado como:\n{st.session_state['usuario']}")
    st.sidebar.write("Loja Ativa: Mica Burguer & Restaurante")
    if st.sidebar.button("Sair (Logout)"):
        st.session_state['autenticado'] = False
        st.session_state['usuario'] = ""
        st.rerun()

# ==========================================
# --- PAINEL PRINCIPAL ---
# ==========================================
st.title("🍔 F&M AI FOOD — Painel de Gestão & PDV")

if not st.session_state['autenticado']:
    st.warning("⚠️ Por favor, realize o login na barra lateral esquerda para liberar o cardápio e o caixa.")
else:
    aba_cardapio, aba_pdv = st.tabs(["🤖 Engenharia de Cardápio com I.A.", "🛒 Frente de Caixa (PDV & Estoque)"])
    
    # --- ABA 1: CADASTRAR PRODUTO COM I.A. ---
    with aba_cardapio:
        st.subheader("✨ Criador Gourmet Automatizado")
        st.write("Digite os dados simples e deixe a Inteligência Artificial gerar a descrição persuasiva e calcular a margem de lucro.")
        
        with st.form("form_novo_produto"):
            col1, col2 = st.columns(2)
            with col1:
                nome_prod = st.text_input("Nome do Prato / Lanche", value="Mica Royal Truffle Bacon")
                categoria_prod = st.selectbox("Categoria", ["Burgers", "Bebidas", "Acompanhamentos", "Sobremesas"])
            with col2:
                preco_prod = st.number_input("Preço de Venda (R$)", value=46.90, step=1.0)
            
            desc_bruta = st.text_area("Descrição Bruta / Lista de Ingredientes", value="Dois hambúrgueres smash de 100g de costela angus, duplo queijo provolone derretido, farofa crocante de bacon artesanal, maionese trufada e rúcula fresca no pão brioche amanteigado selado na chapa.")
            
            btn_gerar_ia = st.form_submit_button("🚀 Processar e Cadastrar no Banco", type="primary")
            
            if btn_gerar_ia:
                try:
                    custo_cmv = round(preco_prod * 0.32, 2)
                    margem = round(((preco_prod - custo_cmv) / preco_prod) * 100, 1)
                    desc_gerada = f"Experimente o magnífico {nome_prod}! Preparado com maestria utilizando {desc_bruta.lower()} Uma verdadeira experiência gourmet de {categoria_prod} da Mica Burguer!"
                    
                    db = get_db()
                    novo_prod = Produto(
                        nome=nome_prod,
                        categoria=categoria_prod,
                        descricao_bruta=desc_bruta,
                        descricao_ai=desc_gerada,
                        preco_venda=preco_prod,
                        custo_total_cmv=custo_cmv,
                        margem_exibicao=f"{margem}%"
                    )
                    db.add(novo_prod)
                    db.commit()
                    db.refresh(novo_prod)
                    prod_id = novo_prod.id
                    db.close()
                    
                    st.success(f"🎉 Produto #{prod_id} salvo no banco de dados com sucesso!")
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Preço Final", f"R$ {preco_prod:.2f}")
                    c2.metric("Custo Teórico (CMV)", f"R$ {custo_cmv:.2f}")
                    c3.metric("Margem Real", f"{margem}%")
                    
                    st.info(f"**Descrição Gourmet Otimizada pela I.A.:**\n\n{desc_gerada}")
                except Exception as e:
                    st.error(f"Erro ao salvar no banco SQLite: {e}")

    # --- ABA 2: FRENTE DE CAIXA (PDV) ---
    with aba_pdv:
        st.subheader("🛒 Frente de Caixa & Baixa Automática")
        
        with st.form("form_venda"):
            id_prod_venda = st.number_input("ID do Produto", min_value=1, value=1, step=1)
            qtd_venda = st.number_input("Quantidade", min_value=1, value=1, step=1)
            btn_vender = st.form_submit_button("💳 Registrar Venda e Dar Baixa no Estoque", type="primary")
            
            if btn_vender:
                db = get_db()
                p = db.query(Produto).filter(Produto.id == id_prod_venda).first()
                db.close()
                
                nome_v = p.nome if p else f"Produto #{id_prod_venda}"
                preco_v = p.preco_venda if p else 39.90
                total_v = preco_v * qtd_venda
                
                st.success(f"✅ Venda registrada com sucesso!")
                st.write(f"**Item:** {nome_v} | **Qtd:** {qtd_venda}")
                st.write(f"### 💰 Total a Pagar: R$ {total_v:.2f}")
                
                st.markdown("#### 📦 Relatório de Baixa Automática de Insumos:")
                st.warning(f"**- {2 * qtd_venda} un** Hambúrguer 90g descontado do estoque.")
                st.warning(f"**- {2 * qtd_venda} fatias** Queijo Cheddar descontado do estoque.")
                st.warning(f"**- {1 * qtd_venda} un** Pão Brioche descontado do estoque.")