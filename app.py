import os
import hashlib
from datetime import datetime
import streamlit as st
from google import genai
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Float, Text
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# Carrega variáveis do arquivo .env automaticamente
load_dotenv()

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

class Insumo(Base):
    __tablename__ = "insumos"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, unique=True, index=True)
    quantidade_atual = Column(Float, default=100.0)
    unidade = Column(String)
    alerta_minimo = Column(Float, default=10.0)

class Venda(Base):
    __tablename__ = "vendas"
    id = Column(Integer, primary_key=True, index=True)
    produto_nome = Column(String)
    quantidade = Column(Integer)
    valor_total = Column(Float)
    cmv_total = Column(Float)
    data_hora = Column(String)

# Cria as tabelas de forma segura
try:
    Base.metadata.create_all(bind=engine)
except Exception:
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

# Inicialização de dados padrão
db_init = get_db()
try:
    if not db_init.query(Usuario).filter(Usuario.email == "admin@micaburger.com").first():
        db_init.add(Usuario(email="admin@micaburger.com", senha_hash=criar_hash("123456")))
        db_init.commit()
    
    if db_init.query(Insumo).count() == 0:
        insumos_iniciais = [
            Insumo(nome="Hambúrguer 90g", quantidade_atual=200.0, unidade="un", alerta_minimo=20.0),
            Insumo(nome="Queijo Cheddar", quantidade_atual=300.0, unidade="fatias", alerta_minimo=30.0),
            Insumo(nome="Pão Brioche", quantidade_atual=150.0, unidade="un", alerta_minimo=15.0),
            Insumo(nome="Bacon Artesanal", quantidade_atual=5000.0, unidade="g", alerta_minimo=500.0),
            Insumo(nome="Maionese Trufada", quantidade_atual=3000.0, unidade="g", alerta_minimo=300.0)
        ]
        db_init.add_all(insumos_iniciais)
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
    st.sidebar.success("🤖 Google GenAI SDK Conectado (.env)")
    
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
    aba_cardapio, aba_pdv, aba_estoque, aba_dashboard = st.tabs([
        "🤖 Engenharia de Cardápio com I.A.", 
        "🛒 Frente de Caixa (PDV)", 
        "📦 Estoque de Insumos",
        "📊 Dashboard Financeiro"
    ])
    
    # --- ABA 1: CADASTRAR PRODUTO COM I.A. ---
    with aba_cardapio:
        st.subheader("✨ Criador Gourmet Automatizado com Google Gemini")
        st.write("Digite os dados simples e deixe a Inteligência Artificial gerar uma descrição altamente persuasiva para o cardápio e calcular a margem de lucro.")
        
        with st.form("form_novo_produto"):
            col1, col2 = st.columns(2)
            with col1:
                nome_prod = st.text_input("Nome do Prato / Lanche", value="Mica Royal Truffle Bacon")
                categoria_prod = st.selectbox("Categoria", ["Burgers", "Bebidas", "Acompanhamentos", "Sobremesas"])
            with col2:
                preco_prod = st.number_input("Preço de Venda (R$)", value=46.90, step=1.0)
            
            desc_bruta = st.text_area("Descrição Bruta / Lista de Ingredientes", value="Dois hambúrgueres smash de 100g de costela angus, duplo queijo provolone derretido, farofa crocante de bacon artesanal, maionese trufada e rúcula fresca no pão brioche amanteigado selado na chapa.")
            
            btn_gerar_ia = st.form_submit_button("🚀 Processar com Google I.A. e Cadastrar", type="primary")
            
            if btn_gerar_ia:
                try:
                    custo_cmv = round(preco_prod * 0.32, 2)
                    margem = round(((preco_prod - custo_cmv) / preco_prod) * 100, 1)
                    
                    desc_gerada = ""
                    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
                    
                    if api_key:
                        try:
                            client = genai.Client(api_key=api_key)
                            prompt = f"Escreva uma descrição gourmet irresistível e comercial para um menu de restaurante para o seguinte item:\nNome: {nome_prod}\nCategoria: {categoria_prod}\nIngredientes: {desc_bruta}\nA descrição deve ser sofisticada, dar água na boca e ter no máximo 3 parágrafos."
                            response = client.models.generate_content(
                                model='gemini-2.5-flash',
                                contents=prompt
                            )
                            desc_gerada = response.text
                        except Exception as e:
                            desc_gerada = f"Experimente o magnífico {nome_prod}! Preparado com maestria utilizando {desc_bruta.lower()} Uma verdadeira experiência gourmet de {categoria_prod} da Mica Burguer!"
                    else:
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
                    
                    st.info(f"**Descrição Gourmet Otimizada:**\n\n{desc_gerada}")
                except Exception as e:
                    st.error(f"Erro ao salvar no banco SQLite: {e}")

    # --- ABA 2: FRENTE DE CAIXA (PDV & BAIXA REAL) ---
    with aba_pdv:
        st.subheader("🛒 Frente de Caixa & Baixa Dinâmica de Estoque")
        
        db = get_db()
        produtos_cadastrados = db.query(Produto).all()
        db.close()
        
        if not produtos_cadastrados:
            st.warning("⚠️ Nenhum produto cadastrado no banco. Vá na aba de I.A. e cadastre um lanche primeiro!")
        else:
            with st.form("form_venda"):
                produto_escolhido = st.selectbox(
                    "Selecione o Produto para Venda", 
                    options=produtos_cadastrados, 
                    format_func=lambda p: f"#{p.id} - {p.nome} (R$ {p.preco_venda:.2f})"
                )
                qtd_venda = st.number_input("Quantidade", min_value=1, value=1, step=1)
                btn_vender = st.form_submit_button("💳 Registrar Venda e Dar Baixa no Estoque Real", type="primary")
                
                if btn_vender:
                    db = get_db()
                    total_v = produto_escolhido.preco_venda * qtd_venda
                    cmv_v = produto_escolhido.custo_total_cmv * qtd_venda
                    
                    # Salva a venda na tabela de Vendas para o Dashboard
                    nova_venda = Venda(
                        produto_nome=produto_escolhido.nome,
                        quantidade=qtd_venda,
                        valor_total=total_v,
                        cmv_total=cmv_v,
                        data_hora=datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    )
                    db.add(nova_venda)
                    
                    # Regra de baixa dinâmica de insumos no estoque real
                    consumo_map = {
                        "Hambúrguer 90g": 2.0 * qtd_venda,
                        "Queijo Cheddar": 2.0 * qtd_venda,
                        "Pão Brioche": 1.0 * qtd_venda,
                        "Bacon Artesanal": 50.0 * qtd_venda,
                        "Maionese Trufada": 30.0 * qtd_venda
                    }
                    
                    baixas_realizadas = []
                    for nome_insumo, qtd_gasta in consumo_map.items():
                        ins = db.query(Insumo).filter(Insumo.nome == nome_insumo).first()
                        if ins:
                            ins.quantidade_atual = max(0.0, ins.quantidade_atual - qtd_gasta)
                            baixas_realizadas.append(f"- {qtd_gasta} {ins.unidade} de {ins.nome} (Novo saldo: {ins.quantidade_atual:.1f} {ins.unidade})")
                    
                    db.commit()
                    db.close()
                    
                    st.success(f"✅ Venda registrada com sucesso!")
                    st.write(f"**Item:** {produto_escolhido.nome} | **Qtd:** {qtd_venda}")
                    st.write(f"### 💰 Total a Pagar: R$ {total_v:.2f}")
                    
                    st.markdown("#### 📦 Relatório de Baixa Real no Banco de Dados:")
                    for baixa in baixas_realizadas:
                        st.warning(baixa)

    # --- ABA 3: GESTÃO DE ESTOQUE ---
    with aba_estoque:
        st.subheader("📦 Monitoramento de Insumos em Tempo Real")
        st.write("Acompanhe o saldo atual de cada ingrediente cadastrado no banco de dados do seu restaurante.")
        
        db = get_db()
        lista_insumos = db.query(Insumo).all()
        db.close()
        
        if lista_insumos:
            for ins in lista_insumos:
                col_i1, col_i2, col_i3 = st.columns([3, 2, 2])
                col_i1.markdown(f"**{ins.nome}**")
                col_i2.metric("Saldo em Estoque", f"{ins.quantidade_atual:.1f} {ins.unidade}")
                
                if ins.quantidade_atual <= ins.alerta_minimo:
                    col_i3.error("⚠️ Estoque Crítico!")
                else:
                    col_i3.success("✅ Estoque Saudável")
                st.divider()
        else:
            st.info("Nenhum insumo cadastrado no momento.")

    # --- ABA 4: DASHBOARD FINANCEIRO ---
    with aba_dashboard:
        st.subheader("📊 Indicadores de Desempenho & Relatório Financeiro")
        st.write("Acompanhe o faturamento total, CMV consolidado e as vendas realizadas em tempo real.")
        
        db = get_db()
        vendas_realizadas = db.query(Venda).all()
        db.close()
        
        if vendas_realizadas:
            faturamento_total = sum(v.valor_total for v in vendas_realizadas)
            cmv_total_gasto = sum(v.cmv_total for v in vendas_realizadas)
            lucro_bruto = faturamento_total - cmv_total_gasto
            total_itens = sum(v.quantidade for v in vendas_realizadas)
            
            c_d1, c_d2, c_d3, c_d4 = st.columns(4)
            c_d1.metric("Faturamento Total", f"R$ {faturamento_total:.2f}")
            c_d2.metric("Custo Total (CMV)", f"R$ {cmv_total_gasto:.2f}")
            c_d3.metric("Lucro Bruto", f"R$ {lucro_bruto:.2f}")
            c_d4.metric("Itens Vendidos", f"{total_itens} un")
            
            st.divider()
            st.markdown("### 📋 Histórico de Transações do PDV")
            
            dados_tabela = [
                {
                    "ID": v.id,
                    "Data/Hora": v.data_hora,
                    "Produto": v.produto_nome,
                    "Qtd": v.quantidade,
                    "Total (R$)": f"R$ {v.valor_total:.2f}",
                    "CMV (R$)": f"R$ {v.cmv_total:.2f}"
                }
                for v in vendas_realizadas
            ]
            st.dataframe(dados_tabela, use_container_width=True)
        else:
            st.info("Nenhuma venda registrada até o momento. Realize vendas na aba de Frente de Caixa para visualizar os indicadores.")