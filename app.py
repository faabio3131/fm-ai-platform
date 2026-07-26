from datetime import datetime
import os
from dotenv import load_dotenv
import pandas as pd
import sqlalchemy
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
    inspect,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import streamlit as st

# --- 1. CONFIGURAÇÃO DO AMBIENTE E BANCO DE DADOS INTEGRADO ---
load_dotenv()
os.makedirs("imagens", exist_ok=True)

DB_PATH = "banco_erp_local.db"
engine = create_engine(
    f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# --- MODELOS DO BANCO DE DADOS (ORM) ---
class Produto(Base):
    __tablename__ = "produtos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, unique=True, index=True, nullable=False)
    categoria = Column(String, nullable=False)
    preco_venda = Column(Float, nullable=False, default=0.0)
    custo_unitario = Column(Float, default=0.0)
    margem_lucro = Column(Float, default=0.0)
    imagem_path = Column(String, nullable=True)

    ingredientes = relationship(
        "FichaTecnica", back_populates="produto", cascade="all, delete-orphan"
    )
    vendas = relationship("Venda", back_populates="produto")


class Insumo(Base):
    __tablename__ = "insumos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, unique=True, index=True, nullable=False)
    quantidade_atual = Column(Float, default=0.0)
    unidade_medida = Column(String, default="un")
    alerta_minimo = Column(Float, default=10.0)
    custo_unitario = Column(Float, default=0.0)

    receitas_vinculadas = relationship(
        "FichaTecnica", back_populates="insumo", cascade="all, delete-orphan"
    )


class FichaTecnica(Base):
    __tablename__ = "ficha_tecnica"

    id = Column(Integer, primary_key=True, index=True)
    produto_id = Column(Integer, ForeignKey("produtos.id"), nullable=False)
    insumo_id = Column(Integer, ForeignKey("insumos.id"), nullable=False)
    quantidade_gasta = Column(Float, nullable=False)

    produto = relationship("Produto", back_populates="ingredientes")
    insumo = relationship("Insumo", back_populates="receitas_vinculadas")


class Venda(Base):
    __tablename__ = "vendas"

    id = Column(Integer, primary_key=True, index=True)
    produto_id = Column(Integer, ForeignKey("produtos.id"), nullable=False)
    quantidade = Column(Integer, nullable=False, default=1)
    valor_total = Column(Float, nullable=False, default=0.0)
    custo_total = Column(Float, default=0.0)
    data_venda = Column(DateTime, default=datetime.now)

    produto = relationship("Produto", back_populates="vendas")


# Criação automática das tabelas
Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()


# --- CONFIGURAÇÃO DA INTERFACE STREAMLIT ---
st.set_page_config(
    page_title="F&M AI FOOD — ERP Gastronômico", page_icon="🍔", layout="wide"
)

# Carrega API do Google Gemini se disponível
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
    st.success("Conectado como:\n**admin@micaburguer.com**")
    st.info("🏪 **Loja Ativa:**\nMica Burguer & Restaurante")

    if GENAI_DISPONIVEL:
        st.markdown("🟢 **Google GenAI Ativo**")
    else:
        st.markdown("⚠️ **Modo Offline / Sem Chave API**")

    st.markdown("---")
    if st.button("🚪 Sair (Logout)", use_container_width=True):
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
                value=38.90,
                step=0.50,
                format="%.2f",
            )
            custo_cmv = st.number_input(
                "📉 Custo Teórico dos Insumos / CMV (R$)",
                min_value=0.0,
                value=14.50,
                step=0.50,
                format="%.2f",
            )

            if preco_venda > 0:
                margem_calc = ((preco_venda - custo_cmv) / preco_venda) * 100
                st.info(f"📈 **Margem de Lucro Bruta Prevista:** {margem_calc:.1f}%")
            else:
                margem_calc = 0.0

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
            descricao_gerada = f"Experimente o magnífico {nome_prato}! Preparado com maestria utilizando {ingredientes_base.lower()}. Uma verdadeira experiência gourmet da Mica Burguer!"
            caminho_imagem_salva = None

            if GENAI_DISPONIVEL:
                with st.spinner(
                    "🤖 A Inteligência Artificial está escrevendo a legenda gourmet e renderizando a fotografia..."
                ):
                    try:
                        model_text = genai.GenerativeModel("gemini-1.5-flash")
                        prompt_texto = f"Escreva uma descrição publicitária curta, altamente persuasiva, gourmet e apetitosa para um cardápio de restaurante para o prato: '{nome_prato}'. Ingredientes: {ingredientes_base}. Use emojis e gatilhos mentais gastronômicos."
                        resp_texto = model_text.generate_content(prompt_texto)
                        if resp_texto and resp_texto.text:
                            descricao_gerada = resp_texto.text.strip()

                        try:
                            from google.generativeai import ImageGenerationModel

                            model_img = ImageGenerationModel(
                                "imagen-3.0-generate-002"
                            )
                            prompt_img = f"Professional studio food photography of a gourmet burger named {nome_prato}, containing {ingredientes_base}. 4k resolution, cinematic lighting, appetizing presentation, dark moody background, restaurant advertisement style."
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
                        except Exception as e_img:
                            st.warning(
                                f"⚠️ IA de imagem em modo de reserva ({e_img}). O texto foi gerado com sucesso."
                            )
                    except Exception as e_ia:
                        st.warning(
                            f"⚠️ Operando em Modo Offline ({e_ia}). Usando texto padrão."
                        )

            try:
                novo_produto = Produto(
                    nome=nome_prato,
                    categoria=categoria,
                    preco_venda=preco_venda,
                    custo_unitario=custo_cmv,
                    margem_lucro=margem_calc,
                    imagem_path=caminho_imagem_salva,
                )
                db.add(novo_produto)
                db.commit()
                st.success(
                    f"🎉 Produto **{nome_prato}** cadastrado e gravado com sucesso!"
                )

                st.subheader("✍️ Descrição Gourmet Otimizada:")
                st.info(descricao_gerada)

                if caminho_imagem_salva and os.path.exists(
                    caminho_imagem_salva
                ):
                    st.subheader("📸 Fotografia Publicitária Gerada:")
                    st.image(
                        caminho_imagem_salva,
                        width=350,
                        caption=f"Foto Oficial: {nome_prato}",
                    )
            except Exception as e_db:
                db.rollback()
                st.error(f"❌ Erro ao gravar no banco: {e_db}")

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
                st.caption(f"R$ {prod.preco_venda:.2f} | {prod.categoria}")
    else:
        st.info("Nenhum produto cadastrado no banco de dados até o momento.")


# ==============================================================================
# ABA 2: CAMPANHAS & AUTOMAÇÃO SOCIAL
# ==============================================================================
with aba2:
    st.header("📢 Gerador de Campanhas & Automação de Marketing")
    st.write(
        "Crie postagens conversivas para o Instagram e WhatsApp reaproveitando as fotos oficiais do seu cardápio."
    )

    db = get_db()
    produtos = db.query(Produto).all()

    if not produtos:
        st.warning(
            "⚠️ Cadastre pelo menos um produto na Aba 1 para criar campanhas promocionais."
        )
    else:
        col_camp1, col_camp2 = st.columns(2)
        with col_camp1:
            prato_selecionado = st.selectbox(
                "🎯 Selecione o Prato em Destaque",
                produtos,
                format_func=lambda p: f"{p.nome} — R$ {p.preco_venda:.2f}",
            )
            tipo_promo = st.selectbox(
                "🔥 Objetivo da Campanha",
                [
                    "Happy Hour & Desconto",
                    "Lançamento Exclusivo",
                    "Especial de Fim de Semana",
                    "Apetite Noturno / Fome da Madrugada",
                ],
            )
            canal_social = st.selectbox(
                "📲 Canal de Destino",
                ["Instagram Feed & Stories", "WhatsApp VIP / Lista", "Facebook"],
            )

            btn_gerar_post = st.button(
                "⚡ Gerar Campanha com I.A.", type="primary"
            )

        with col_camp2:
            if btn_gerar_post:
                texto_promo = f"🚨 ATENÇÃO GOURMET! 🚨\n\nChegou a hora de provar o inigualável **{prato_selecionado.nome}** na Mica Burguer! Por apenas R$ {prato_selecionado.preco_venda:.2f}, você vive uma experiência inesquecível.\n\n👇 Peça já o seu!"

                if GENAI_DISPONIVEL:
                    with st.spinner("🧠 Escrevendo copy publicitária..."):
                        try:
                            model_social = genai.GenerativeModel(
                                "gemini-1.5-flash"
                            )
                            prompt_social = f"Escreva uma postagem de marketing persuasiva e vibrante para o {canal_social} sobre o prato: '{prato_selecionado.nome}' que custa R$ {prato_selecionado.preco_venda:.2f}. Objetivo: {tipo_promo}. Inclua emojis e CTA."
                            res_social = model_social.generate_content(
                                prompt_social
                            )
                            if res_social and res_social.text:
                                texto_promo = res_social.text.strip()
                        except Exception:
                            pass

                st.subheader("📱 Legenda Pronta para Postagem:")
                st.code(texto_promo, language="markdown")

                if prato_selecionado.imagem_path and os.path.exists(
                    prato_selecionado.imagem_path
                ):
                    st.image(
                        prato_selecionado.imagem_path,
                        width=300,
                        caption=f"Foto Oficial: {prato_selecionado.nome}",
                    )


# ==============================================================================
# ABA 3: FRENTE DE CAIXA (PDV)
# ==============================================================================
with aba3:
    st.header("🛒 Frente de Caixa — PDV & Baixa em Tempo Real")
    st.write(
        "Registre os pedidos do balcão e veja a baixa de estoque acontecer por gramagem via Ficha Técnica."
    )

    db = get_db()
    lista_pratos = db.query(Produto).all()

    if not lista_pratos:
        st.warning(
            "⚠️ Cadastre produtos no cardápio para habilitar as vendas no Frente de Caixa."
        )
    else:
        col_pdv1, col_pdv2 = st.columns([1, 2])

        with col_pdv1:
            st.subheader("🍔 Lançar Pedido")
            produto_selecionado = st.selectbox(
                "Prato / Lanche",
                lista_pratos,
                format_func=lambda x: f"{x.nome} (R$ {x.preco_venda:.2f})",
            )
            quantidade = st.number_input(
                "Quantidade Vendida", min_value=1, value=1, step=1
            )

            valor_unit = produto_selecionado.preco_venda
            valor_total = valor_unit * quantidade

            st.markdown("---")
            st.markdown(f"**Preço Unitário:** R$ {valor_unit:.2f}")
            st.markdown(f"### 💰 Total do Pedido: R$ {valor_total:.2f}")

            if st.button(
                "✅ Confirmar Pedido & Baixar Estoque",
                type="primary",
                use_container_width=True,
            ):
                db_acao = SessionLocal()
                try:
                    prod_atual = (
                        db_acao.query(Produto)
                        .filter_by(id=produto_selecionado.id)
                        .first()
                    )

                    if not prod_atual:
                        st.error("❌ Produto não encontrado.")
                    else:
                        nova_venda = Venda(
                            produto_id=prod_atual.id,
                            quantidade=quantidade,
                            valor_total=valor_total,
                            custo_total=(prod_atual.custo_unitario or 0.0)
                            * quantidade,
                            data_venda=datetime.now(),
                        )
                        db_acao.add(nova_venda)

                        relatorio_baixa = []
                        if prod_atual.ingredientes:
                            for item_receita in prod_atual.ingredientes:
                                insumo = item_receita.insumo
                                consumo_real = (
                                    item_receita.quantidade_gasta * quantidade
                                )
                                insumo.quantidade_atual = max(
                                    0.0, insumo.quantidade_atual - consumo_real
                                )
                                relatorio_baixa.append(
                                    f"• **{insumo.nome}**: -{consumo_real:.3f} {insumo.unidade_medida}"
                                )
                        else:
                            st.warning(
                                "⚠️ Produto sem Ficha Técnica vinculada."
                            )

                        db_acao.commit()
                        st.success(
                            f"🎉 Pedido de **{quantidade}x {prod_atual.nome}** registrado!"
                        )

                        if relatorio_baixa:
                            st.info(
                                "📉 **Baixa de Estoque Realizada:**\n\n"
                                + "\n".join(relatorio_baixa)
                            )
                except Exception as e:
                    db_acao.rollback()
                    st.error(f"❌ Erro ao processar venda: {e}")
                finally:
                    db_acao.close()

        with col_pdv2:
            st.subheader("📋 Últimas Vendas do Dia")
            db_vendas = get_db()
            vendas_dia = (
                db_vendas.query(Venda)
                .order_by(Venda.data_venda.desc())
                .limit(10)
                .all()
            )

            if vendas_dia:
                dados_vendas = [
                    {
                        "Horário": v.data_venda.strftime("%H:%M:%S")
                        if v.data_venda
                        else "--:--",
                        "Prato / Lanche": v.produto.nome
                        if v.produto
                        else "Item Excluído",
                        "Qtd": v.quantidade,
                        "Valor Total (R$)": f"R$ {v.valor_total:.2f}",
                        "Custo CMV (R$)": f"R$ {v.custo_total:.2f}",
                    }
                    for v in vendas_dia
                ]
                df_vendas = pd.DataFrame(dados_vendas)
                st.dataframe(df_vendas, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhuma transação registrada no caixa hoje.")


# ==============================================================================
# ABA 4: ESTOQUE DE INSUMOS & ALMOXARIFADO
# ==============================================================================
with aba4:
    st.header("📦 Gestão Inteligente de Insumos & Estoque")
    st.write("Acompanhe o saldo dos ingredientes em tempo real.")

    db = get_db()
    insumos = db.query(Insumo).all()

    if insumos:
        dados_estoque = [
            {
                "ID": i.id,
                "Insumo / Ingrediente": i.nome,
                "Saldo Atual": f"{i.quantidade_atual:.2f} {i.unidade_medida}",
                "Alerta Mínimo": f"{i.alerta_minimo:.2f} {i.unidade_medida}",
                "Custo Unitário (R$)": f"R$ {i.custo_unitario:.2f}",
                "Status": "🔴 Repor"
                if i.quantidade_atual <= i.alerta_minimo
                else "🟢 Normal",
            }
            for i in insumos
        ]
        st.dataframe(
            pd.DataFrame(dados_estoque), use_container_width=True, hide_index=True
        )
    else:
        st.info("Nenhum insumo cadastrado.")

    st.markdown("---")
    with st.expander("➕ Cadastrar ou Atualizar Saldo de Insumo"):
        with st.form("form_novo_insumo"):
            col_ins1, col_ins2, col_ins3 = st.columns(3)
            with col_ins1:
                nome_ins = st.text_input("Nome do Ingrediente")
                unidade = st.selectbox(
                    "Unidade", ["g", "kg", "un", "fatias", "ml", "L"]
                )
            with col_ins2:
                qtd_inicial = st.number_input(
                    "Quantidade Inicial", min_value=0.0, value=500.0, step=10.0
                )
                alerta_min = st.number_input(
                    "Alerta Mínimo", min_value=0.0, value=50.0, step=5.0
                )
            with col_ins3:
                custo_ins = st.number_input(
                    "Custo Unitário (R$)",
                    min_value=0.0,
                    value=0.05,
                    step=0.01,
                    format="%.4f",
                )

            if st.form_submit_button("💾 Salvar Insumo", type="primary"):
                if nome_ins:
                    db = get_db()
                    try:
                        ins_existente = (
                            db.query(Insumo).filter_by(nome=nome_ins).first()
                        )
                        if ins_existente:
                            ins_existente.quantidade_atual += qtd_inicial
                            ins_existente.custo_unitario = custo_ins
                        else:
                            novo_ins = Insumo(
                                nome=nome_ins,
                                quantidade_atual=qtd_inicial,
                                unidade_medida=unidade,
                                alerta_minimo=alerta_min,
                                custo_unitario=custo_ins,
                            )
                            db.add(novo_ins)
                        db.commit()
                        st.success("Insumo salvo com sucesso!")
                        st.rerun()
                    except Exception as e:
                        db.rollback()
                        st.error(f"Erro: {e}")


# ==============================================================================
# ABA 5: DASHBOARD FINANCEIRO & BI
# ==============================================================================
with aba5:
    st.header("📊 Dashboard Financeiro & BI Gastronômico")
    st.write(
        "Análise de desempenho, lucro bruto e margens operacionais em tempo real."
    )

    db = get_db()
    todas_vendas = db.query(Venda).all()

    if not todas_vendas:
        st.info("Realize vendas na Aba 3 para ver os gráficos e métricas.")
    else:
        fat_total = sum(v.valor_total for v in todas_vendas)
        custo_tot = sum(v.custo_total for v in todas_vendas)
        lucro_bruto = fat_total - custo_tot
        margem_geral = (
            (lucro_bruto / fat_total * 100) if fat_total > 0 else 0.0
        )

        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("💵 Faturamento", f"R$ {fat_total:,.2f}")
        kpi2.metric("📉 CMV Total", f"R$ {custo_tot:,.2f}")
        kpi3.metric("📈 Lucro Bruto", f"R$ {lucro_bruto:,.2f}")
        kpi4.metric("📊 Margem Geral", f"{margem_geral:.1f}%")

        st.markdown("---")

        col_graf1, col_graf2 = st.columns(2)
        with col_graf1:
            st.subheader("🍔 Vendas por Produto")
            df_graf = pd.DataFrame(
                [
                    {
                        "Produto": v.produto.nome
                        if v.produto
                        else "Deletado",
                        "Total Vendido (R$)": v.valor_total,
                    }
                    for v in todas_vendas
                ]
            )
            df_agrupado = (
                df_graf.groupby("Produto")["Total Vendido (R$)"]
                .sum()
                .reset_index()
            )
            st.bar_chart(
                df_agrupado,
                x="Produto",
                y="Total Vendido (R$)",
                use_container_width=True,
            )

        with col_graf2:
            st.subheader("📈 Faturamento vs. CMV")
            df_cmv = pd.DataFrame(
                {
                    "Categoria": ["Faturamento", "CMV", "Lucro Bruto"],
                    "Valor (R$)": [fat_total, custo_tot, lucro_bruto],
                }
            )
            st.bar_chart(
                df_cmv,
                x="Categoria",
                y="Valor (R$)",
                color=["#1E3A8A"],
                use_container_width=True,
            )