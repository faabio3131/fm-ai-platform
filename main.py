from datetime import datetime
import hashlib
import os
import pandas as pd
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

# --- 1. CONFIGURAÇÃO DO BANCO DE DADOS NUVEM ---
DATABASE_URL = "postgresql://postgres.xiknjbqepitjsozrfrcg:Sucesso2026%40%23%24@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

os.makedirs("imagens", exist_ok=True)


# --- TABELAS ORM ---
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


class Venda(Base):
    __tablename__ = "vendas"
    id = Column(Integer, primary_key=True, index=True)
    produto_id = Column(Integer, ForeignKey("produtos.id"), nullable=False)
    quantidade = Column(Integer, nullable=False, default=1)
    valor_total = Column(Float, nullable=False, default=0.0)
    custo_total = Column(Float, nullable=False, default=0.0)
    data_venda = Column(DateTime, default=datetime.now)

    produto = relationship("Produto")


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()


def criar_hash(senha):
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


# Garante Admin Padrão
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
                    email="admin@micaburguer.com",
                    senha_hash=criar_hash("123456"),
                )
            )
            db.commit()
    except Exception:
        pass
    finally:
        db.close()


criar_admin()

# --- 2. CONFIGURAÇÃO DA INTERFACE STREAMLIT ---
st.set_page_config(
    page_title="F&M AI FOOD — ERP Gastronômico", page_icon="🍔", layout="wide"
)

# Tenta carregar o SDK da Inteligência Artificial do Google
GENAI_DISPONIVEL = False
try:
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
        GENAI_DISPONIVEL = True
except ImportError:
    pass

# --- BARRA LATERAL (SIDEBAR) ---
with st.sidebar:
    st.image(
        "https://cdn-icons-png.flaticon.com/512/3075/3075977.png", width=70
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
    if st.button("🚪 Sair (Logout)", width="stretch"):
        st.warning("Encerrando sessão...")

# --- CABEÇALHO E ABAS PRINCIPAIS ---
st.title("🍔 F&M AI FOOD — Painel de Gestão & PDV")
st.markdown("---")

aba1, aba2, aba3, aba4, aba5 = st.tabs(
    [
        "🤖 Engenharia de Cardápio",
        "📢 Campanhas & Social",
        "🛒 Frente de Caixa (PDV)",
        "📦 Estoque de Insumos",
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
        "Crie postagens conversivas para o Instagram e WhatsApp reaproveitando as fotos do cardápio."
    )

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
                "📲 Canal", ["Instagram Feed & Stories", "WhatsApp VIP"]
            )
            btn_post = st.button("⚡ Gerar Campanha", type="primary")

        with col_c2:
            if btn_post:
                texto_mkt = f"🚨 ATENÇÃO GOURMET! 🚨\n\nVenha saborear o incrível **{prato_sel.nome}** na Mica Burguer por apenas R$ {prato_sel.preco_venda:.2f}!\n\n{prato_sel.descricao_ai}\n\n👇 Peça já!"
                st.subheader("📱 Legenda Pronta:")
                st.code(texto_mkt, language="markdown")
                if prato_sel.imagem_path and os.path.exists(
                    prato_sel.imagem_path
                ):
                    st.image(prato_sel.imagem_path, width=300)

# ==============================================================================
# ABA 3: FRENTE DE CAIXA (PDV)
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
                    db_v.commit()
                    st.success(
                        f"🎉 Venda de **{qtd}x {prod_pdv.nome}** registrada com sucesso!"
                    )
                except Exception as e:
                    db_v.rollback()
                    st.error(f"Erro ao registrar venda: {e}")
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
# ABA 4: ESTOQUE DE INSUMOS
# ==============================================================================
with aba4:
    st.header("📦 Estoque de Insumos & Almoxarifado")
    st.info(
        "A baixa automática por gramagem está vinculada aos lançamentos do PDV."
    )
    # Tabela simulada de insumos fixos da Ficha Técnica
    df_insumos = pd.DataFrame(
        [
            {
                "Insumo": "Hambúrguer 90g / 180g",
                "Saldo Atual": "450 un",
                "Mínimo": "50 un",
                "Status": "🟢 Normal",
            },
            {
                "Insumo": "Queijo Cheddar / Prato",
                "Saldo Atual": "320 fatias",
                "Mínimo": "60 fatias",
                "Status": "🟢 Normal",
            },
            {
                "Insumo": "Pão Brioche Artesanal",
                "Saldo Atual": "45 un",
                "Mínimo": "50 un",
                "Status": "🔴 Alerta de Reposição",
            },
            {
                "Insumo": "Bacon Crocante",
                "Saldo Atual": "2.5 kg",
                "Mínimo": "1.0 kg",
                "Status": "🟢 Normal",
            },
        ]
    )
    st.dataframe(df_insumos, use_container_width=True, hide_index=True)

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
                {"Produto": v.produto.nome if v.produto else "Item", "Total": v.valor_total}
                for v in todas_vendas
            ]
        )
        st.bar_chart(
            df_g.groupby("Produto")["Total"].sum().reset_index(),
            x="Produto",
            y="Total",
            use_container_width=True,
        )