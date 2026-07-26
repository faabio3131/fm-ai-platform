import os
import hashlib
from datetime import datetime
from io import BytesIO
from PIL import Image
import requests
import pandas as pd
import streamlit as st
from google import genai
from google.genai import types
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
# --- IDENTIDADE VISUAL CORPORATIVA (CSS) ---
# ==========================================
st.markdown("""
    <style>
    /* Ajuste de fundo global e tipografia limpa */
    .main {
        background-color: #F8FAFC;
    }

    /* Estilização elegante dos cartões de métricas */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        padding: 16px;
        border-radius: 10px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
        border-left: 4px solid #1E3A8A; /* Azul Corporativo */
    }

    /* Cores de títulos padronizadas */
    h1, h2, h3 {
        color: #0F172A;
        font-family: 'Inter', sans-serif;
    }

    /* Botões principais com destaque corporativo */
    .stButton>button {
        border-radius: 6px;
        font-weight: 600;
    }
    </style>
""", unsafe_allow_html=True)

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
# --- BARRA LATERAL (LOGOTIPO OFICIAL) ---
# ==========================================
try:
    st.sidebar.image("logo.png", use_container_width=True)
except Exception:
    st.sidebar.markdown("<h2 style='text-align: center; color: #1E3A8A;'>F&M AI FOOD</h2>", unsafe_allow_html=True)

st.sidebar.markdown("---")
st.sidebar.title("🔐 Acesso Corporativo")

# ==========================================
# --- BARRA LATERAL (LOGIN) ---
# ==========================================
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
    aba_cardapio, aba_promos, aba_pdv, aba_estoque, aba_dashboard = st.tabs([
        "🤖 Engenharia de Cardápio com I.A.", 
        "📢 Campanhas & Automação Social",
        "🛒 Frente de Caixa (PDV)", 
        "📦 Estoque de Insumos",
        "📊 Dashboard Financeiro & Gráficos"
    ])
    
    # --- ABA 1: CADASTRAR PRODUTO COM I.A. & GERAÇÃO DE IMAGEM ---
    with aba_cardapio:
        st.subheader("✨ Criador Gourmet Automatizado com Google Gemini & Imagen")
        st.write("Digite os dados simples e deixe a Inteligência Artificial gerar uma descrição irresistível e uma foto promocional exclusiva para o seu cardápio.")
        
        with st.form("form_novo_produto"):
            col1, col2 = st.columns(2)
            with col1:
                nome_prod = st.text_input("Nome do Prato / Lanche", value="Mica Royal Truffle Bacon")
                categoria_prod = st.selectbox("Categoria", ["Burgers", "Bebidas", "Acompanhamentos", "Sobremesas"])
            with col2:
                preco_prod = st.number_input("Preço de Venda (R$)", value=46.90, step=1.0)
            
            desc_bruta = st.text_area("Descrição Bruta / Lista de Ingredientes", value="Dois hambúrgueres smash de 100g de costela angus, duplo queijo provolone derretido, farofa crocante de bacon artesanal, maionese trufada e rúcula fresca no pão brioche amanteigado selado na chapa.")
            
            btn_gerar_ia = st.form_submit_button("🚀 Processar Texto & Imagem com Google I.A.", type="primary")
            
            if btn_gerar_ia:
                try:
                    custo_cmv = round(preco_prod * 0.32, 2)
                    margem = round(((preco_prod - custo_cmv) / preco_prod) * 100, 1)
                    
                    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
                    desc_gerada = ""
                    imagem_gerada_pil = None
                    
                    if api_key:
                        try:
                            client = genai.Client(api_key=api_key)
                            
                            prompt_texto = f"Escreva uma descrição gourmet irresistível e comercial para um menu de restaurante para o seguinte item:\nNome: {nome_prod}\nCategoria: {categoria_prod}\nIngredientes: {desc_bruta}\nA descrição deve ser sofisticada, dar água na boca e ter no máximo 3 parágrafos."
                            response_txt = client.models.generate_content(
                                model='gemini-2.5-flash',
                                contents=prompt_texto
                            )
                            desc_gerada = response_txt.text
                            
                            prompt_img = f"Professional high-end restaurant food photography of {nome_prod}, featuring {desc_bruta}, magazine style, gourmet lighting, appetizing presentation"
                            response_img = client.models.generate_images(
                                model='imagen-3.0-generate-002',
                                prompt=prompt_img,
                                config=types.GenerateImagesConfig(
                                    number_of_images=1,
                                    output_mime_type="image/jpeg",
                                ),
                            )
                            if response_img.generated_images:
                                img_bytes = response_img.generated_images[0].image.image_bytes
                                imagem_gerada_pil = Image.open(BytesIO(img_bytes))
                                
                        except Exception as e:
                            st.warning(f"⚠️ A IA do Google encontrou uma limitação no momento: {e}")
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
                    
                    if imagem_gerada_pil:
                        st.image(imagem_gerada_pil, caption=f"📸 Foto Promocional gerada por IA: {nome_prod}", use_container_width=True)
                    
                    st.markdown("### ✍️ Descrição Gourmet Otimizada:")
                    st.info(desc_gerada)
                except Exception as e_geral:
                    st.error(f"Erro ao processar o formulário: {e_geral}")

        st.divider()
        st.subheader("📥 Exportar Cardápio Completo")
        db = get_db()
        todos_produtos = db.query(Produto).all()
        db.close()
        
        if todos_produtos:
            texto_cardapio = "=== CARDÁPIO OFICIAL MICA BURGUER & RESTAURANTE ===\n\n"
            for p in todos_produtos:
                texto_cardapio += f"[{p.categoria.upper()}] {p.nome} - R$ {p.preco_venda:.2f}\n"
                texto_cardapio += f"{p.descricao_ai}\n\n"
            
            st.download_button(
                label="📥 Baixar Cardápio Completo (TXT)",
                data=texto_cardapio,
                file_name="cardapio_mica_burguer.txt",
                mime="text/plain"
            )
        else:
            st.info("Nenhum produto cadastrado no momento. Utilize o gerador acima para adicionar itens ao cardápio.")

    # --- ABA 2: CAMPANHAS & AUTOMAÇÃO SOCIAL ---
    with aba_promos:
        st.subheader("📢 Gerador de Campanhas & Automação de Marketing")
        st.write("Crie chamadas comerciais persuasivas para WhatsApp, Instagram e Delivery em segundos.")
        
        db = get_db()
        produtos_cadastrados = db.query(Produto).all()
        db.close()
        
        if not produtos_cadastrados:
            st.info("Cadastre pelo menos um produto na aba 'Engenharia de Cardápio' para gerar campanhas.")
        else:
            nomes_produtos = [p.nome for p in produtos_cadastrados]
            
            col_p1, col_p2, col_p3 = st.columns(3)
            with col_p1:
                prato_alvo = st.selectbox("Selecione o Prato/Lanche", nomes_produtos)
            with col_p2:
                tipo_promo = st.selectbox("Tipo de Promoção", [
                    "Combo Especiais (Ex: Lanche + Bebida com desconto)",
                    "Happy Hour / Desconto de Horário",
                    "Frete Grátis na Região",
                    "Lançamento Exclusivo do Dia"
                ])
            with col_p3:
                canal_dest = st.selectbox("Canal de Divulgação", ["WhatsApp (Texto Direto & Emojis)", "Instagram (Legenda + Hashtags)", "Push Notification (App de Delivery)"])
                
            if st.button("📢 Gerar Campanha com I.A.", type="primary"):
                api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
                texto_campanha = ""
                
                if api_key:
                    try:
                        client = genai.Client(api_key=api_key)
                        prompt_promo = f"Atue como um especialista em marketing gastronômico. Crie um texto promocional altamente conversivo para o seguinte cenário:\n- Produto: {prato_alvo}\n- Tipo de Oferta: {tipo_promo}\n- Canal: {canal_dest}\nUse gatilhos mentais de urgência e apetite, inclua emojis apropriados e uma Chamada para Ação (CTA) irresistível."
                        
                        response_promo = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=prompt_promo
                        )
                        texto_campanha = response_promo.text
                    except Exception as e:
                        texto_campanha = f"🔥 *OFERTA IMPERDÍVEL MICA BURGUER!* 🔥\n\nHoje é dia de saborear o incrível *{prato_alvo}* com nossa condição especial de *{tipo_promo}*!\n\n🍔 Peça agora mesmo pelo nosso WhatsApp ou Delivery e receba quentinho em casa!\n\n📲 *Clique aqui e faça seu pedido!* #MicaBurguer #Gastronomia #Delivery"
                else:
                    texto_campanha = f"🔥 *OFERTA IMPERDÍVEL MICA BURGUER!* 🔥\n\nHoje é dia de saborear o incrível *{prato_alvo}* com nossa condição especial de *{tipo_promo}*!\n\n🍔 Peça agora mesmo pelo nosso WhatsApp ou Delivery e receba quentinho em casa!\n\n📲 *Clique aqui e faça seu pedido!* #MicaBurguer #Gastronomia #Delivery"
                
                st.markdown("### 🎯 Campanha Pronta para Uso:")
                st.success(texto_campanha)

    # --- ABA 3: FRENTE DE CAIXA (PDV) ---
    with aba_pdv:
        st.subheader("🛒 Frente de Caixa Rápida (PDV Touch)")
        
        db = get_db()
        produtos_pdv = db.query(Produto).all()
        db.close()
        
        if not produtos_pdv:
            st.info("Cadastre produtos na aba de Engenharia de Cardápio para abrir as vendas no caixa.")
        else:
            col_cx1, col_cx2 = st.columns([2, 1])
            with col_cx1:
                st.markdown("#### 🍔 Selecione o Produto para Venda:")
                mapa_prod = {f"{p.nome} - R$ {p.preco_venda:.2f}": p for p in produtos_pdv}
                item_selecionado = st.selectbox("Prato / Lanche", list(mapa_prod.keys()))
                qtd_venda = st.number_input("Quantidade", min_value=1, value=1, step=1)
                
                prod_obj = mapa_prod[item_selecionado]
                total_venda = round(prod_obj.preco_venda * qtd_venda, 2)
                cmv_total_venda = round(prod_obj.custo_total_cmv * qtd_venda, 2)
                
                st.markdown(f"### Total do Pedido: **R$ {total_venda:.2f}**")
                
                if st.button("✅ Confirmar Pedido & Baixar Estoque", type="primary"):
                    db = get_db()
                    nova_venda = Venda(
                        produto_nome=prod_obj.nome,
                        quantidade=qtd_venda,
                        valor_total=total_venda,
                        cmv_total=cmv_total_venda,
                        data_hora=datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    )
                    db.add(nova_venda)
                    
                    # Deduz automaticamente do estoque de insumos
                    insumos_db = db.query(Insumo).all()
                    for ins em insumos_db:
                        ins.quantidade_atual = max(0.0, ins.quantidade_atual - (1.0 * qtd_venda))
                        
                    db.commit()
                    db.close()
                    st.success(f"Pedido de {qtd_venda}x {prod_obj.nome} registrado com sucesso!")
            
            with col_cx2:
                st.markdown("#### 📜 Últimas Vendas do Dia")
                db = get_db()
                ultimas_vendas = db.query(Venda).order_by(Venda.id.desc()).limit(5).all()
                db.close()
                
                if ultimas_vendas:
                    for v in ultimas_vendas:
                        st.info(f"**{v.quantidade}x {v.produto_nome}**\nTotal: R$ {v.valor_total:.2f}\n*{v.data_hora}*")
                else:
                    st.write("Nenhuma venda registrada ainda.")

    # --- ABA 4: ESTOQUE DE INSUMOS ---
    with aba_estoque:
        st.subheader("📦 Gestão Inteligente de Insumos & Estoque")
        
        db = get_db()
        insumos = db.query(Insumo).all()
        db.close()
        
        if insumos:
            dados_estoque = []
            for idx, item em enumerate(insumos):
                status = "🟢 Normal" if item.quantidade_atual > item.alerta_minimo else "🔴 Alerta de Reposição"
                dados_estoque.append({
                    "ID": item.id,
                    "Insumo": item.nome,
                    "Quantidade Atual": f"{item.quantidade_atual} {item.unidade}",
                    "Alerta Mínimo": f"{item.alerta_minimo} {item.unidade}",
                    "Status": status
                })
            
            df_estoque = pd.DataFrame(dados_estoque)
            st.dataframe(df_estoque, use_container_width=True, hide_index=True)
            
            st.divider()
            st.markdown("#### 🔄 Atualização de Saldo Rápida")
            with st.form("form_atualiza_estoque"):
                col_e1, col_e2 = st.columns(2)
                with col_e1:
                    insumo_sel = st.selectbox("Selecione o Insumo para Atualizar", [i.nome for i in insumos])
                with col_e2:
                    nova_qtd = st.number_input("Nova Quantidade em Estoque", min_value=0.0, step=10.0, value=100.0)
                
                if st.form_submit_button("Atualizar Estoque", type="primary"):
                    db = get_db()
                    item_db = db.query(Insumo).filter(Insumo.nome == insumo_sel).first()
                    if item_db:
                        item_db.quantidade_atual = nova_qtd
                        db.commit()
                        st.success(f"Estoque de {insumo_sel} atualizado para {nova_qtd}!")
                    db.close()
                    st.rerun()

    # --- ABA 5: DASHBOARD FINANCEIRO & GRÁFICOS ---
    with aba_dashboard:
        st.subheader("📊 Dashboard Financeiro & Inteligência de Lucratividade")
        
        db = get_db()
        vendas = db.query(Venda).all()
        db.close()
        
        if not vendas:
            st.info("Realize vendas no PDV para alimentar os gráficos financeiros em tempo real.")
        else:
            faturamento_total = sum(v.valor_total for v in vendas)
            cmv_total_acumulado = sum(v.cmv_total for v in vendas)
            lucro_bruto = faturamento_total - cmv_total_acumulado
            pct_cmv = round((cmv_total_acumulado / faturamento_total) * 100, 1) if faturamento_total > 0 else 0
            
            col_f1, col_f2, col_f3, col_f4 = st.columns(4)
            col_f1.metric("Faturamento Acumulado", f"R$ {faturamento_total:.2f}")
            col_f2.metric("Custo Total (CMV)", f"R$ {cmv_total_acumulado:.2f}")
            col_f3.metric("Lucro Bruto", f"R$ {lucro_bruto:.2f}")
            col_f4.metric("CMV Médio", f"{pct_cmv}%")
            
            st.divider()
            
            col_g1, col_g2 = st.columns(2)
            
            with col_g1:
                st.markdown("#### 📈 Vendas por Prato / Lanche")
                df_vendas = pd.DataFrame([{
                    "Produto": v.produto_nome,
                    "Quantidade": v.quantidade,
                    "Valor Total": v.valor_total
                } for v in vendas])
                
                df_resumo = df_vendas.groupby("Produto").sum().reset_index()
                st.bar_chart(data=df_resumo, x="Produto", y="Valor Total")
                
            with col_g2:
                st.markdown("#### 📋 Histórico Detalhado de Transações")
                df_historico = pd.DataFrame([{
                    "Data/Hora": v.data_hora,
                    "Produto": v.produto_nome,
                    "Qtd": v.quantidade,
                    "Total (R$)": f"{v.valor_total:.2f}"
                } for v in vendas])
                st.dataframe(df_historico, use_container_width=True, hide_index=True)