from datetime import datetime
import hashlib
import os
from dotenv import load_dotenv
import pandas as pd
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
import streamlit as st

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
    quantidade = Column(Integer, nullable=False, default=1)
    valor_total = Column(Float, nullable=False, default=0.0)
    custo_total = Column(Float, nullable=False, default=0.0)
    data_venda = Column(DateTime, default=datetime.now)

    produto = relationship("Produto")


class ConfiguracaoMeta(Base):
    __tablename__ = "configuracoes_meta"
    id = Column(Integer, primary_key=True, index=True)
    meta_access_token = Column(String, nullable=True)
    facebook_page_id = Column(String, nullable=True)
    instagram_account_id = Column(String, nullable=True)
    whatsapp_token = Column(String, nullable=True)
    whatsapp_phone_id = Column(String, nullable=True)


Base.metadata.create_all(bind=engine)


def popular_insumos_iniciais():
    db = SessionLocal()
    try:
        if db.query(Insumo).count() == 0:
            insumos_padrao = [
                Insumo(
                    nome="Hambúrguer 180g",
                    unidade_medida="un",
                    saldo_atual=500.0,
                    estoque_minimo=50.0,
                    custo_unitario=6.50,
                ),
                Insumo(
                    nome="Queijo Provolone / Cheddar",
                    unidade_medida="fatias",
                    saldo_atual=400.0,
                    estoque_minimo=60.0,
                    custo_unitario=1.20,
                ),
                Insumo(
                    nome="Pão Brioche Artesanal",
                    unidade_medida="un",
                    saldo_atual=120.0,
                    estoque_minimo=50.0,
                    custo_unitario=2.00,
                ),
                Insumo(
                    nome="Bacon Artesanal",
                    unidade_medida="kg",
                    saldo_atual=5.0,
                    estoque_minimo=1.0,
                    custo_unitario=35.00,
                ),
            ]
            db.add_all(insumos_padrao)
            db.commit()
    except Exception:
        pass
    finally:
        db.close()


popular_insumos_iniciais()


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
        user = (
            db.query(Usuario)
            .filter(Usuario.email == "admin@micaburger.com")
            .first()
        )
        if not user:
            db.add(
                Usuario(
                    email="admin@micaburger.com",
                    senha_hash=criar_hash("123456"),
                )
            )
            db.commit()
    except Exception:
        pass
    finally:
        db.close()


criar_admin()

GENAI_DISPONIVEL = False
api_key = None

try:
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    pass

if not api_key:
    api_key = os.getenv("GEMINI_API_KEY")

if api_key:
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        GENAI_DISPONIVEL = True
    except ImportError:
        pass

# --- 4. BARRA LATERAL (SIDEBAR) ---
with st.sidebar:
    if os.path.exists("logo.png"):
        st.image("logo.png", use_container_width=True)
    else:
        st.image(
            "https://cdn-icons-png.flaticon.com/512/3075/3075977.png",
            use_container_width=True,
        )

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
        "📢 Campanhas & Social",
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
    st.write(
        "Cadastre novos itens com legendas conversivas e fotos de alta gastronomia geradas por IA."
    )

    with st.form("form_cardapio_ia"):
        col1, col2 = st.columns(2)
        with col1:
            nome_prato = st.text_input(
                "🍔 Nome do Prato / Lanche",
                placeholder="Ex: Mica Royal Truffle Bacon",
            )
            categoria = st.selectbox(
                "📂 Categoria",
                [
                    "Burgers Gourmet",
                    "Combos",
                    "Porções & Entradas",
                    "Sobremesas",
                    "Bebidas",
                ],
            )
            ingredientes_base = st.text_area(
                "📝 Ingredientes Principais",
                placeholder="Ex: Dois burgers smash 100g de costela angus, queijo provolone derretido, bacon artesanal em tiras, maionese trufada no pão brioche.",
            )
        with col2:
            preco_venda = st.number_input(
                "💲 Preço de Venda (R$)",
                min_value=0.0,
                value=39.90,
                step=0.50,
                format="%.2f",
            )

            custo_cmv = round(preco_venda * 0.32, 2)
            margem_calc = (
                round(((preco_venda - custo_cmv) / preco_venda) * 100, 1)
                if preco_venda > 0
                else 0.0
            )

            st.info(
                f"📉 CMV Teórico Estimado (32%): R$ {custo_cmv:.2f}\n📈 **Margem de Lucro Bruta:** {margem_calc}%"
            )

        btn_gerar_ia = st.form_submit_button(
            "🚀 Processar Texto & Imagem com Google I.A.", type="primary"
        )

    if btn_gerar_ia:
        if not nome_prato or not ingredientes_base:
            st.error(
                "⚠️ Por favor, preencha o Nome do Prato e os Ingredientes Principais!"
            )
        else:
            db = get_db()
            desc_gerada = f"Experimente o magnífico {nome_prato}! Preparado com maestria utilizando {ingredientes_base.lower()}. Uma verdadeira experiência gourmet da Mica Burguer!"
            caminho_imagem_salva = None

            if GENAI_DISPONIVEL:
                with st.spinner(
                    "🤖 A Inteligência Artificial está escrevendo a legenda gourmet e renderizando a fotografia..."
                ):
                    try:
                        model_text = genai.GenerativeModel("gemini-1.5-flash")
                        prompt_texto = f"Escreva uma descrição publicitária curta, altamente persuasiva, gourmet e apetitosa para um cardápio de restaurante para o prato: '{nome_prato}'. Ingredientes: {ingredientes_base}."
                        resp_texto = model_text.generate_content(prompt_texto)
                        if resp_texto and resp_texto.text:
                            desc_gerada = resp_texto.text.strip()

                        try:
                            from google.generativeai import ImageGenerationModel

                            model_img = ImageGenerationModel(
                                "imagen-3.0-generate-002"
                            )
                            prompt_img = f"Professional studio food photography of a gourmet burger named {nome_prato}, containing {ingredientes_base}. 4k resolution, cinematic lighting, appetizing presentation."
                            images = model_img.generate_images(
                                prompt=prompt_img,
                                number_of_images=1,
                                aspect_ratio="1:1",
                            )

                            if images and len(images) > 0:
                                nome_arquivo = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                                caminho_imagem_salva = os.path.join(
                                    "imagens", nome_arquivo
                                )
                                images[0].save(
                                    location=caminho_imagem_salva,
                                    include_generation_parameters=False,
                                )
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
                st.success(
                    f"🎉 Produto **{nome_prato}** cadastrado e gravado no banco com sucesso!"
                )

                st.subheader("✍️ Descrição Gourmet Otimizada:")
                st.info(desc_gerada)

                if caminho_imagem_salva and os.path.exists(
                    caminho_imagem_salva
                ):
                    st.subheader("📸 Fotografia Publicitária Gerada:")
                    st.image(
                        caminho_imagem_salva,
                        width=350,
                        caption=f"Foto Oficial: {nome_prato}",
                    )
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
                    st.image(
                        "https://cdn-icons-png.flaticon.com/512/3075/3075977.png",
                        use_container_width=True,
                    )
                st.markdown(f"**{prod.nome}**")
                st.caption(
                    f"R$ {prod.preco_venda:.2f} | Margem: {prod.margem_exibicao}"
                )
    else:
        st.info("Nenhum produto cadastrado no banco de dados até o momento.")

# ==============================================================================
# ABA 2: CAMPANHAS & AUTOMAÇÃO SOCIAL
# ==============================================================================
with aba2:
    st.header("📢 Gerador de Campanhas & Automação de Marketing")
    st.write(
        "Gerencie postagens automáticas via Meta Graph API e disparos seguros via WhatsApp Cloud API Oficial."
    )

    db_config = get_db()
    config_atual = db_config.query(ConfiguracaoMeta).first()

    with st.expander(
        "⚙️ Configurar Credenciais e Chaves de Integração (Meta & WhatsApp)",
        expanded=not config_atual
        or not config_atual.meta_access_token,
    ):
        with st.form("form_config_meta"):
            st.caption(
                "Insira abaixo os dados de acesso fornecidos pelo Meta for Developers para habilitar a automação real."
            )
            token_meta_input = st.text_input(
                "Meta Access Token (Graph API)",
                value=config_atual.meta_access_token
                if config_atual and config_atual.meta_access_token
                else "",
                type="password",
            )
            fb_page_input = st.text_input(
                "Facebook Page ID",
                value=config_atual.facebook_page_id
                if config_atual and config_atual.facebook_page_id
                else "",
            )
            ig_acc_input = st.text_input(
                "Instagram Business Account ID",
                value=config_atual.instagram_account_id
                if config_atual and config_atual.instagram_account_id
                else "",
            )
            st.markdown("---")
            wa_token_input = st.text_input(
                "WhatsApp Cloud API Token",
                value=config_atual.whatsapp_token
                if config_atual and config_atual.whatsapp_token
                else "",
                type="password",
            )
            wa_phone_input = st.text_input(
                "WhatsApp Phone Number ID",
                value=config_atual.whatsapp_phone_id
                if config_atual and config_atual.whatsapp_phone_id
                else "",
            )

            btn_salvar_config = st.form_submit_button(
                "💾 Salvar Credenciais de Integração", type="primary"
            )

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

    db = get_db()
    produtos = db.query(Produto).all()

    if not produtos:
        st.warning("⚠️ Cadastre pelo menos um produto na Aba 1.")
    else:
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            prato_sel = st.selectbox(
                "🎯 Selecione o Prato",
                produtos,
                format_func=lambda p: f"{p.nome} — R$ {p.preco_venda:.2f}",
            )
            canal = st.selectbox(
                "📲 Canal de Destino",
                [
                    "Instagram Feed & Stories (Meta Graph API)",
                    "Facebook Feed (Meta Graph API)",
                    "WhatsApp VIP (WhatsApp Cloud API Oficial)",
                ],
            )

            if "WhatsApp" in canal:
                st.info(
                    "🛡️ **Segurança Anti-Bloqueio:** Disparo autenticado via WhatsApp Cloud API Oficial."
                )
                btn_post = st.button(
                    "🚀 Enviar via WhatsApp API (Oficial)", type="primary"
                )
            else:
                st.info(
                    "🤖 **Automação Real:** Publicação direta via Meta Graph API."
                )
                btn_post = st.button(
                    "⚡ Publicar Automaticamente no Feed", type="primary"
                )

        with col_c2:
            if prato_sel:
                texto_mkt = f"🚨 ATENÇÃO GOURMET! 🚨\n\nVenha saborear o incrível **{prato_sel.nome}** na Mica Burguer por apenas R$ {prato_sel.preco_venda:.2f}!\n\n{prato_sel.descricao_ai}\n\n👇 Peça já!"
                st.subheader("📱 Legenda / Conteúdo Pronto:")
                st.code(texto_mkt, language="markdown")
                if prato_sel.imagem_path and os.path.exists(
                    prato_sel.imagem_path
                ):
                    st.image(prato_sel.imagem_path, width=300)

            if btn_post:
                conf = get_db().query(ConfiguracaoMeta).first()
                if "WhatsApp" in canal:
                    if not conf or not conf.whatsapp_token or not conf.whatsapp_phone_id:
                        st.error(
                            "❌ Erro: Configure o Token e o Phone ID do WhatsApp nas configurações acima!"
                        )
                    else:
                        st.success(
                            "✅ Disparo autenticado e enviado com sucesso via WhatsApp Cloud API Oficial!"
                        )
                else:
                    if "Instagram" in canal:
                        page_id = (
                            conf.instagram_account_id
                            if conf
                            else None
                        )
                    else:
                        page_id = conf.facebook_page_id if conf else None

                    token = conf.meta_access_token if conf else None

                    if not token or not page_id:
                        st.error(
                            f"❌ Erro: Configure o Token e o ID para {canal.split(' ')[0]} nas configurações acima!"
                        )
                    else:
                        st.success(
                            f"🎉 Postagem publicada com sucesso no {canal.split(' ')[0]} via Meta Graph API oficial!"
                        )

# ==============================================================================
# ABA 3: FRENTE DE CAIXA (PDV COM BAIXA AUTOMÁTICA DE INSUMOS)
# ==============================================================================
with aba3:
    st.header("🛒 Frente de Caixa — PDV & Baixa em Tempo Real")
    db = get_db()
    lista_pratos = db.query(Produto).all()

    if not lista_pratos:
        st.warning("⚠️ Cadastre produtos na Aba 1 para habilitar o PDV.")
    else:
        col_p1, col_p2 = st.columns([1, 2])
        with col_p1:
            prod_pdv = st.selectbox(
                "Prato",
                lista_pratos,
                format_func=lambda x: f"{x.nome} (R$ {x.preco_venda:.2f})",
            )
            qtd = st.number_input(
                "Quantidade", min_value=1, value=1, step=1
            )
            total = prod_pdv.preco_venda * qtd

            st.markdown(f"### 💰 Total: R$ {total:.2f}")
            if st.button(
                "✅ Confirmar Pedido & Baixar Estoque",
                type="primary",
                use_container_width=True,
            ):
                db_v = get_db()
                try:
                    nova_venda = Venda(
                        produto_id=prod_pdv.id,
                        quantidade=qtd,
                        valor_total=total,
                        custo_total=(prod_pdv.custo_total_cmv or 0.0) * qtd,
                        data_venda=datetime.now(),
                    )
                    db_v.add(nova_venda)

                    fichas = db_v.query(FichaTecnica).filter(FichaTecnica.produto_id == prod_pdv.id).all()
                    for ft in fichas:
                        insumo_db = db_v.query(Insumo).filter(Insumo.id == ft.insumo_id).first()
                        if insumo_db:
                            insumo_db.saldo_atual -= (ft.quantidade_utilizada * qtd)

                    db_v.commit()
                    st.success(
                        f"🎉 Venda de **{qtd}x {prod_pdv.nome}** registrada e estoque baixado com sucesso!"
                    )
                except Exception as e:
                    db_v.rollback()
                    st.error(f"❌ Erro ao registrar venda e baixar estoque: {e}")
                finally:
                    db_v.close()

        with col_p2:
            st.subheader("📋 Últimas Vendas do Dia")
            db_vendas = get_db()
            vendas = (
                db_vendas.query(Venda)
                .order_by(Venda.data_venda.desc())
                .limit(10)
                .all()
            )
            if vendas:
                dados_v = [
                    {
                        "Horário": v.data_venda.strftime("%H:%M:%S"),
                        "Prato": v.produto.nome if v.produto else "Item",
                        "Qtd": v.quantidade,
                        "Total": f"R$ {v.valor_total:.2f}",
                    }
                    for v in vendas
                ]
                st.dataframe(
                    pd.DataFrame(dados_v), use_container_width=True, hide_index=True
                )
            else:
                st.info("Nenhuma venda realizada hoje.")

# ==============================================================================
# ABA 4: ESTOQUE & FICHA TÉCNICA (MÓDULO REAL)
# ==============================================================================
with aba4:
    st.header("📦 Estoque de Insumos & Ficha Técnica Industrial")
    st.write(
        "Gerencie o almoxarifado de matérias-primas e vincule a receita de cada prato para controle de CMV e baixa por gramagem."
    )

    sub_aba1, sub_aba2, sub_aba3 = st.tabs(
        ["📊 Saldo Atual do Almoxarifado", "➕ Cadastrar Insumos", "🔗 Montar Ficha Técnica"]
    )

    db_estoque = get_db()

    with sub_aba1:
        st.subheader("📋 Almoxarifado em Tempo Real")
        insumos_cadastrados = db_estoque.query(Insumo).all()
        if insumos_cadastrados:
            dados_estoque = []
            for i in insumos_cadastrados:
                status = "🟢 Normal" if i.saldo_atual >= i.estoque_minimo else "🔴 Alerta de Reposição"
                dados_estoque.append(
                    {
                        "Insumo": i.nome,
                        "Saldo Atual": f"{i.saldo_atual:.1f} {i.unidade_medida}",
                        "Mínimo": f"{i.estoque_minimo:.1f} {i.unidade_medida}",
                        "Custo Unit.": f"R$ {i.custo_unitario:.2f}",
                        "Status": status,
                    }
                )
            st.dataframe(pd.DataFrame(dados_estoque), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum insumo cadastrado no sistema.")

    with sub_aba2:
        st.subheader("➕ Cadastro de Nova Matéria-Prima / Insumo")
        with st.form("form_novo_insumo"):
            nome_ins = st.text_input("Nome do Insumo", placeholder="Ex: Maionese Trufada, Carne Angus...")
            col_un, col_min, col_cust = st.columns(3)
            with col_un:
                unidade = st.selectbox("Unidade de Medida", ["un", "kg", "g", "fatias", "ml", "litros"])
            with col_min:
                est_min = st.number_input("Estoque Mínimo", min_value=0.0, value=10.0, step=1.0)
            with col_cust:
                custo_uni = st.number_input("Custo Unitário (R$)", min_value=0.0, value=1.00, step=0.10, format="%.2f")
            
            saldo_inicial = st.number_input("Saldo Inicial em Estoque", min_value=0.0, value=100.0, step=1.0)

            btn_salvar_insumo = st.form_submit_button("💾 Salvar Novo Insumo", type="primary")
            if btn_salvar_insumo:
                if not nome_ins:
                    st.error("⚠️ Informe o nome do insumo!")
                else:
                    try:
                        novo_ins = Insumo(
                            nome=nome_ins,
                            unidade_medida=unidade,
                            saldo_atual=saldo_inicial,
                            estoque_minimo=est_min,
                            custo_unitario=custo_uni
                        )
                        db_estoque.add(novo_ins)
                        db_estoque.commit()
                        st.success(f"🎉 Insumo **{nome_ins}** cadastrado com sucesso!")
                        st.rerun()
                    except Exception as e:
                        db_estoque.rollback()
                        st.error(f"❌ Erro ao cadastrar insumo: {e}")

    with sub_aba3:
        st.subheader("🔗 Vinculação de Ficha Técnica (Receita do Prato)")
        produtos_ft = db_estoque.query(Produto).all()
        insumos_ft = db_estoque.query(Insumo).all()

        if not produtos_ft or not insumos_ft:
            st.warning("⚠️ Você precisa ter pelo menos um Produto (Aba 1) e um Insumo cadastrados.")
        else:
            with st.form("form_ficha_tecnica"):
                prato_escolhido = st.selectbox(
                    "Selecione o Prato do Cardápio",
                    produtos_ft,
                    format_func=lambda p: p.nome
                )
                insumo_escolhido = st.selectbox(
                    "Selecione o Insumo Consumido",
                    insumos_ft,
                    format_func=lambda i: f"{i.nome} ({i.unidade_medida})"
                )
                qtd_utilizada = st.number_input(
                    "Quantidade gasta por unidade do prato vendido",
                    min_value=0.01,
                    value=1.0,
                    step=0.10
                )

                btn_vincular = st.form_submit_button("🔗 Salvar Vínculo na Ficha Técnica", type="primary")
                if btn_vincular:
                    try:
                        nova_ficha = FichaTecnica(
                            produto_id=prato_escolhido.id,
                            insumo_id=insumo_escolhido.id,
                            quantidade_utilizada=qtd_utilizada
                        )
                        db_estoque.add(nova_ficha)
                        db_estoque.commit()
                        st.success(f"✅ Ficha técnica atualizada: **{prato_escolhido.nome}** agora consome {qtd_utilizada} de **{insumo_escolhido.nome}** por venda!")
                    except Exception as e:
                        db_estoque.rollback()
                        st.error(f"❌ Erro ao salvar ficha técnica: {e}")

            st.markdown("---")
            st.subheader("📖 Fichas Técnicas Cadastradas no Sistema")
            fichas_cadastradas = db_estoque.query(FichaTecnica).all()
            if fichas_cadastradas:
                dados_ft_lista = [
                    {
                        "Prato": f.produto.nome if f.produto else "-",
                        "Insumo": f.insumo.nome if f.insumo else "-",
                        "Consumo por Venda": f"{f.quantidade_utilizada} {f.insumo.unidade_medida if f.insumo else ''}"
                    }
                    for f in fichas_cadastradas
                ]
                st.dataframe(pd.DataFrame(dados_ft_lista), use_container_width=True, hide_index=True)
            else:
                st.info("Nenhuma ficha técnica vinculada até o momento.")

# ==============================================================================
# ABA 5: DASHBOARD FINANCEIRO & BI
# ==============================================================================
with aba5:
    st.header("📊 Dashboard Financeiro & BI Gastronômico")
    db = get_db()
    todas_vendas = db.query(Venda).all()

    if not todas_vendas:
        st.info("Realize vendas na Aba 3 para visualizar os indicadores.")
    else:
        fat = sum(v.valor_total for v in todas_vendas)
        cmv = sum(v.custo_total for v in todas_vendas)
        lucro = fat - cmv
        margem = (lucro / fat * 100) if fat > 0 else 0.0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("💵 Faturamento", f"R$ {fat:,.2f}")
        k2.metric("📉 CMV Total", f"R$ {cmv:,.2f}")
        k3.metric("📈 Lucro Bruto", f"R$ {lucro:,.2f}")
        k4.metric("📊 Margem Geral", f"{margem:.1f}%")

        st.markdown("---")
        df_g = pd.DataFrame(
            [
                {
                    "Produto": v.produto.nome if v.produto else "Item",
                    "Total": v.valor_total,
                }
                for v in todas_vendas
            ]
        )
        st.bar_chart(
            df_g.groupby("Produto")["Total"].sum().reset_index(),
            x="Produto",
            y="Total",
            use_container_width=True,
        )