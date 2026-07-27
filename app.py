import os
import streamlit as st

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

# --- 2. BANCO DE DADOS E ORM ---
load_dotenv()
os.makedirs("imagens", exist_ok=True)

DATABASE_URL = "sqlite:///./banco_erp_local.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


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


class ContatoGerencial(Base):
    __tablename__ = "contatos_gerenciais"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String)
    whatsapp = Column(String, unique=True, index=True)
    cargo = Column(String)  # "Administrador" ou "Gerente"
    receber_alertas_estoque = Column(Integer, default=1)  # 1 = Sim, 0 = Não


Base.metadata.create_all(bind=engine)

with engine.connect() as conexao:
    try:
        res_vendas = conexao.execute(sqlalchemy.text("PRAGMA table_info(vendas);")).fetchall()
        cols_vendas = [col[1] for col in res_vendas]
        if "cliente_id" not in cols_vendas:
            conexao.execute(sqlalchemy.text("ALTER TABLE vendas ADD COLUMN cliente_id INTEGER;"))
            conexao.commit()
    except Exception:
        pass


def recalcular_cmv_geral(db_session):
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


def executar_forecasting_e_alertar(db_session):
    insumos = db_session.query(Insumo).all()
    vendas_recentes = db_session.query(Venda).filter(
        Venda.data_venda >= datetime.now() - timedelta(days=3)
    ).all()

    destinatarios = db_session.query(ContatoGerencial).filter(
        ContatoGerencial.receber_alertas_estoque == 1
    ).all()

    config_meta = db_session.query(ConfiguracaoMeta).first()
    
    if not destinatarios or not config_meta or not config_meta.whatsapp_token:
        return "⚠️ Configure os contatos gerenciais e o token do WhatsApp para ativar os alertas preditivos."

    resumo_estoque = "\n".join([f"- {i.nome}: Saldo Atual = {i.saldo_atual} {i.unidade_medida}, Mínimo = {i.estoque_minimo}" for i in insumos])
    
    prompt_forecast = f"""
    Você é o assistente de inteligência preditiva de um ERP gastronômico.
    Analise o estado atual do almoxarifado abaixo e determine se há algum ingrediente com risco iminente de esgotamento com base no ritmo operacional de hamburgueria:
    {resumo_estoque}
    
    Retorne APENAS um array JSON puro (sem markdown) com os insumos em risco crítico:
    [
      {{"insumo": "Nome do Insumo", "previsao_esgotamento": "Sábado às 20h", "mensagem_alerta": "Estoque crítico de pão brioche!"}}
    ]
    Se nenhum item estiver em risco, retorne [].
    """

    try:
        import google.generativeai as genai
        model_forecast = genai.GenerativeModel("models/gemini-flash-latest")
        resp = model_forecast.generate_content(prompt_forecast)
        texto_limpo = resp.text.strip().replace("```json", "").replace("```", "").strip()
        alertas_ia = json.loads(texto_limpo)

        if not alertas_ia:
            return "✅ Estoque seguro. Nenhum alerta preditivo gerado no momento."

        url_wa = f"https://graph.facebook.com/v17.0/{config_meta.whatsapp_phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {config_meta.whatsapp_token}",
            "Content-Type": "application/json"
        }

        total_enviados = 0
        for alerta in alertas_ia:
            texto_msg = f"🚨 *ALERTA PREDITIVO DE ESTOQUE (I.A.)* 🚨\n\nItem: *{alerta['insumo']}*\nPrevisão de Ruptura: *{alerta['previsao_esgotamento']}*\nStatus: {alerta['mensagem_alerta']}\n\n*Acesse o painel F&M AI FOOD para realizar a reposição imediata.*"

            for contato in destinatarios:
                payload = {
                    "messaging_product": "whatsapp",
                    "to": contato.whatsapp,
                    "type": "text",
                    "text": {"body": texto_msg}
                }
                response = requests.post(url_wa, headers=headers, json=payload)
                if response.status_code == 200:
                    total_enviados += 1

        return f"🚀 Forecasting concluído! {len(alertas_ia)} alertas preditivos gerados e disparados para {total_enviados} gestores via WhatsApp."

    except Exception as e:
        return f"❌ Erro ao executar forecasting preditivo: {e}"


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
                Cliente(nome="Ana Souza", whatsapp="11988882222", ultima_compra=datetime.now() - timedelta(days=18), total_gasto=120.0, status="Inativo"),
            ]
            db.add_all(clientes_padrao)
            db.commit()

        if db.query(Produto).count() == 0:
            prato_padrao = Produto(
                nome="Mica Royal Truffle Bacon",
                categoria="Burgers Gourmet",
                descricao_bruta="Hambúrguer 180g angus, queijo provolone derretido, bacon artesanal em tiras e maionese trufada no pão brioche.",
                descricao_ai="Experimente o magnífico Mica Royal Truffle Bacon! Preparado com maestria utilizando costela angus, queijo provolone derretido e bacon artesanal.",
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

# --- 3. BARRA LATERAL ---
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
            ingredientes_base = st.text_area("📝 Ingredientes Principais", placeholder="Ex: Dois burgers smash 100g de costela angus, queijo provolone derretido...")
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
            desc_gerada = f"Experimente o magnífico {nome_prato}! Preparado com maestria."
            caminho_imagem_salva = None

            if GENAI_DISPONIVEL:
                with st.spinner("🤖 A Inteligência Artificial está escrevendo a legenda gourmet..."):
                    try:
                        model_text = genai.GenerativeModel("models/gemini-flash-latest")
                        prompt_texto = f"Escreva uma descrição publicitária curta, altamente persuasiva, gourmet e apetitosa para um cardápio de restaurante para o prato: '{nome_prato}'. Ingredientes: {ingredientes_base}."
                        resp_texto = model_text.generate_content(prompt_texto)
                        if resp_texto and resp_texto.text:
                            desc_gerada = resp_texto.text.strip()
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
                st.success(f"🎉 Produto **{nome_prato}** cadastrado com sucesso!")
                st.info(desc_gerada)
            except Exception as e:
                db.rollback()
                st.error(f"❌ Erro ao salvar no banco: {e}")

# ==============================================================================
# ABA 2: CRM E WHATSAPP
# ==============================================================================
with aba2:
    st.header("📢 CRM, Campanhas & Automação de WhatsApp")
    st.write("Dispare promoções automáticas e resgate clientes inativos pelo WhatsApp.")
    db_crm = get_db()
    inativos = db_crm.query(Cliente).all()
    st.markdown(f"### 👥 Clientes na Base: **{len(inativos)}**")

# ==============================================================================
# ABA 3: FRENTE DE CAIXA (PDV COM UPSELL)
# ==============================================================================
with aba3:
    st.header("🛒 Frente de Caixa — PDV com Upsell Inteligente")
    db = get_db()
    lista_pratos = db.query(Produto).all()
    if not lista_pratos:
        st.warning("⚠️ Cadastre produtos na Aba 1 para habilitar o PDV.")
    else:
        prod_pdv = st.selectbox("Prato / Lanche", lista_pratos, format_func=lambda x: f"{x.nome} (R$ {x.preco_venda:.2f})")
        qtd = st.number_input("Quantidade", min_value=1, value=1, step=1)
        total = prod_pdv.preco_venda * qtd

        with st.container(border=True):
            st.markdown("💡 **Dica de Upsell da I.A. para o Caixa:**")
            sugestao_upsell = "Ofereça adicionar **Bacon Crocante** ou **Queijo Extra** por +R$ 5,00!"
            if GENAI_DISPONIVEL and prod_pdv:
                try:
                    model_up = genai.GenerativeModel("models/gemini-flash-latest")
                    prompt_up = f"Atuo como caixa em uma hamburgueria. O cliente está comprando '{prod_pdv.nome}'. Dê uma sugestão curta (1 frase) de adicional de alta margem."
                    resp_up = model_up.generate_content(prompt_up)
                    if resp_up and resp_up.text:
                        sugestao_upsell = resp_up.text.strip()
                except Exception:
                    pass
            st.info(f"🤖 *\"{sugestao_upsell}\"*")

        st.markdown(f"### 💰 Total a Pagar: R$ {total:.2f}")
        if st.button("✅ Confirmar Pedido & Baixar Estoque", type="primary"):
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
                st.success(f"🎉 Venda de **{qtd}x {prod_pdv.nome}** registrada com sucesso! Estoque baixado.")
            except Exception as e:
                db_v.rollback()
                st.error(f"❌ Erro ao registrar venda: {e}")
            finally:
                db_v.close()

# ==============================================================================
# ABA 4: ESTOQUE & FICHA TÉCNICA (COM OS 3 LEITORES DE I.A. VISION)
# ==============================================================================
with aba4:
    st.header("📦 Estoque de Insumos & Ficha Técnica Industrial")
    st.write("Gerencie o almoxarifado, monte fichas técnicas em massa e dê entrada com nota fiscal via I.A.")

    sub_aba1, sub_aba2, sub_aba3, sub_aba4 = st.tabs([
        "📊 Saldo Atual do Almoxarifado", 
        "➕ Cadastrar Insumos (I.A.)", 
        "🔗 Montar Receita (I.A.)",
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
            st.info("Nenhum insumo cadastrado.")

        st.markdown("---")
        st.subheader("🤖 Forecasting & Alerta Preditivo (I.A.)")
        st.write("O robô analisa o estoque e avisa os administradores via WhatsApp caso algum insumo corra risco de acabar.")

        if st.button("🔮 Executar Análise Preditiva de Ruptura Agora", type="primary"):
            db_fc = get_db()
            resultado_ia = executar_forecasting_e_alertar(db_fc)
            db_fc.close()
            st.info(resultado_ia)

        with st.expander("👥 Configurar Gestores para Alerta de WhatsApp"):
            with st.form("form_contato_gerencial"):
                c_nome = st.text_input("Nome do Gestor", placeholder="Ex: Carlos (Gerente Geral)")
                c_whats = st.text_input("WhatsApp (com DDI e DDD)", placeholder="Ex: 5516999998888")
                c_cargo = st.selectbox("Cargo", ["Administrador", "Gerente"])
                
                btn_salvar_contato = st.form_submit_button("💾 Salvar Contato Gerencial", type="primary")
                if btn_salvar_contato:
                    db_g = get_db()
                    try:
                        novo_cg = ContatoGerencial(nome=c_nome, whatsapp=c_whats, cargo=c_cargo)
                        db_g.add(novo_cg)
                        db_g.commit()
                        st.success(f"✅ Gestor **{c_nome}** cadastrado com sucesso!")
                    except Exception as e:
                        db_g.rollback()
                        st.error(f"❌ Erro ao salvar contato: {e}")
                    finally:
                        db_g.close()

        st.markdown("---")
        st.subheader("📋 Equipe Gestora Cadastrada")
        gestores_cadastrados = db_estoque.query(ContatoGerencial).all()
        if gestores_cadastrados:
            for g in gestores_cadastrados:
                col_g1, col_g2, col_g3, col_g4 = st.columns([3, 2, 2, 1])
                col_g1.write(f"**{g.nome}**")
                col_g2.write(f"📱 {g.whatsapp}")
                col_g3.write(f"💼 {g.cargo}")
                if col_g4.button("🗑️ Excluir", key=f"del_gestor_{g.id}"):
                    db_del = get_db()
                    try:
                        db_del.query(ContatoGerencial).filter(ContatoGerencial.id == g.id).delete()
                        db_del.commit()
                        st.success(f"Gestor {g.nome} removido com sucesso!")
                        st.rerun()
                    except Exception as e:
                        db_del.rollback()
                        st.error(f"Erro ao excluir: {e}")
                    finally:
                        db_del.close()
        else:
            st.info("Nenhum gestor cadastrado no momento.")

    # --- SUB-ABA 2: CADASTRO EM MASSA VIA FOTO DE NF ---
    with sub_aba2:
        st.subheader("➕ Cadastro Automático de Insumos via Foto (I.A. Vision)")
        st.write("Suba a foto da Nota Fiscal. O Gemini cadastrará os itens novos adivinhando a unidade e reabastecerá os existentes!")
        
        arquivo_nf_cad = st.file_uploader("📸 Envie a foto da Nota Fiscal para Cadastro", type=["jpg", "jpeg", "png"], key="uploader_nf_cad_ia")
        
        if arquivo_nf_cad:
            col_img_c, col_btn_c = st.columns([1, 2])
            with col_img_c:
                st.image(arquivo_nf_cad, caption="Nota para Cadastro", use_container_width=True)
            with col_btn_c:
                if st.button("🚀 Cadastrar e Atualizar Insumos com I.A.", type="primary", use_container_width=True):
                    with st.spinner("🤖 O Gemini está analisando os itens e criando os cadastros no banco..."):
                        try:
                            model_vision = genai.GenerativeModel("models/gemini-flash-latest")
                            img_pil = Image.open(arquivo_nf_cad)
                            
                            prompt_ocr_cad = 'Você é um auditor e almoxarife de gastronomia industrial. Analise esta nota fiscal ou cupom e extraia os itens comprados. Para cada item, infira a unidade de medida padrão gastronômica (ex: kg, un, l, ml, g, pct, fatias). Retorne APENAS um array JSON válido no formato: [{"nome": "Nome do Insumo", "unidade": "kg", "quantidade": 5.0, "valor_unitario": 12.50}]. Regras: Retorne EXCLUSIVAMENTE o JSON puro (sem markdown), sem textos extras. Quantidades e valores como números float.'
                            
                            resp_cad = model_vision.generate_content([prompt_ocr_cad, img_pil])
                            itens_lidos = json.loads(resp_cad.text.strip().replace("```json", "").replace("```", "").strip())
                            
                            db_cad = get_db()
                            novos_cadastrados = []
                            for item in itens_lidos:
                                nome_l = str(item.get("nome", "")).strip()
                                unidade_l = str(item.get("unidade", "un")).lower().strip()
                                qtd_l = float(item.get("quantidade", 0.0))
                                custo_l = float(item.get("valor_unitario", 0.0))
                                
                                if not nome_l or qtd_l <= 0:
                                    continue
                                    
                                ins_db = db_cad.query(Insumo).filter(Insumo.nome.ilike(f"%{nome_l}%")).first()
                                if ins_db:
                                    ins_db.saldo_atual += qtd_l
                                    if custo_l > 0:
                                        ins_db.custo_unitario = custo_l
                                else:
                                    novo_i = Insumo(nome=nome_l, unidade_medida=unidade_l, saldo_atual=qtd_l, estoque_minimo=max(1.0, qtd_l*0.15), custo_unitario=custo_l)
                                    db_cad.add(novo_i)
                                    novos_cadastrados.append(nome_l)
                                    
                            db_cad.commit()
                            recalcular_cmv_geral(db_cad)
                            db_cad.close()
                            st.success("🎉 Processo finalizado com sucesso! Almoxarifado e cardápio atualizados.")
                        except Exception as e:
                            st.error(f"❌ Erro ao processar cadastro: {e}")

    # --- SUB-ABA 3: MONTAGEM DE RECEITAS VIA FOTO DE RECEITA ---
    with sub_aba3:
        st.subheader("🔗 Montagem Automática de Ficha Técnica via Foto (I.A. Vision)")
        produtos_ft = db_estoque.query(Produto).all()
        if not produtos_ft:
            st.warning("⚠️ Cadastre produtos na Aba 1 primeiro.")
        else:
            prato_escolhido = st.selectbox("🎯 Selecione o Prato para Montar:", produtos_ft, format_func=lambda p: f"{p.nome} (R$ {p.preco_venda:.2f})")
            arquivo_receita = st.file_uploader("📸 Envie a foto da Receita ou Ficha Técnica", type=["jpg", "jpeg", "png"], key="uploader_receita_ia")
            
            if arquivo_receita:
                if st.button("🚀 Ler Receita e Montar Ficha Técnica com I.A.", type="primary", use_container_width=True):
                    with st.spinner(f"🤖 Lendo receita e vinculando insumos para {prato_escolhido.nome}..."):
                        try:
                            model_vision = genai.GenerativeModel("models/gemini-flash-latest")
                            img_pil = Image.open(arquivo_receita)
                            
                            prompt_ocr_rec = 'Você é um chef executivo e engenheiro de cardápio. Analise esta foto de receita, ficha técnica ou manual de cozinha. Extraia os ingredientes e as quantidades utilizadas para preparar uma porção do prato. Retorne APENAS um array JSON válido no formato: [{"nome": "Nome do Ingrediente", "quantidade": 0.150}]. Regras: Retorne EXCLUSIVAMENTE o JSON puro (sem markdown), sem textos extras. As quantidades devem ser números float compatíveis com a unidade padrão.'
                            
                            resp_rec = model_vision.generate_content([prompt_ocr_rec, img_pil])
                            ingredientes_lidos = json.loads(resp_rec.text.strip().replace("```json", "").replace("```", "").strip())
                            
                            db_rec = get_db()
                            db_rec.query(FichaTecnica).filter(FichaTecnica.produto_id == prato_escolhido.id).delete()
                            
                            for item in ingredientes_lidos:
                                nome_ing = str(item.get("nome", "")).strip()
                                qtd_ing = float(item.get("quantidade", 0.0))
                                if not nome_ing or qtd_ing <= 0:
                                    continue
                                insumo_db = db_rec.query(Insumo).filter(Insumo.nome.ilike(f"%{nome_ing}%")).first()
                                if insumo_db:
                                    db_rec.add(FichaTecnica(produto_id=prato_escolhido.id, insumo_id=insumo_db.id, quantidade_utilizada=qtd_ing))
                                    
                            db_rec.commit()
                            recalcular_cmv_geral(db_rec)
                            db_rec.close()
                            st.success(f"🎉 Ficha Técnica de **{prato_escolhido.nome}** montada com sucesso e CMV reajustado!")
                        except Exception as e:
                            st.error(f"❌ Erro ao ler receita: {e}")

    # --- SUB-ABA 4: ENTRADA DE NOTA FISCAL / REPOSIÇÃO ---
    with sub_aba4:
        st.subheader("🧾 Entrada Automática via Nota Fiscal (Reposição)")
        arquivo_nf = st.file_uploader("📸 Envie a Nota Fiscal de Compra", type=["jpg", "jpeg", "png"], key="uploader_nf_reposicao")
        if arquivo_nf:
            if st.button("🚀 Ler Cupom e Atualizar Estoque", type="primary", use_container_width=True):
                with st.spinner("🤖 Lendo nota fiscal e atualizando custos..."):
                    try:
                        model_vision = genai.GenerativeModel("models/gemini-flash-latest")
                        img_pil = Image.open(arquivo_nf)
                        prompt_ocr = 'Você é um auditor de estoque e custos para gastronomia industrial. Analise a imagem desta nota fiscal. Extraia os itens e retorne APENAS um array JSON no formato: [{"nome": "Insumo", "quantidade": 10.0, "valor_unitario": 5.50}]. Exclusivamente JSON puro, sem markdown.'
                        
                        response_ocr = model_vision.generate_content([prompt_ocr, img_pil])
                        itens_extraidos = json.loads(response_ocr.text.strip().replace("```json", "").replace("```", "").strip())
                        
                        db_in = get_db()
                        for item in itens_extraidos:
                            nome_lido = str(item.get("nome", "")).strip()
                            qtd_lida = float(item.get("quantidade", 0.0))
                            custo_lido = float(item.get("valor_unitario", 0.0))
                            if not nome_lido or qtd_lida <= 0:
                                continue
                            insumo_db = db_in.query(Insumo).filter(Insumo.nome.ilike(f"%{nome_lido}%")).first()
                            if insumo_db:
                                insumo_db.saldo_atual += qtd_lida
                                if custo_lido > 0:
                                    insumo_db.custo_unitario = custo_lido
                                    
                        db_in.commit()
                        recalcular_cmv_geral(db_in)
                        db_in.close()
                        st.success("🎉 Entrada de estoque e CMV atualizados com sucesso!")
                    except Exception as e:
                        st.error(f"❌ Erro ao processar nota: {e}")

# ==============================================================================
# ABA 5: DASHBOARD FINANCEIRO
# ==============================================================================
with aba5:
    st.header("📊 Dashboard Financeiro & Indicadores")
    db_dash = get_db()
    todas_vendas = db_dash.query(Venda).all()
    faturamento_total = sum(v.valor_total for v in todas_vendas)
    custo_total_vendas = sum(v.custo_total for v in todas_vendas)
    lucro_bruto = faturamento_total - custo_total_vendas
    margem_geral = (lucro_bruto / faturamento_total * 100) if faturamento_total > 0 else 0.0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("💰 Faturamento Total", f"R$ {faturamento_total:.2f}")
    m2.metric("📉 CMV Total", f"R$ {custo_total_vendas:.2f}")
    m3.metric("💵 Lucro Bruto", f"R$ {lucro_bruto:.2f}")
    m4.metric("📈 Margem Média", f"{margem_geral:.1f}%")

    st.markdown("---")
    st.subheader("📈 Histórico de Vendas")
    if todas_vendas:
        st.dataframe(pd.DataFrame([
            {"Data": v.data_venda.strftime("%d/%m/%Y %H:%M"), "Produto": v.produto.nome if v.produto else "Item", "Qtd": v.quantidade, "Total": f"R$ {v.valor_total:.2f}"}
            for v in todas_vendas
        ]), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma venda registrada.")