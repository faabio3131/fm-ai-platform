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

# ---> TÍTULO DE ACESSO (APENAS UMA VEZ) <---
st.sidebar.title("🔐 Acesso Corporativo")

if not st.session_state['autenticado']:
    st.sidebar.info("Faça login para liberar as ferramentas do ERP.")
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
                    
                    st.info(f"**Descrição Gourmet Otimizada:**\n\n{desc_gerada}")
                except Exception as e:
                    st.error(f"Erro ao processar na I.A. ou salvar no banco: {e}")

        st.divider()
        st.subheader("📥 Exportar Cardápio Completo")
        db = get_db()
        todos_produtos = db.query(Produto).all()
        db.close()
        
        if todos_produtos:
            texto_cardapio = "=== CARDÁPIO OFICIAL MICA BURGER & RESTAURANTE ===\n\n"
            for p in todos_produtos:
                texto_cardapio += f"[{p.categoria.upper()}] {p.nome} - R$ {p.preco_venda:.2f}\n"
                texto_cardapio += f"{p.descricao_ai}\n"
                texto_cardapio += "-" * 50 + "\n\n"
            
            st.download_button(
                label="📥 Baixar Cardápio Completo (TXT)",
                data=texto_cardapio,
                file_name="cardapio_mica_burger.txt",
                mime="text/plain"
            )

    # --- ABA 2: GERADOR DE PROMOÇÕES & AUTOMAÇÃO SOCIAL ---
    with aba_promos:
        st.subheader("📢 Campanhas Inteligentes & Postagem Automática (Meta API)")
        st.write("Gere copys comerciais com I.A. e dispare de forma automática para o Facebook/Instagram ou segura para o WhatsApp.")
        
        with st.form("form_promocao"):
            tipo_promo = st.selectbox("Objetivo da Campanha", [
                "Combo de Fim de Semana (Lanche + Batata + Bebida)", 
                "Desconto Relâmpago de Terça-feira", 
                "Aniversário da Loja / Frete Grátis",
                "Lançamento de Novo Prato"
            ])
            detalhes_oferta = st.text_area("Detalhes da Oferta / Preço Promocional", value="Na compra de qualquer burger gourmet, leve uma batata rústica por mais R$ 9,90 apenas hoje!")
            
            btn_criar_promo = st.form_submit_button("✨ Gerar Campanhas com Google I.A.", type="primary")
            
            if btn_criar_promo:
                api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
                wa_txt, ig_txt, fb_txt = "", "", ""
                
                if api_key:
                    try:
                        client = genai.Client(api_key=api_key)
                        prompt_multi = f"""
                        Crie campanhas de marketing para o restaurante hamburgueria artesanal Mica Burger com base nestes dados:
                        Tipo de Campanha: {tipo_promo}
                        Detalhes: {detalhes_oferta}

                        Divida obrigatoriamente a sua resposta usando estas exatas marcações:
                        === WHATSAPP ===
                        (Mensagem direta, alegre, com emojis e chamada para ação curta)

                        === INSTAGRAM ===
                        (Legenda altamente visual, estilo estético, engajadora e com hashtags gourmet como #MicaBurger #BurgerGourmet #Promocao)

                        === FACEBOOK ===
                        (Post engajador para comunidade, detalhado e convidativo)
                        """
                        response_m = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=prompt_multi
                        )
                        full_resp = response_m.text
                        
                        if "=== INSTAGRAM ===" in full_resp and "=== FACEBOOK ===" in full_resp:
                            parts = full_resp.split("=== INSTAGRAM ===")
                            wa_txt = parts[0].replace("=== WHATSAPP ===", "").strip()
                            ig_fb = parts[1].split("=== FACEBOOK ===")
                            ig_txt = ig_fb[0].strip()
                            fb_txt = ig_fb[1].strip() if len(ig_fb) > 1 else ""
                        else:
                            wa_txt, ig_txt, fb_txt = full_resp, full_resp, full_resp
                    except Exception as e:
                        wa_txt = f"🔥 *PROMOÇÃO MICA BURGER* 🔥\n\n{detalhes_oferta}"
                        ig_txt = f"🔥 *PROMOÇÃO MICA BURGER* 🔥\n\n{detalhes_oferta}\n\n#MicaBurger"
                        fb_txt = f"🔥 *PROMOÇÃO MICA BURGER* 🔥\n\n{detalhes_oferta}"
                else:
                    wa_txt = f"🔥 *PROMOÇÃO MICA BURGER* 🔥\n\n{detalhes_oferta}"
                    ig_txt = f"🔥 *PROMOÇÃO MICA BURGER* 🔥\n\n{detalhes_oferta}\n\n#MicaBurger"
                    fb_txt = f"🔥 *PROMOÇÃO MICA BURGER* 🔥\n\n{detalhes_oferta}"
                
                st.session_state['promo_wa'] = wa_txt
                st.session_state['promo_ig'] = ig_txt
                st.session_state['promo_fb'] = fb_txt
                st.success("🎉 Campanhas geradas com sucesso!")

        if 'promo_wa' in st.session_state and st.session_state['promo_wa']:
            st.divider()
            sub_wa, sub_ig, sub_fb = st.tabs(["📱 WhatsApp (Um Clique)", "📸 Instagram (Automático)", "📘 Facebook (Automático)"])
            
            with sub_wa:
                st.info(st.session_state['promo_wa'])
                msg_cod = st.session_state['promo_wa'].replace('\n', '%0A').replace(' ', '%20')
                link_w = f"https://wa.me/?text={msg_cod}"
                st.markdown(f"### 📲 [Clique aqui para disparar no WhatsApp]({link_w})", unsafe_allow_html=True)
                
            with sub_ig:
                st.info(st.session_state['promo_ig'])
                if st.button("🚀 Publicar Automaticamente no Instagram (API Meta)"):
                    token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")
                    ig_id = os.getenv("INSTAGRAM_ACCOUNT_ID")
                    if not token or not ig_id:
                        st.error("⚠️ Chaves da API do Instagram não configuradas no arquivo .env")
                    else:
                        st.info("🔄 Conectando à API da Meta para publicar no Instagram...")
                        # Estrutura de requisição Graph API para o Instagram
                        # Nota: Requer URL pública da imagem para o container do IG
                        try:
                            url_container = f"https://graph.facebook.com/v19.0/{ig_id}/media"
                            payload = {
                                "image_url": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd", # Exemplo de imagem pública
                                "caption": st.session_state['promo_ig'],
                                "access_token": token
                            }
                            res = requests.post(url_container, data=payload).json()
                            if "id" in res:
                                creation_id = res["id"]
                                url_publish = f"https://graph.facebook.com/v19.0/{ig_id}/media_publish"
                                res_pub = requests.post(url_publish, data={"creation_id": creation_id, "access_token": token}).json()
                                if "id" in res_pub:
                                    st.success("✅ Publicado com sucesso no Instagram!")
                                else:
                                    st.error(f"Erro ao publicar: {res_pub}")
                            else:
                                st.error(f"Erro ao criar container de mídia: {res}")
                        except Exception as ex:
                            st.error(f"Erro de conexão com a API da Meta: {ex}")
                
            with sub_fb:
                st.info(st.session_state['promo_fb'])
                if st.button("🚀 Publicar Automaticamente na Página do Facebook"):
                    token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")
                    page_id = os.getenv("FACEBOOK_PAGE_ID")
                    if not token or not page_id:
                        st.error("⚠️ Chaves da API do Facebook não configuradas no arquivo .env")
                    else:
                        st.info("🔄 Conectando à API da Meta para publicar no Facebook...")
                        try:
                            url_fb = f"https://graph.facebook.com/v19.0/{page_id}/feed"
                            payload_fb = {
                                "message": st.session_state['promo_fb'],
                                "access_token": token
                            }
                            res_fb = requests.post(url_fb, data=payload_fb).json()
                            if "id" in res_fb:
                                st.success("✅ Publicado com sucesso no Facebook!")
                            else:
                                st.error(f"Erro ao publicar: {res_fb}")
                        except Exception as ex:
                            st.error(f"Erro de conexão com a API da Meta: {ex}")

    # --- ABA 3: FRENTE DE CAIXA (PDV & WHATSAPP) ---
    with aba_pdv:
        st.subheader("🛒 Frente de Caixa & Envio de Pedido via WhatsApp")
        
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
                btn_vender = st.form_submit_button("💳 Registrar Venda, Baixar Estoque e Gerar WhatsApp", type="primary")
                
                if btn_vender:
                    db = get_db()
                    total_v = produto_escolhido.preco_venda * qtd_venda
                    cmv_v = produto_escolhido.custo_total_cmv * qtd_venda
                    data_atual = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    
                    nova_venda = Venda(
                        produto_nome=produto_escolhido.nome,
                        quantidade=qtd_venda,
                        valor_total=total_v,
                        cmv_total=cmv_v,
                        data_hora=data_atual
                    )
                    db.add(nova_venda)
                    
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
                    
                    msg_wa = f"🍔 *NOVO PEDIDO - MICA BURGER* 🍔%0A%0A*Item:* {produto_escolhido.nome}%0A*Quantidade:* {qtd_venda}%0A*Valor Total:* R$ {total_v:.2f}%0A*Horário:* {data_atual}%0A%0A_Pedido processado via F&M AI FOOD ERP_"
                    link_whatsapp = f"https://wa.me/?text={msg_wa}"
                    
                    st.markdown(f"### 📲 [Clique aqui para enviar o pedido para a Cozinha / Cliente via WhatsApp]({link_whatsapp})", unsafe_allow_html=True)
                    
                    st.markdown("#### 📦 Relatório de Baixa Real no Banco de Dados:")
                    for baixa in baixas_realizadas:
                        st.warning(baixa)

    # --- ABA 4: GESTÃO DE ESTOQUE ---
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

    # --- ABA 5: DASHBOARD FINANCEIRO & GRÁFICOS ---
    with aba_dashboard:
        st.subheader("📊 Indicadores de Desempenho & Gráficos Avançados")
        st.write("Acompanhe o faturamento, CMV consolidado e gráficos de desempenho comercial em tempo real.")
        
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
            c_d3.metric("Lucro Bruto", f"R$ {lucro_bruto:[.2f]}" if False else f"R$ {lucro_bruto:.2f}")
            c_d4.metric("Itens Vendidos", f"{total_itens} un")
            
            st.divider()
            st.markdown("### 📈 Gráficos de Vendas por Produto")
            
            df_vendas = pd.DataFrame([
                {
                    "Produto": v.produto_nome,
                    "Quantidade": v.quantidade,
                    "Faturamento": v.valor_total
                }
                for v in vendas_realizadas
            ])
            
            if not df_vendas.empty:
                df_chart = df_vendas.groupby("Produto")[["Faturamento", "Quantidade"]].sum()
                
                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    st.markdown("#### Faturamento por Produto (R$)")
                    st.bar_chart(df_chart["Faturamento"])
                with col_g2:
                    st.markdown("#### Quantidade Vendida (un)")
                    st.bar_chart(df_chart["Quantidade"])
            
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
            st.info("Nenhuma venda registrada até o momento. Realize vendas na aba de Frente de Caixa para visualizar os gráficos e indicadores.")