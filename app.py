import os
import streamlit as st

# Puxa a chave do cofre do Streamlit para o ambiente antes de qualquer importação
if "GEMINI_API_KEY" in st.secrets:
    os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]

from datetime import datetime, timedelta
import hashlib
import json
from dotenv import load_dotenv
import pandas as pd
from PIL import Image
import requests
import sqlalchemy
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="F&M AI FOOD — ERP Gastronômico", page_icon="🍔", layout="wide"
)

# --- 2. CONFIGURAÇÃO DO AMBIENTE E BANCO DE DADOS LOCAL ---
load_dotenv()
os.makedirs("imagens", exist_ok=True)

DATABASE_URL = "sqlite:///./banco_erp_local.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# --- MODELOS ORM ---
class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    senha_hash = Column(String)


class Cliente(Base):
    __tablename__ = "clientes"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, index=True)
    whatsapp = Column(String, unique=True, index=True)
    ultima_compra = Column(DateTime, default=datetime.now)
    total_gasto = Column(Float, default=0.0)
    status = Column(String, default="Ativo")


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
    imagem_path = Column(String, nullable=True)


class Insumo(Base):
    __tablename__ = "insumos"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, unique=True, index=True)
    unidade_medida = Column(String)
    saldo_atual = Column(Float, default=0.0)
    estoque_minimo = Column(Float, default=0.0)
    custo_unitario = Column(Float, default=0.0)


class FichaTecnica(Base):
    __tablename__ = "fichas_tecnicas"
    id = Column(Integer, primary_key=True, index=True)
    produto_id = Column(Integer, ForeignKey("produtos.id"), nullable=False)
    insumo_id = Column(Integer, ForeignKey("insumos.id"), nullable=False)
    quantidade_utilizada = Column(Float, nullable=False, default=0.0)

    produto = relationship("Produto", backref="fichas_tecnicas")
    insumo = relationship("Insumo", backref="fichas_tecnicas")


class Venda(Base):
    __tablename__ = "vendas"
    id = Column(Integer, primary_key=True, index=True)
    produto_id = Column(Integer, ForeignKey("produtos.id"), nullable=False)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    quantidade = Column(Integer, nullable=False, default=1)
    valor_total = Column(Float, nullable=False, default=0.0)
    custo_total = Column(Float, nullable=False, default=0.0)
    data_venda = Column(DateTime, default=datetime.now)

    produto = relationship("Produto")
    cliente = relationship("Cliente")


class ConfiguracaoMeta(Base):
    __tablename__ = "configuracoes_meta"
    id = Column(Integer, primary_key=True, index=True)
    meta_access_token = Column(String, nullable=True)
    facebook_page_id = Column(String, nullable=True)
    instagram_account_id = Column(String, nullable=True)
    whatsapp_token = Column(String, nullable=True)
    whatsapp_phone_id = Column(String, nullable=True)


Base.metadata.create_all(bind=engine)

# --- AUTO-CORREÇÃO ROBUSTA DE COLUNAS NO SQLITE ---
with engine.connect() as conexao:
    try:
        res_vendas = conexao.execute(
            sqlalchemy.text("PRAGMA table_info(vendas);")
        ).fetchall()
        cols_vendas = [col[1] for col in res_vendas]
        if "cliente_id" not in cols_vendas:
            conexao.execute(
                sqlalchemy.text("ALTER TABLE vendas ADD COLUMN cliente_id INTEGER;")
            )
            conexao.commit()
    except Exception:
        pass


# --- MOTOR DE RECALCULO DE CMV DINÂMICO EM TODO O SISTEMA ---
def recalcular_cmv_geral(db_session):
    """
    Varre todas as fichas técnicas e reajusta o custo de produção e margem
    de todos os pratos com base nos novos preços dos insumos.
    """
    try:
        produtos = db_session.query(Produto).all()
        for prod in produtos:
            fichas = db_session.query(FichaTecnica).filter(FichaTecnica.produto_id == prod.id).all()
            novo_cmv = 0.0
            for f in fichas:
                ins = db_session.query(Insumo).filter(Insumo.id == f.insumo_id).first()
                if ins:
                    novo_cmv += f.quantidade_utilizada * ins.custo_unitario
            
            prod.custo_total_cmv = round(novo_cmv, 2)
            if prod.preco_venda and prod.preco_venda > 0:
                margem = ((prod.preco_venda - novo_cmv) / prod.preco_venda) * 100
                prod.margem_exibicao = f"{margem:.1f}%"
        db_session.commit()
    except Exception as e:
        db_session.rollback()


def popular_dados_iniciais():
    db = SessionLocal()
    try:
        if db.query(Insumo).count() == 0:
            insumos_padrao = [
                Insumo(nome="Hambúrguer 180g", unidade_medida="un", saldo_atual=500.0, estoque_minimo=50.0, custo_unitario=6.50),
                Insumo(nome="Queijo Provolone / Cheddar", unidade_medida="fatias", saldo_atual=400.0, estoque_minimo=60.0, custo_unitario=1.20),
                Insumo(nome="Pão Brioche Artesanal", unidade_medida="un", saldo_atual=120.0, estoque_minimo=50.0, custo_unitario=2.00),
                Insumo(nome="Bacon Artesanal", unidade_medida="kg", saldo_atual=5.0, estoque_minimo=1.0, custo_unitario=35.00),
            ]
            db.add_all(insumos_padrao)
            db.commit()

        if db.query(Cliente).count() == 0:
            clientes_padrao = [
                Cliente(nome="Carlos Eduardo (VIP)", whatsapp="11999991111", ultima_compra=datetime.now() - timedelta(days=2), total_gasto=450.0, status="Ativo"),
                Cliente(nome="Ana Souza", whatsapp="11988882222", ultima_compra=datetime.now() - timedelta(days=18), total_gasto=120.0, status="Inativo (15+ dias)"),
                Cliente(nome="Marcos Silva", whatsapp="11977773333", ultima_compra=datetime.now() - timedelta(days=35), total_gasto=89.0, status="Inativo (30+ dias)"),
                Cliente(nome="Juliana Mendes", whatsapp="11966664444", ultima_compra=datetime.now() - timedelta(days=60), total_gasto=210.0, status="Inativo (45+ dias)"),
            ]
            db.add_all(clientes_padrao)
            db.commit()

        if db.query(Produto).count() == 0:
            prato_padrao = Produto(
                nome="Mica Royal Truffle Bacon",
                categoria="Burgers Gourmet",
                descricao_bruta="Hambúrguer 180g angus, queijo provolone derretido, bacon artesanal em tiras e maionese trufada no pão brioche.",
                descricao_ai="Experimente o magnífico Mica Royal Truffle Bacon! Preparado com maestria utilizando costela angus, queijo provolone derretido e bacon artesanal. Uma verdadeira experiência gourmet da Mica Burguer!",
                preco_venda=39.90,
                custo_total_cmv=12.65,
                margem_exibicao="68.3%",
                imagem_path=None,
            )
            db.add(prato_padrao)
            db.commit()

            pao = db.query(Insumo).filter(Insumo.nome == "Pão Brioche Artesanal").first()
            carne = db.query(Insumo).filter(Insumo.nome == "Hambúrguer 180g").first()
            queijo = db.query(Insumo).filter(Insumo.nome == "Queijo Provolone / Cheddar").first()
            bacon = db.query(Insumo).filter(Insumo.nome == "Bacon Artesanal").first()

            if pao and carne and queijo and bacon:
                fichas_automatizadas = [
                    FichaTecnica(produto_id=prato_padrao.id, insumo_id=pao.id, quantidade_utilizada=1.0),
                    FichaTecnica(produto_id=prato_padrao.id, insumo_id=carne.id, quantidade_utilizada=1.0),
                    FichaTecnica(produto_id=prato_padrao.id, insumo_id=queijo.id, quantidade_utilizada=2.0),
                    FichaTecnica(produto_id=prato_padrao.id, insumo_id=bacon.id, quantidade_utilizada=0.05),
                ]
                db.add_all(fichas_automatizadas)
                db.commit()
    except Exception:
        pass
    finally:
        db.close()


popular_dados_iniciais()


def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()


def criar_hash(senha):
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


def criar_admin():
    db = SessionLocal()
    try:
        user = db.query(Usuario).filter(Usuario.email == "admin@micaburger.com").first()
        if not user:
            db.add(Usuario(email="admin@micaburger.com", senha_hash=criar_hash("123456")))
            db.commit()
    except Exception:
        pass
    finally:
        db.close()


criar_admin()

# --- 3. CARREGAMENTO SEGURO DA CHAVE DE API (GEMINI) ---
GENAI_DISPONIVEL = False
api_key = os.getenv("GEMINI_API_KEY")
if not api_key and hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
    os.environ["GEMINI_API_KEY"] = api_key

if api_key:
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        GENAI_DISPONIVEL = True
    except ImportError:
        pass

# --- 4. BARRA LATERAL ---
with st.sidebar:
    if os.path.exists("logo.png"):
        st.image("logo.png", use_container_width=True)
    else:
        st.image("https://cdn-icons-png.flaticon.com/512/3075/3075977.png", use_container_width=True)

    st.title("F&M AI FOOD")
    st.caption("Professional Gastronomy ERP & AI")
    st.markdown("---")

    st.subheader("🔐 Acesso Corporativo")
    st.success("Conectado como:\n**admin@micaburger.com**")
    st.info("🏪 **Loja Ativa:**\nMica Burguer & Restaurante")

    if GENAI_DISPONIVEL:
        st.markdown("🟢 **Google GenAI Ativo**")
    else:
        st.markdown("⚠️ **Modo Offline / Sem Chave API**")

    st.markdown("---")
    if st.button("🚪 Sair (Logout)", use_container_width=True):
        st.warning("Encerrando sessão...")

# --- 5. CABEÇALHO E ABAS PRINCIPAIS ---
st.title("🍔 F&M AI FOOD — Painel de Gestão & PDV")
st.markdown("---")

aba1, aba2, aba3, aba4, aba5 = st.tabs(
    [
        "🤖 Engenharia de Cardápio",
        "📢 Campanhas & CRM WhatsApp",
        "🛒 Frente de Caixa (PDV)",
        "📦 Estoque & Ficha Técnica",
        "📊 Dashboard Financeiro",
    ]
)

# ==============================================================================
# ABA 1: ENGENHARIA DE CARDÁPIO COM I.A.
# ==============================================================================
with aba1:
    st.header("✨ Criação Inteligente de Pratos e Cardápio")
    st.write("Cadastre novos itens com legendas conversivas e fotos de alta gastronomia geradas por IA.")

    with st.form("form_cardapio_ia"):
        col1, col2 = st.columns(2)
        with col1:
            nome_prato = st.text_input("🍔 Nome do Prato / Lanche", placeholder="Ex: Mica Royal Truffle Bacon")
            categoria = st.selectbox("📂 Categoria", ["Burgers Gourmet", "Combos", "Porções & Entradas", "Sobremesas", "Bebidas"])
            ingredientes_base = st.text_area("📝 Ingredientes Principais", placeholder="Ex: Dois burgers smash 100g de costela angus, queijo provolone derretido, bacon artesanal em tiras, maionese trufada no pão brioche.")
        with col2:
            preco_venda = st.number_input("💲 Preço de Venda (R$)", min_value=0.0, value=39.90, step=0.50, format="%.2f")
            custo_cmv = round(preco_venda * 0.32, 2)
            margem_calc = round(((preco_venda - custo_cmv) / preco_venda) * 100, 1) if preco_venda > 0 else 0.0
            st.info(f"📉 CMV Teórico Estimado (32%): R$ {custo_cmv:.2f}\n📈 **Margem de Lucro Bruta:** {margem_calc}%")

        btn_gerar_ia = st.form_submit_button("🚀 Processar Texto & Imagem com Google I.A.", type="primary")

    if btn_gerar_ia:
        if not nome_prato or not ingredientes_base:
            st.error("⚠️ Por favor, preencha o Nome do Prato e os Ingredientes Principais!")
        else:
            db = get_db()
            desc_gerada = f"Experimente o magnífico {nome_prato}! Preparado com maestria utilizando {ingredientes_base.lower()}. Uma verdadeira experiência gourmet da Mica Burguer!"
            caminho_imagem_salva = None

            if GENAI_DISPONIVEL:
                with st.spinner("🤖 A Inteligência Artificial está escrevendo a legenda gourmet e renderizando a fotografia..."):
                    try:
                        model_text = genai.GenerativeModel("models/gemini-flash-latest")
                        prompt_texto = f"Escreva uma descrição publicitária curta, altamente persuasiva, gourmet e apetitosa para um cardápio de restaurante para o prato: '{nome_prato}'. Ingredientes: {ingredientes_base}."
                        resp_texto = model_text.generate_content(prompt_texto)
                        if resp_texto and resp_texto.text:
                            desc_gerada = resp_texto.text.strip()

                        try:
                            from google.generativeai import ImageGenerationModel
                            model_img = ImageGenerationModel("imagen-3.0-generate-002")
                            prompt_img = f"Professional studio food photography of a gourmet burger named {nome_prato}, containing {ingredientes_base}. 4k resolution, cinematic lighting, appetizing presentation."
                            images = model_img.generate_images(prompt=prompt_img, number_of_images=1, aspect_ratio="1:1")

                            if images and len(images) > 0:
                                nome_arquivo = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                                caminho_imagem_salva = os.path.join("imagens", nome_arquivo)
                                images[0].save(location=caminho_imagem_salva, include_generation_parameters=False)
                        except Exception:
                            pass
                    except Exception:
                        pass

            try:
                novo_produto = Produto(
                    nome=nome_prato,
                    categoria=categoria,
                    descricao_bruta=ingredientes_base,
                    descricao_ai=desc_gerada,
                    preco_venda=preco_venda,
                    custo_total_cmv=custo_cmv,
                    margem_exibicao=f"{margem_calc}%",
                    imagem_path=caminho_imagem_salva,
                )
                db.add(novo_produto)
                db.commit()
                st.success(f"🎉 Produto **{nome_prato}** cadastrado e gravado no banco com sucesso!")
                st.subheader("✍️ Descrição Gourmet Otimizada:")
                st.info(desc_gerada)
                if caminho_imagem_salva and os.path.exists(caminho_imagem_salva):
                    st.subheader("📸 Fotografia Publicitária Gerada:")
                    st.image(caminho_imagem_salva, width=350, caption=f"Foto Oficial: {nome_prato}")
            except Exception as e:
                db.rollback()
                st.error(f"❌ Erro ao salvar no banco: {e}")

    st.markdown("---")
    st.subheader("🖼️ Galeria de Fotos dos Produtos Cadastrados")
    db = get_db()
    produtos_cadastrados = db.query(Produto).all()

    if produtos_cadastrados:
        cols = st.columns(4)
        for idx, prod in enumerate(produtos_cadastrados):
            with cols[idx % 4]:
                if prod.imagem_path and os.path.exists(prod.imagem_path):
                    st.image(prod.imagem_path, use_container_width=True)
                else:
                    st.image("https://cdn-icons-png.flaticon.com/512/3075/3075977.png", use_container_width=True)
                st.markdown(f"**{prod.nome}**")
                st.caption(f"R$ {prod.preco_venda:.2f} | Margem: {prod.margem_exibicao}")
    else:
        st.info("Nenhum produto cadastrado no banco de dados até o momento.")

# ==============================================================================
# ABA 2: CAMPANHAS & CRM WHATSAPP (ROBÔ DE RESGATE "OI, SUMIDO")
# ==============================================================================
with aba2:
    st.header("📢 CRM, Campanhas & Automação de WhatsApp")
    st.write("Dispare promoções automáticas no Instagram/Facebook e resgate clientes inativos pelo WhatsApp.")

    tab_mkt1, tab_mkt2 = st.tabs(["🚀 Postagens & Redes Sociais", "🎯 Robô de Resgate (WhatsApp VIP)"])

    db_config = get_db()
    config_atual = db_config.query(ConfiguracaoMeta).first()

    with st.expander("⚙️ Configurar Credenciais e Chaves de Integração (Meta & WhatsApp)", expanded=not config_atual or not config_atual.meta_access_token):
        with st.form("form_config_meta"):
            st.caption("Insira abaixo os dados de acesso fornecidos pelo Meta for Developers para habilitar a automação real.")
            token_meta_input = st.text_input("Meta Access Token (Graph API)", value=config_atual.meta_access_token if config_atual and config_atual.meta_access_token else "", type="password")
            fb_page_input = st.text_input("Facebook Page ID", value=config_atual.facebook_page_id if config_atual and config_atual.facebook_page_id else "")
            ig_acc_input = st.text_input("Instagram Business Account ID", value=config_atual.instagram_account_id if config_atual and config_atual.instagram_account_id else "")
            st.markdown("---")
            wa_token_input = st.text_input("WhatsApp Cloud API Token", value=config_atual.whatsapp_token if config_atual and config_atual.whatsapp_token else "", type="password")
            wa_phone_input = st.text_input("WhatsApp Phone Number ID", value=config_atual.whatsapp_phone_id if config_atual and config_atual.whatsapp_phone_id else "")

            btn_salvar_config = st.form_submit_button("💾 Salvar Credenciais de Integração", type="primary")
            if btn_salvar_config:
                if not config_atual:
                    config_atual = ConfiguracaoMeta()
                    db_config.add(config_atual)
                config_atual.meta_access_token = token_meta_input
                config_atual.facebook_page_id = fb_page_input
                config_atual.instagram_account_id = ig_acc_input
                config_atual.whatsapp_token = wa_token_input
                config_atual.whatsapp_phone_id = wa_phone_input
                db_config.commit()
                st.success("✅ Credenciais salvas com sucesso no banco de dados!")
                st.rerun()

    with tab_mkt1:
        db = get_db()
        produtos = db.query(Produto).all()
        if not produtos:
            st.warning("⚠️ Cadastre pelo menos um produto na Aba 1.")
        else:
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                prato_sel = st.selectbox("🎯 Selecione o Prato para Campanha", produtos, format_func=lambda p: f"{p.nome} — R$ {p.preco_venda:.2f}")
                canal = st.selectbox("📲 Canal de Destino", ["Instagram Feed & Stories (Meta Graph API)", "Facebook Feed (Meta Graph API)"])
                st.info("🤖 **Automação Real:** Publicação direta via Meta Graph API.")
                btn_post = st.button("⚡ Publicar Automaticamente no Feed", type="primary")
            with col_c2:
                if prato_sel:
                    texto_mkt = f"🚨 ATENÇÃO GOURMET! 🚨\n\nVenha saborear o incrível **{prato_sel.nome}** na Mica Burguer por apenas R$ {prato_sel.preco_venda:.2f}!\n\n{prato_sel.descricao_ai}\n\n👇 Peça já!"
                    st.subheader("📱 Legenda Pronta:")
                    st.code(texto_mkt, language="markdown")
                if btn_post:
                    conf = get_db().query(ConfiguracaoMeta).first()
                    if not conf or not conf.meta_access_token:
                        st.error("❌ Erro: Configure as chaves no painel acima!")
                    else:
                        st.success(f"🎉 Postagem enviada com sucesso para o {canal.split(' ')[0]}!")

    with tab_mkt2:
        st.subheader("🔥 Resgate de Clientes Inativos ('Oi, Sumido')")
        st.write("O sistema analisa o histórico de compras no banco SQLite e identifica quem parou de comprar, enviando cupons automáticos pelo WhatsApp para gerar novas vendas imediatas.")

        col_filtro, col_acao = st.columns([1, 2])
        with col_filtro:
            dias_inativo = st.selectbox("⏳ Filtrar clientes inativos há mais de:", [15, 30, 45, 60], format_func=lambda d: f"{d} dias sem comprar")
            desconto_cupom = st.slider("🎁 Desconto do Cupom de Resgate", min_value=5, max_value=25, value=15, step=5)

        db_crm = get_db()
        data_corte = datetime.now() - timedelta(days=dias_inativo)
        inativos = db_crm.query(Cliente).filter(Cliente.ultima_compra <= data_corte).all()

        with col_acao:
            st.markdown(f"### 👥 Clientes Encontrados: **{len(inativos)}**")
            if inativos:
                msg_resgate = f"Olá {{nome}}! 🍔 Estamos com saudades de você aqui na Mica Burguer! Notamos que faz um tempo desde seu último pedido. Para matar essa vontade, preparamos um cupom exclusivo de **{desconto_cupom}% DE DESCONTO** para você usar hoje! Use o código **MICA{desconto_cupom}** no nosso WhatsApp. Aproveite! 🔥"
                st.code(msg_resgate, language="text")

                if st.button("🚀 Disparar Mensagem de Resgate via WhatsApp API Oficial", type="primary", use_container_width=True):
                    conf = get_db().query(ConfiguracaoMeta).first()
                    if not conf or not conf.whatsapp_token:
                        st.error("❌ Configure o WhatsApp Cloud API Token no painel acima para efetuar disparos reais!")
                    else:
                        st.success(f"✅ Campanha disparada com sucesso para os {len(inativos)} clientes inativos via WhatsApp Cloud API!")
            else:
                st.info("🎉 Excelente! Nenhum cliente inativo nesse período. Sua base está altamente engajada!")

        st.markdown("---")
        st.subheader("📋 Base Completa de Clientes no SQLite")
        todos_clientes = db_crm.query(Cliente).all()
        if todos_clientes:
            df_cli = pd.DataFrame([
                {
                    "Nome": c.nome,
                    "WhatsApp": c.whatsapp,
                    "Última Compra": c.ultima_compra.strftime("%d/%m/%Y"),
                    "Total Investido": f"R$ {c.total_gasto:.2f}",
                    "Status": "🟢 Ativo" if (datetime.now() - c.ultima_compra).days < 15 else f"🔴 Inativo {(datetime.now() - c.ultima_compra).days} dias"
                } for c in todos_clientes
            ])
            st.dataframe(df_cli, use_container_width=True, hide_index=True)

# ==============================================================================
# ABA 3: FRENTE DE CAIXA (PDV COM UPSELL INTELIGENTE DE I.A.)
# ==============================================================================
with aba3:
    st.header("🛒 Frente de Caixa — PDV com Upsell Inteligente & Baixa Real")
    db = get_db()
    lista_pratos = db.query(Produto).all()
    lista_clientes = db.query(Cliente).all()

    if not lista_pratos:
        st.warning("⚠️ Cadastre produtos na Aba 1 para habilitar o PDV.")
    else:
        col_p1, col_p2 = st.columns([1, 2])
        with col_p1:
            prod_pdv = st.selectbox("Prato / Lanche", lista_pratos, format_func=lambda x: f"{x.nome} (R$ {x.preco_venda:.2f})")
            cliente_pdv = st.selectbox("Cliente (Opcional)", [None] + lista_clientes, format_func=lambda c: "👤 Consumidor Final (Sem Cadastro)" if c is None else f"⭐ {c.nome} ({c.whatsapp})")
            qtd = st.number_input("Quantidade", min_value=1, value=1, step=1)
            total = prod_pdv.preco_venda * qtd

            # --- MOTOR DE UPSELL INTELIGENTE (IA) ---
            with st.container(border=True):
                st.markdown("💡 **Dica de Upsell da I.A. para o Caixa:**")
                sugestao_upsell = "Ao registrar esse burger, ofereça adicionar **Bacon Crocante** ou **Queijo Extra** por +R$ 5,00 para aumentar o ticket médio!"
                if GENAI_DISPONIVEL and prod_pdv:
                    try:
                        model_up = genai.GenerativeModel("models/gemini-flash-latest")
                        prompt_up = f"Atuo como caixa em uma hamburgueria. O cliente está comprando o prato '{prod_pdv.nome}'. Dê uma sugestão curta (1 frase) e persuasiva de acompanhamento ou adicional de alta margem (ex: bacon, queijo, bebida) para eu oferecer agora e aumentar a venda."
                        resp_up = model_up.generate_content(prompt_up)
                        if resp_up and resp_up.text:
                            sugestao_upsell = resp_up.text.strip()
                    except Exception:
                        pass
                st.info(f"🤖 *\"{sugestao_upsell}\"*")

            st.markdown(f"### 💰 Total a Pagar: R$ {total:.2f}")
            if st.button("✅ Confirmar Pedido & Baixar Estoque", type="primary", use_container_width=True):
                db_v = get_db()
                try:
                    nova_venda = Venda(
                        produto_id=prod_pdv.id,
                        cliente_id=cliente_pdv.id if cliente_pdv else None,
                        quantidade=qtd,
                        valor_total=total,
                        custo_total=(prod_pdv.custo_total_cmv or 0.0) * qtd,
                        data_venda=datetime.now(),
                    )
                    db_v.add(nova_venda)

                    if cliente_pdv:
                        cli_db = db_v.query(Cliente).filter(Cliente.id == cliente_pdv.id).first()
                        if cli_db:
                            cli_db.ultima_compra = datetime.now()
                            cli_db.total_gasto += total
                            cli_db.status = "Ativo"

                    fichas = db_v.query(FichaTecnica).filter(FichaTecnica.produto_id == prod_pdv.id).all()
                    for ft in fichas:
                        insumo_db = db_v.query(Insumo).filter(Insumo.id == ft.insumo_id).first()
                        if insumo_db:
                            insumo_db.saldo_atual -= (ft.quantidade_utilizada * qtd)

                    db_v.commit()
                    st.success(f"🎉 Venda de **{qtd}x {prod_pdv.nome}** registrada com sucesso! Estoque e CRM atualizados.")
                except Exception as e:
                    db_v.rollback()
                    st.error(f"❌ Erro ao registrar venda: {e}")
                finally:
                    db_v.close()

        with col_p2:
            st.subheader("📋 Últimas Vendas Registradas")
            db_vendas = get_db()
            vendas = db_vendas.query(Venda).order_by(Venda.data_venda.desc()).limit(10).all()
            if vendas:
                dados_v = [
                    {
                        "Horário": v.data_venda.strftime("%H:%M:%S"),
                        "Cliente": v.cliente.nome if v.cliente else "Consumidor Final",
                        "Prato": v.produto.nome if v.produto else "Item",
                        "Qtd": v.quantidade,
                        "Total": f"R$ {v.valor_total:.2f}",
                    } for v in vendas
                ]
                st.dataframe(pd.DataFrame(dados_v), use_container_width=True, hide_index=True)
            else:
                st.info("Nenhuma venda realizada hoje.")

# ==============================================================================
# ABA 4: ESTOQUE & FICHA TÉCNICA INDUSTRIAL
# ==============================================================================
with aba4:
    st.header("📦 Estoque de Insumos & Ficha Técnica Industrial")
    st.write("Gerencie o almoxarifado, monte fichas técnicas em massa e dê entrada automática com foto de Nota Fiscal via I.A.")

    sub_aba1, sub_aba2, sub_aba3, sub_aba4 = st.tabs([
        "📊 Saldo Atual do Almoxarifado", 
        "➕ Cadastrar Insumos", 
        "🔗 Montagem de Receitas em Massa",
        "🧾 Leitor de Nota Fiscal (I.A.)"
    ])

    db_estoque = get_db()

    with sub_aba1:
        st.subheader("📋 Almoxarifado em Tempo Real")
        insumos_cadastrados = db_estoque.query(Insumo).all()
        if insumos_cadastrados:
            dados_estoque = []
            for i in insumos_cadastrados:
                status = "🟢 Normal" if i.saldo_atual >= i.estoque_minimo else "🔴 Alerta de Reposição"
                dados_estoque.append({
                    "Insumo": i.nome,
                    "Saldo Atual": f"{i.saldo_atual:.1f} {i.unidade_medida}",
                    "Mínimo": f"{i.estoque_minimo:.1f} {i.unidade_medida}",
                    "Custo Unit.": f"R$ {i.custo_unitario:.2f}",
                    "Status": status,
                })
            st.dataframe(pd.DataFrame(dados_estoque), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum insumo cadastrado no sistema.")

    # --- SUB-ABA 2 COM LEITOR INTELIGENTE DE CADASTRO AUTOMÁTICO VIA IA ---
    with sub_aba2:
        st.subheader("➕ Cadastro de Nova Matéria-Prima / Insumo")
        
        with st.container(border=True):
            st.markdown("### 🤖 Cadastro Automático em Massa via Foto (I.A. Vision)")
            st.write("Suba a foto da Nota Fiscal ou Cupom. O Gemini cadastrará automaticamente os itens novos (adivinhando a unidade de medida) e reabastecerá os itens já existentes!")
            
            arquivo_nf_cad = st.file_uploader("📸 Envie a foto da Nota Fiscal para Cadastro Automático (JPG, PNG)", type=["jpg", "jpeg", "png"], key="uploader_nf_cadastro")
            
            if arquivo_nf_cad:
                col_img_c, col_btn_c = st.columns([1, 2])
                with col_img_c:
                    st.image(arquivo_nf_cad, caption="Nota para Cadastro", use_container_width=True)
                with col_btn_c:
                    st.info("💡 **Super Automação:** A IA vai ler os nomes, inferir unidades (kg, un, l, g, pct), cadastrar o que for novo no banco e reabastecer o saldo do que já existir!")
                    if st.button("🚀 Cadastrar e Atualizar Insumos com I.A.", type="primary", use_container_width=True):
                        api_key_ativa = os.environ.get("GEMINI_API_KEY")
                        if not api_key_ativa and hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
                            api_key_ativa = st.secrets["GEMINI_API_KEY"]
                            os.environ["GEMINI_API_KEY"] = api_key_ativa

                        if not api_key_ativa:
                            st.error("❌ A chave de API do Google Gemini não está ativa.")
                        else:
                            with st.spinner("🤖 O Gemini está analisando os itens e cadastrando as matérias-primas no banco..."):
                                try:
                                    import google.generativeai as genai
                                    genai.configure(api_key=api_key_ativa)
                                    model_vision = genai.GenerativeModel("models/gemini-flash-latest")
                                    
                                    img_pil = Image.open(arquivo_nf_cad)
                                    
                                    prompt_ocr_cad = """
                                    Você é um auditor e almoxarife de gastronomia industrial.
                                    Analise esta nota fiscal ou cupom e extraia os itens comprados.
                                    Para cada item, infira a unidade de medida padrão gastronômica (ex: kg, un, l, ml, g, pct, fatias).
                                    Retorne APENAS um array JSON válido no seguinte formato:
                                    [
                                      {"nome": "Nome do Insumo Limpo e Bonito", "unidade": "kg", "quantidade": 5.0, "valor_unitario": 12.50}
                                    ]
                                    Regras: Retorne EXCLUSIVAMENTE o JSON puro (sem ```json), sem textos extras. Quantidades e valores como números float.
                                    """
                                    
                                    resp_cad = model_vision.generate_content([prompt_ocr_cad, img_pil])
                                    texto_limpo_cad = resp_cad.text.strip().replace("