import os
import streamlit as st

# Patch: ensure compatibility with custom keyword args used across the app
# Some calls use st.container(border=True) which is not a Streamlit argument.
# We wrap the original container to accept and ignore unknown kwargs like 'border'.
try:
    if not hasattr(st, "_orig_container"):
        st._orig_container = st.container
        def _container_compat(*args, **kwargs):
            # ignore non-standard visual kwargs used in the app
            kwargs.pop("border", None)
            kwargs.pop("bordered", None)
            return st._orig_container(*args, **kwargs)
        st.container = _container_compat
except Exception:
    pass

# --- 0. CONFIGURAÇÃO DE SEGURANÇA E AMBIENTE ---
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

# --- 1. CONFIGURAÇÃO DA PÁGINA E ESTILIZAÇÃO ---
st.set_page_config(
    page_title="F&M AI FOOD — ERP Gastronômico & PDV Inteligente",
    page_icon="🍔",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. BANCO DE DADOS E CONFIGURAÇÃO ORM ---
load_dotenv()
os.makedirs("imagens", exist_ok=True)

DATABASE_URL = "sqlite:///./banco_erp_local.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# --- 3. MODELOS DAS TABELAS DO BANCO DE DADOS ---
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
    saldo_cashback = Column(Float, default=0.0)
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
    forma_pagamento = Column(String, default="Pix")
    status_pagamento = Column(String, default="Aprovado")
    data_venda = Column(DateTime, default=datetime.now)

    produto = relationship("Produto")
    cliente = relationship("Cliente")


class GatewayConfig(Base):
    __tablename__ = 'gateway_config'
    id = Column(Integer, primary_key=True)
    gateway_provider = Column(String(50), default="Mercado Pago")
    gateway_api_key = Column(String(255), nullable=True)
    gateway_pix_key = Column(String(100), nullable=True)
    ambiente = Column(String(20), default="Sandbox")


class ConfiguracaoMeta(Base):
    __tablename__ = "configuracoes_meta"
    id = Column(Integer, primary_key=True, index=True)
    meta_access_token = Column(String, nullable=True)
    facebook_page_id = Column(String, nullable=True)
    instagram_account_id = Column(String, nullable=True)
    whatsapp_token = Column(String, nullable=True)
    whatsapp_phone_id = Column(String, nullable=True)
    gateway_provider = Column(String, default="Mercado Pago")
    gateway_pix_key = Column(String, nullable=True)
    gateway_api_key = Column(String, nullable=True)


class ContatoGerencial(Base):
    __tablename__ = "contatos_gerenciais"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String)
    whatsapp = Column(String, unique=True, index=True)
    cargo = Column(String)
    receber_alertas_estoque = Column(Integer, default=1)


# Criar todas as tabelas no banco de dados com proteção contra tabelas existentes
try:
    Base.metadata.create_all(bind=engine, checkfirst=True)
except Exception as e:
    print(f"Aviso de schema/tabelas: {e}")

# --- 4. MIGRAÇÕES AUTOMÁTICAS DE SCHEMA ---
with engine.connect() as conexao:
    try:
        res_vendas = conexao.execute(sqlalchemy.text("PRAGMA table_info(vendas);")).fetchall()
        cols_vendas = [col[1] for col in res_vendas]
        if "cliente_id" not in cols_vendas:
            conexao.execute(sqlalchemy.text("ALTER TABLE vendas ADD COLUMN cliente_id INTEGER;"))
        if "forma_pagamento" not in cols_vendas:
            conexao.execute(sqlalchemy.text("ALTER TABLE vendas ADD COLUMN forma_pagamento VARCHAR DEFAULT 'Pix';"))
        if "status_pagamento" not in cols_vendas:
            conexao.execute(sqlalchemy.text("ALTER TABLE vendas ADD COLUMN status_pagamento VARCHAR DEFAULT 'Aprovado';"))
        
        res_cli = conexao.execute(sqlalchemy.text("PRAGMA table_info(clientes);")).fetchall()
        cols_cli = [col[1] for col in res_cli]
        if "saldo_cashback" not in cols_cli:
            conexao.execute(sqlalchemy.text("ALTER TABLE clientes ADD COLUMN saldo_cashback FLOAT DEFAULT 0.0;"))
            
        res_conf = conexao.execute(sqlalchemy.text("PRAGMA table_info(configuracoes_meta);")).fetchall()
        cols_conf = [col[1] for col in res_conf]
        if "gateway_provider" not in cols_conf:
            conexao.execute(sqlalchemy.text("ALTER TABLE configuracoes_meta ADD COLUMN gateway_provider VARCHAR DEFAULT 'Mercado Pago';"))
        if "gateway_pix_key" not in cols_conf:
            conexao.execute(sqlalchemy.text("ALTER TABLE configuracoes_meta ADD COLUMN gateway_pix_key VARCHAR;"))
        if "gateway_api_key" not in cols_conf:
            conexao.execute(sqlalchemy.text("ALTER TABLE configuracoes_meta ADD COLUMN gateway_api_key VARCHAR;"))
            
        conexao.commit()
    except Exception as e:
        print(f"Aviso na verificação de migrações SQLite: {e}")


# --- 5. FUNÇÕES UTILITÁRIAS E DE NEGÓCIO ---
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
    except Exception as e:
        db.rollback()
    finally:
        db.close()


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

import streamlit as st


# ==============================================================================
# SUB-ABA / MÓDULO: CADASTRO DE PRODUTO COM FICHA TÉCNICA E PRECIFICAÇÃO IA
# ==============================================================================
import json
import streamlit as st


def render_cadastro_ficha_tecnica(db_session, Insumo, Produto, FichaTecnica, client=None, GENAI_DISPONIVEL=False):
    st.subheader("👨‍🍳 Engenharia de Cardápio & Ficha Técnica Granular")
    
    modo = st.radio(
        "Escolha como deseja cadastrar:",
        ["✍️ Cadastro Manual", "🤖 Importação Automática via IA (Foto/PDF/Texto)"],
        horizontal=True
    )
    
    st.markdown("---")
    
    if modo == "✍️ Cadastro Manual":
        col_nome, col_cat = st.columns([2, 1])
        with col_nome:
            nome_produto = st.text_input("Nome do Produto / Prato", placeholder="Ex: Mica Royal Truffle Bacon")
        with col_cat:
            categoria = st.selectbox("Categoria", ["Hambúrgueres", "Porções", "Bebidas", "Sobremesas"])
            
        st.write("### 🥗 Composição da Ficha Técnica (Insumos do Almoxarifado)")
        insumos_disponiveis = db_session.query(Insumo).all()
        
        if not insumos_disponiveis:
            st.warning("⚠️ Nenhum insumo encontrado no Almoxarifado. Cadastre os insumos primeiro!")
            return
            
        if "itens_ficha_tecnica" not in st.session_state:
            st.session_state.itens_ficha_tecnica = []
            
        c1, c2, c3 = st.columns([3, 2, 1])
        with c1:
            insumo_selecionado = st.selectbox(
                "Selecione o Insumo",
                options=insumos_disponiveis,
                format_func=lambda x: f"{x.nome} (R$ {x.custo_unitario:.2f} / {x.unidade_medida})",
                key="sel_insumo"
            )
        with c2:
            label_qtd = "Quantidade em GRAMAS (g)" if insumo_selecionado.unidade_medida == "kg" else f"Quantidade ({insumo_selecionado.unidade_medida})"
            qtd_usada = st.number_input(label_qtd, min_value=0.1, value=100.0, step=10.0, key="num_qtd")
            
        with c3:
            st.write(" ")
            st.write(" ")
            if st.button("➕ Adicionar", use_container_width=True):
                custo_item = (qtd_usada / 1000.0) * insumo_selecionado.custo_unitario if insumo_selecionado.unidade_medida == "kg" else qtd_usada * insumo_selecionado.custo_unitario
                st.session_state.itens_ficha_tecnica.append({
                    "insumo_id": insumo_selecionado.id,
                    "nome": insumo_selecionado.nome,
                    "quantidade": qtd_usada,
                    "unidade": "g" if insumo_selecionado.unidade_medida == "kg" else insumo_selecionado.unidade_medida,
                    "custo_calculado": custo_item
                })
                st.rerun()
                
        cmv_total_calculado = 0.0
        if st.session_state.itens_ficha_tecnica:
            st.write("#### 📜 Receita Montada:")
            tabela_dados = []
            for item in st.session_state.itens_ficha_tecnica:
                cmv_total_calculado += item["custo_calculado"]
                tabela_dados.append({
                    "Item": item["nome"],
                    "Qtd na Receita": f"{item['quantidade']} {item['unidade']}",
                    "Custo Residual (R$)": f"R$ {item['custo_calculado']:.2f}"
                })
            st.table(tabela_dados)
            
            if st.button("🗑️ Limpar Receita"):
                st.session_state.itens_ficha_tecnica = []
                st.rerun()
                
        st.markdown("---")
        st.write("### 💰 Precificação Inteligente & Margem de Lucro Pretendida")
        col_cmv, col_margem, col_preco, col_lucro = st.columns(4)
        
        with col_cmv:
            st.metric("Custo de Produção (CMV)", f"R$ {cmv_total_calculado:.2f}")
            
        with col_margem:
            margem_pretendida = st.number_input("Margem Desejada (%)", min_value=5.0, max_value=300.0, value=60.0, step=5.0)
            
        preco_sugerido = (cmv_total_calculado / (1 - (margem_pretendida / 100.0))) if margem_pretendida < 100 else (cmv_total_calculado * (1 + (margem_pretendida / 100.0)))
        
        with col_preco:
            preco_venda_final = st.number_input("Preço de Venda Final (R$)", min_value=0.0, value=float(round(preco_sugerido, 2)), step=0.50)
            
        with col_lucro:
            margem_real = ((preco_venda_final - cmv_total_calculado) / preco_venda_final * 100) if preco_venda_final > 0 else 0
            st.metric("Lucro Bruto / Lanche", f"R$ {(preco_venda_final - cmv_total_calculado):.2f}", delta=f"{margem_real:.1f}% Margem Real")
            
        if st.button("💾 Salvar Produto & Ficha Técnica", type="primary"):
            if not nome_produto:
                st.error("❌ Digite o nome do produto.")
            elif not st.session_state.itens_ficha_tecnica:
                st.error("❌ Adicione pelo menos 1 insumo à ficha técnica.")
            else:
                novo_prod = Produto(
                    nome=nome_produto,
                    categoria=categoria,
                    preco=preco_venda_final,
                    custo_cmv=cmv_total_calculado,
                    margem_lucro=margem_real
                )
                db_session.add(novo_prod)
                db_session.commit()
                
                for item in st.session_state.itens_ficha_tecnica:
                    nova_ft = FichaTecnica(
                        produto_id=novo_prod.id,
                        insumo_id=item["insumo_id"],
                        quantidade_necessaria=item["quantidade"]
                    )
                    db_session.add(nova_ft)
                db_session.commit()
                
                st.success(f"✅ **{nome_produto}** cadastrado com sucesso!")
                st.session_state.itens_ficha_tecnica = []
                st.rerun()

    else:
        st.write("### 📄 Upload de Cardápio Real (Foto, PDF ou Colar Texto) via Gemini")
        st.caption("Carregue o arquivo com seu cardápio oficial que a IA extrairá todos os produtos e cadastrará no banco.")
        
        opcao_fonte = st.radio("Origem do arquivo:", ["📁 Upload de Arquivo (Imagem/PDF)", "📝 Colar Texto do Cardápio"], horizontal=True)
        
        texto_cardapio = ""
        arquivo_upload = None
        
        if opcao_fonte == "📁 Upload de Arquivo (Imagem/PDF)":
            arquivo_upload = st.file_uploader("Arraste a foto do cardápio ou PDF aqui", type=["png", "jpg", "jpeg", "pdf"])
        else:
            texto_cardapio = st.text_area("Cole aqui o texto do seu cardápio com nomes e preços:", height=150)
            
        if st.button("🚀 Processar Cardápio com IA", type="primary"):
            if not GENAI_DISPONIVEL or not client:
                st.error("❌ Integração com Google GenAI/Gemini não configurada no servidor.")
                return
                
            if not arquivo_upload and not texto_cardapio.strip():
                st.error("❌ Por favor, envie um arquivo ou cole o texto do cardápio.")
                return
                
            with st.spinner("🤖 O Gemini está analisando o cardápio real..."):
                try:
                    prompt = """
                    Você é um especialista em ERP gastronômico. Analise o cardápio fornecido e extraia todos os produtos/itens cadastráveis.
                    Retorne EXATAMENTE um JSON no seguinte formato (sem formatação markdown ```json, apenas a string json pura):
                    [
                        {
                            "nome": "Nome do Lanche",
                            "categoria": "Hambúrgueres",
                            "preco": 39.90,
                            "ingredientes": "Descrição ou ingredientes brutos"
                        }
                    ]
                    """
                    
                    if arquivo_upload:
                        bytes_data = arquivo_upload.getvalue()
                        mime = arquivo_upload.type
                        contents = [{'mime_type': mime, 'data': bytes_data}, prompt]
                        response = client.models.generate_content(model="gemini-2.5-flash", contents=contents)
                    else:
                        response = client.models.generate_content(
                            model="gemini-2.5-flash",
                            contents=f"{prompt}\n\n{texto_cardapio}"
                        )
                    
                    texto_limpo = response.text.strip().replace("```json", "").replace("```", "")
                    produtos_extraidos = json.loads(texto_limpo)
                    
                    qtd_cadastrados = 0
                    for prod in produtos_extraidos:
                        cmv_est = round(float(prod.get("preco", 0)) * 0.32, 2)
                        novo_prod = Produto(
                            nome=prod.get("nome"),
                            categoria=prod.get("categoria", "Geral"),
                            preco=float(prod.get("preco", 0)),
                            custo_cmv=cmv_est,
                            margem_lucro=68.0,
                            descricao_bruta=prod.get("ingredientes", "")
                        )
                        db_session.add(novo_prod)
                        qtd_cadastrados += 1
                        
                    db_session.commit()
                    st.success(f"🎉 Sucesso! **{qtd_cadastrados} produtos** foram extraídos pelo Gemini e salvos diretamente no cardápio!")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Erro ao processar cardápio com IA: {e}")


def executar_forecasting_e_alertar(db_session):
    insumos = db_session.query(Insumo).all()
    destinatarios = db_session.query(ContatoGerencial).filter(
        ContatoGerencial.receber_alertas_estoque == 1
    ).all()
    config_meta = db_session.query(ConfiguracaoMeta).first()
    
    if not destinatarios:
        return "⚠️ Nenhum gerente ou administrador está configurado para receber alertas na Aba 4."
    if not config_meta or not config_meta.whatsapp_token:
        return "⚠️ Configure o token de acesso da Meta Cloud API para ativar os disparos reais de WhatsApp."

    resumo_estoque = "\n".join([f"- {i.nome}: Saldo Atual = {i.saldo_atual} {i.unidade_medida}, Mínimo = {i.estoque_minimo}" for i in insumos])
    
    prompt_forecast = f"""
    Você é o assistente de inteligência preditiva de um ERP gastronômico de alta performance.
    Analise o estado atual do almoxarifado abaixo e determine se há algum ingrediente com risco iminente de esgotamento com base no ritmo operacional de uma hamburgueria gourmet:
    {resumo_estoque}
    
    Retorne APENAS um array JSON puro (sem markdown) com os insumos em risco crítico ou de alerta:
    [
      {{"insumo": "Nome do Insumo", "previsao_esgotamento": "Sábado às 20h", "mensagem_alerta": "Estoque crítico para o fim de semana!"}}
    ]
    Se nenhum item estiver em risco, retorne um array vazio [].
    """

    try:
        from google import genai
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt_forecast)
        texto_limpo = resp.text.strip().replace("```json", "").replace("```", "").strip()
        alertas_ia = json.loads(texto_limpo)

        if not alertas_ia:
            return "✅ Estoque operacional seguro. Nenhum alerta preditivo gerado no momento pela Inteligência Artificial."

        url_wa = f"https://graph.facebook.com/v17.0/{config_meta.whatsapp_phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {config_meta.whatsapp_token}",
            "Content-Type": "application/json"
        }

        total_enviados = 0
        for alerta in alertas_ia:
            texto_msg = f"🚨 *ALERTA PREDITIVO DE ESTOQUE (F&M AI FOOD)* 🚨\n\nItem: *{alerta['insumo']}*\nPrevisão de Ruptura: *{alerta['previsao_esgotamento']}*\nStatus: {alerta['mensagem_alerta']}\n\n*Acesse imediatamente o painel corporativo para realizar a compra de reposição.*"

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

        return f"🚀 Análise concluída com sucesso! {len(alertas_ia)} alertas preditivos foram gerados e disparados para {total_enviados} gestores via WhatsApp."
    except Exception as e:
        return f"❌ Erro técnico ao processar forecasting inteligente: {e}"


def popular_dados_iniciais():
    db = SessionLocal()
    try:
        if db.query(ConfiguracaoMeta).count() == 0:
            db.add(ConfiguracaoMeta(gateway_provider="Mercado Pago"))
            db.commit()

        if db.query(Insumo).count() == 0:
            insumos_padrao = [
                Insumo(nome="Hambúrguer 180g Angus", unidade_medida="un", saldo_atual=500.0, estoque_minimo=50.0, custo_unitario=6.50),
                Insumo(nome="Queijo Provolone / Cheddar", unidade_medida="fatias", saldo_atual=400.0, estoque_minimo=60.0, custo_unitario=1.20),
                Insumo(nome="Pão Brioche Artesanal", unidade_medida="un", saldo_atual=120.0, estoque_minimo=50.0, custo_unitario=2.00),
                Insumo(nome="Bacon Artesanal em Tiras", unidade_medida="kg", saldo_atual=5.0, estoque_minimo=1.0, custo_unitario=35.00),
                Insumo(nome="Batata Frita Cruda", unidade_medida="kg", saldo_atual=30.0, estoque_minimo=10.0, custo_unitario=8.90),
                Insumo(nome="Refrigerante Lata 350ml", unidade_medida="un", saldo_atual=90.0, estoque_minimo=24.0, custo_unitario=2.80),
            ]
            db.add_all(insumos_padrao)
            db.commit()

        if db.query(Cliente).count() == 0:
            clientes_padrao = [
                Cliente(nome="Carlos Eduardo (VIP)", whatsapp="11999991111", ultima_compra=datetime.now() - timedelta(days=2), total_gasto=450.0, saldo_cashback=15.0, status="Ativo"),
                Cliente(nome="Ana Souza Silva", whatsapp="11988882222", ultima_compra=datetime.now() - timedelta(days=18), total_gasto=120.0, saldo_cashback=0.0, status="Inativo"),
                Cliente(nome="Marcos Oliveira", whatsapp="11977773333", ultima_compra=datetime.now() - timedelta(days=25), total_gasto=290.0, saldo_cashback=5.50, status="Inativo"),
            ]
            db.add_all(clientes_padrao)
            db.commit()

        if db.query(Produto).count() == 0:
            prato_padrao = Produto(
                nome="Mica Royal Truffle Bacon",
                categoria="Burgers Gourmet",
                descricao_bruta="Hambúrguer 180g angus, queijo provolone derretido, bacon artesanal em tiras e maionese trufada no pão brioche artesanal.",
                descricao_ai="Experimente o magnífico Mica Royal Truffle Bacon! Preparado com maestria utilizando costela angus selecionada, queijo provolone derretido e bacon artesanal crocante no pão brioche selado na manteiga.",
                preco_venda=39.90,
                custo_total_cmv=12.65,
                margem_exibicao="68.3%",
                imagem_path=None,
            )
            db.add(prato_padrao)
            db.commit()

            pao = db.query(Insumo).filter(Insumo.nome == "Pão Brioche Artesanal").first()
            carne = db.query(Insumo).filter(Insumo.nome == "Hambúrguer 180g Angus").first()
            queijo = db.query(Insumo).filter(Insumo.nome == "Queijo Provolone / Cheddar").first()
            bacon = db.query(Insumo).filter(Insumo.nome == "Bacon Artesanal em Tiras").first()

            if pao and carne and queijo and bacon:
                fichas_automatizadas = [
                    FichaTecnica(produto_id=prato_padrao.id, insumo_id=pao.id, quantidade_utilizada=1.0),
                    FichaTecnica(produto_id=prato_padrao.id, insumo_id=carne.id, quantidade_utilizada=1.0),
                    FichaTecnica(produto_id=prato_padrao.id, insumo_id=queijo.id, quantidade_utilizada=2.0),
                    FichaTecnica(produto_id=prato_padrao.id, insumo_id=bacon.id, quantidade_utilizada=0.05),
                ]
                db.add_all(fichas_automatizadas)
                db.commit()
    except Exception as e:
        db.rollback()
    finally:
        db.close()


# Inicialização das configurações
criar_admin()
popular_dados_iniciais()

# Verificação da Inteligência Artificial Gemini
GENAI_DISPONIVEL = True
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")

from google import genai

client = genai.Client(api_key=GEMINI_API_KEY)


# --- 6. BARRA LATERAL (SIDEBAR CORPORATIVA) ---
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
        st.markdown("🟢 **Google GenAI Ativo (Gemini 2.0 Flash)**")
    else:
        st.markdown("⚠️ **Modo Offline / Sem Chave API**")
        st.caption("Insira GEMINI_API_KEY no .env ou st.secrets para ativar recursos inteligentes.")
    
    st.markdown("---")
    st.markdown("### ⚙️ Atalhos de Suporte")
    st.write("📞 Atendimento 24/7 via WhatsApp")
    st.write("📊 Licença Corporativa Ativa")


# --- 7. CABEÇALHO DO PAINEL PRINCIPAL ---
st.title("🍔 F&M AI FOOD — Painel de Gestão, PDV & Gateway")
st.markdown("---")

# --- 8. ESTRUTURA DAS 6 ABAS PRINCIPAIS ---
aba1, aba2, aba3, aba4, aba5, aba6 = st.tabs(
    [
        "🤖 Engenharia de Cardápio",
        "📢 CRM, Resgate & Cashback",
        "🛒 Frente de Caixa (PDV & Pix)",
        "📦 Estoque & Ficha Técnica",
        "📊 Dashboard Financeiro",
        "💬 Bot Cliente (Mica I.A.)",
    ]
)


# ==============================================================================
# ABA 1: ENGENHARIA DE CARDÁPIO COM INTELIGÊNCIA ARTIFICIAL
# ==============================================================================
with aba1:
    render_cadastro_ficha_tecnica(
        db_session=get_db(),
        Insumo=Insumo,
        Produto=Produto,
        FichaTecnica=FichaTecnica
    )


# ==============================================================================
# ABA 2: CRM, RECUPERAÇÃO DE CLIENTES ("OI, SUMIDO") & CASHBACK
# ==============================================================================
with aba2:
    st.header("📢 CRM, Campanhas de Resgate ('Oi, Sumido') & Fidelidade Cashback")
    st.write("Engaje clientes inativos com cupons persuasivos gerados pela I.A. e administre saldos de cashback da sua base de consumidores.")

    sub_crm1, sub_crm2 = st.tabs(["🔄 Recuperação de Clientes Inativos (Upsell)", "💳 Gestão de Fidelidade & Cashback"])

    db_crm_base = get_db()

    # --- SUB-ABA 1: RESGATE DE CLIENTES INATIVOS ---
    with sub_crm1:
        st.subheader("🤖 Automação de Resgate com Inteligência Artificial")
        st.write("A plataforma identifica clientes sem compras há mais de 15 dias e sugere abordagens personalizadas com cupons de desconto para disparar no WhatsApp.")
        
        data_corte_inativos = datetime.now() - timedelta(days=15)
        clientes_inativos = db_crm_base.query(Cliente).filter(
            (Cliente.ultima_compra <= data_corte_inativos) | (Cliente.status == "Inativo")
        ).all()

        st.markdown(f"### 👥 Clientes em risco de churn identificados: **{len(clientes_inativos)}**")

        if clientes_inativos:
            for cli in clientes_inativos:
                with st.container(border=True):
                    c_col1, c_col2, c_col3 = st.columns([2, 2, 3])
                    with c_col1:
                        st.markdown(f"**👤 {cli.nome}**")
                        st.write(f"📱 WhatsApp: `{cli.whatsapp}`")
                        st.write(f"📌 Status: **{cli.status}**")
                    
                    with c_col2:
                        st.write(f"🕒 Última compra: **{cli.ultima_compra.strftime('%d/%m/%Y')}**")
                        st.write(f"💰 Total acumulado: **R$ {cli.total_gasto:.2f}**")
                        st.write(f"💳 Cashback disponível: **R$ {cli.saldo_cashback:.2f}**")
                    
                    msg_resgate_padrao = f"Olá {cli.nome}! Sentimos muito a sua falta aqui no Mica Burguer. Preparamos um cupom exclusivo de 15% de desconto para você pedir seu hambúrguer favorito hoje!"
                    
                    if GENAI_DISPONIVEL:
                        try:
                            prompt_resg = f"Escreva uma mensagem curta, carinhosa e muito persuasiva de WhatsApp para resgatar o cliente '{cli.nome}', que não faz pedidos em nossa hamburgueria gourmet há semanas. Ofereça um cupom especial de 15% de desconto (CUPOM: VOLTAMICA15). Sem clichês em excesso."
                            resp_resg = client.models.generate_content(model="gemini-2.5-flash", contents=prompt_resg)
                            if resp_resg and resp_resg.text:
                                msg_resgate_padrao = resp_resg.text.strip()
                        except Exception:
                            pass

                    with c_col3:
                        st.markdown("🤖 **Sugestão de Abordagem I.A.:**")
                        st.info(f"\"{msg_resgate_padrao}\"")
                        if st.button(f"🚀 Disparar Campanha WhatsApp para {cli.nome}", key=f"btn_zap_resgate_{cli.id}", type="primary"):
                            st.success(f"✅ Campanha de resgate enviada com sucesso para o número {cli.whatsapp}!")
        else:
            st.success("🎉 Excelente notícia! Nenhum cliente inativo há mais de 15 dias foi identificado no momento. Sua base está altamente engajada!")

    # --- SUB-ABA 2: GESTÃO DE CASHBACK ---
    with sub_crm2:
        st.subheader("💳 Relatório Geral de Saldos de Cashback")
        st.write("Acompanhe o saldo que cada cliente acumulou para utilizar como desconto em pedidos futuros na loja ou no delivery.")
        
        todos_clientes = db_crm_base.query(Cliente).all()
        if todos_clientes:
            dados_cb = []
            for cl in todos_clientes:
                dados_cb.append({
                    "ID": cl.id,
                    "Nome do Cliente": cl.nome,
                    "WhatsApp": cl.whatsapp,
                    "Total Gasto na Loja": f"R$ {cl.total_gasto:.2f}",
                    "Saldo Cashback": f"R$ {cl.saldo_cashback:.2f}",
                    "Status": cl.status
                })
            st.dataframe(pd.DataFrame(dados_cb), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum cliente cadastrado no banco de dados até o momento.")

        st.markdown("---")
        with st.form("form_ajustar_cashback"):
            st.markdown("### ➕ Creditar Saldo de Cashback Manualmente")
            st.write("Utilize esta função para premiar clientes vips ou conceder bônus promocionais.")
            col_cb1, col_cb2 = st.columns(2)
            with col_cb1:
                cli_escolhido = st.selectbox("Selecione o Cliente para o Crédito", todos_clientes, format_func=lambda x: f"{x.nome} (Saldo Atual: R$ {x.saldo_cashback:.2f})")
            with col_cb2:
                valor_add_cb = st.number_input("Valor do Crédito a Adicionar (R$)", min_value=0.0, value=10.0, step=5.0, format="%.2f")
            
            btn_add_cb = st.form_submit_button("💰 Confirmar Crédito de Cashback", type="primary")
            if btn_add_cb and cli_escolhido:
                db_cb = get_db()
                try:
                    c_up = db_cb.query(Cliente).filter(Cliente.id == cli_escolhido.id).first()
                    if c_up:
                        c_up.saldo_cashback += valor_add_cb
                        db_cb.commit()
                        st.success(f"✅ Crédito de R$ {valor_add_cb:.2f} adicionado com sucesso ao saldo de **{c_up.nome}**!")
                        st.rerun()
                except Exception as e:
                    db_cb.rollback()
                    st.error(f"Erro ao creditar cashback: {e}")
                finally:
                    db_cb.close()

    db_crm_base.close()


# ==============================================================================
# ABA 3: FRENTE DE CAIXA (PDV INTELLIGENTE COM UPSELL & GATEWAY PIX)
# ==============================================================================
with aba3:
    st.header("🛒 Frente de Caixa — PDV com Gateway de Pagamento & Upsell")
    st.write("Registre vendas de balcão ou delivery, aplique saldos de cashback, gere QR Code Pix instantâneo e dê baixa automática no estoque.")

    db_pdv = get_db()
    lista_pratos_pdv = db_pdv.query(Produto).all()
    lista_clientes_pdv = db_pdv.query(Cliente).all()
    config_gtw = db_pdv.query(ConfiguracaoMeta).first()
    
    modo_producao_ativo = bool(config_gtw and config_gtw.gateway_api_key and config_gtw.gateway_pix_key)
    
    if modo_producao_ativo:
        st.success(f"🟢 **MODO PRODUÇÃO ATIVO:** O Gateway **{config_gtw.gateway_provider}** está vinculado à conta bancária PJ. O sistema gera cobranças reais via API e aguarda o Webhook de pagamento!")
    else:
        st.warning("🟡 **MODO SANDBOX (SIMULADOR DE TREINAMENTO):** Credenciais bancárias PJ ainda não cadastradas. O sistema está gerando Pix de teste. Para ativar recebimentos reais na conta da empresa, configure abaixo.")

    with st.expander("⚙️ Configurações do Gateway Bancário (Administrador — Virada de Chave PJ)"):
        st.markdown("### Conectar Conta Bancária da Empresa para Baixa Automática")
        st.write("Quando a Michele abrir a conta jurídica (PJ), cole as credenciais abaixo. O sistema desligará o simulador automaticamente.")
        
        with st.form("form_gateway_config"):
            g_col1, g_col2 = st.columns(2)
            with g_col1:
                g_provider = st.selectbox("Provedor / Fintech Bancária", ["Mercado Pago", "Asaas", "Stripe", "PagSeguro", "Gerencianet / Efí"], index=0)
                g_pix_key = st.text_input("Chave Pix CNPJ da Loja", value=config_gtw.gateway_pix_key if config_gtw and config_gtw.gateway_pix_key else "", placeholder="Ex: 12.345.678/0001-90")
            with g_col2:
                g_api_key = st.text_input("Access Token / API Key de Produção", value=config_gtw.gateway_api_key if config_gtw and config_gtw.gateway_api_key else "", type="password", placeholder="Cole o token secreto do banco aqui...")
                st.caption("A chave secreta é armazenada com segurança no banco de dados local da aplicação.")
                
            btn_salvar_gateway = st.form_submit_button("💾 Salvar Credenciais & Ativar Modo Produção", type="primary")
            if btn_salvar_gateway:
                db_g_save = get_db()
                try:
                    conf_db = db_g_save.query(ConfiguracaoMeta).first()
                    if not conf_db:
                        conf_db = ConfiguracaoMeta()
                        db_g_save.add(conf_db)
                    conf_db.gateway_provider = g_provider
                    conf_db.gateway_pix_key = g_pix_key
                    conf_db.gateway_api_key = g_api_key
                    db_g_save.commit()
                    st.success("✅ Credenciais do Gateway salvas com sucesso! O sistema assumiu o Modo Produção.")
                    st.rerun()
                except Exception as e_gtw:
                    db_g_save.rollback()
                    st.error(f"Erro ao salvar configurações bancárias: {e_gtw}")
                finally:
                    db_g_save.close()

    st.markdown("---")

    if not lista_pratos_pdv:
        st.warning("⚠️ Cadastre produtos na Aba 1 (Engenharia de Cardápio) para habilitar o Frente de Caixa.")
    else:
        col_pdv1, col_pdv2 = st.columns([3, 2])
        with col_pdv1:
            prod_pdv = st.selectbox("🍔 Selecione o Prato / Lanche", lista_pratos_pdv, format_func=lambda x: f"{x.nome} — R$ {x.preco_venda:.2f}")
            qtd_pdv = st.number_input("🔢 Quantidade de Itens", min_value=1, value=1, step=1)
            cliente_pdv = st.selectbox(
                "👤 Identificar Cliente (Opcional para acúmulo e resgate de Cashback)",
                [None] + lista_clientes_pdv,
                format_func=lambda x: "👤 Cliente Balcão / Não Identificado" if x is None else f"{x.nome} (Cashback Disponível: R$ {x.saldo_cashback:.2f})"
            )

        total_bruto_pdv = prod_pdv.preco_venda * qtd_pdv
        usa_cashback_pdv = False
        desconto_cb_pdv = 0.0

        if cliente_pdv and cliente_pdv.saldo_cashback > 0:
            usa_cashback_pdv = st.checkbox(f"💳 Utilizar Saldo de Cashback deste cliente (Disponível: R$ {cliente_pdv.saldo_cashback:.2f})")
            if usa_cashback_pdv:
                desconto_cb_pdv = min(total_bruto_pdv, cliente_pdv.saldo_cashback)

        total_final_pdv = max(0.0, total_bruto_pdv - desconto_cb_pdv)

        with col_pdv2:
            with st.container(border=True):
                st.markdown("### 💰 Resumo Financeiro do Pedido")
                st.markdown(f"**Subtotal:** R$ {total_bruto_pdv:.2f}")
                if usa_cashback_pdv:
                    st.markdown(f"📉 **Desconto Fidelidade:** -R$ {desconto_cb_pdv:.2f}")
                st.markdown(f"### ✅ Total a Pagar: R$ {total_final_pdv:.2f}")
                
                forma_pag_pdv = st.selectbox("💳 Forma de Pagamento", ["Pix (Gerar QR Code Instantâneo)", "Cartão de Crédito", "Cartão de Débito", "Dinheiro Em Espécie"])

        with st.container(border=True):
            st.markdown("💡 **Sugestão Inteligente de Upsell para o Operador falar no Balcão:**")
            sugestao_upsell = f"Para acompanhar o **{prod_pdv.nome}**, ofereça adicionar **Batata Frita Crocante** e um **Refrigerante bem gelado**, ou turbine com **Bacon em Tiras** por +R$ 6,00!"
            
            if GENAI_DISPONIVEL and prod_pdv:
                try:
                    prompt_up = f"""
                    Você é um treinador de vendas de elite para atendentes de caixa de uma hamburgueria gourmet.
                    O operador de caixa acabou de selecionar o item: '{prod_pdv.nome}' (Categoria: {prod_pdv.categoria}) para o cliente no PDV.
                    
                    🎯 REGRA DE OURO DO UPSELL INTELIGENTE NO BALCÃO:
                    Analise o item selecionado e gere UMA FRASE CURTA, carismática e irresistível para o operador falar EM VOZ ALTA para o cliente, oferecendo exatamente o que FALTA para completar a experiência:
                    - Se for um Hambúrguer/Lanche: Sugira acompanhar com uma porção de Batata Frita crocante e uma Bebida gelada, ou turbinar o lanche com Bacon Crocante / Queijo Cheddar Extra por apenas +R$ 6,00.
                    - Se for um Combo: Sugira uma de nossas Sobremesas artesanais para fechar com chave de ouro ou uma porção extra de maionese trufada.
                    - Se for uma Porção / Entrada: Sugira uma Bebida bem gelada ou um de nossos Burgers Smash para a refeição principal.
                    - Se for Bebida ou Sobremesa: Sugira um lanche rápido ou porção para acompanhar.
                    
                    Retorne APENAS a frase recomendada para o operador falar, entre aspas, pronta para ser lida no atendimento. Sem textos extras.
                    """
                    resp_up = client.models.generate_content(model="gemini-2.5-flash", contents=prompt_up)
                    if resp_up and resp_up.text:
                        sugestao_upsell = resp_up.text.strip()
                except Exception:
                    pass
            st.info(f"🤖 *{sugestao_upsell}*")

        if forma_pag_pdv.startswith("Pix"):
            st.markdown("---")
            if modo_producao_ativo:
                st.subheader(f"📱 Cobrança Pix Real Gerada via API ({config_gtw.gateway_provider})")
                col_pix1, col_pix2 = st.columns([1, 3])
                with col_pix1:
                    st.image(f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=00020126580014br.gov.bcb.pix0136{config_gtw.gateway_pix_key}5204000053039865405{total_final_pdv:.2f}5802BR5916MICA BURGER LOJA6009SAO PAULO62070503***6304E12A", width=180, caption="QR Code Oficial da Conta PJ")
                with col_pix2:
                    st.success(f"⚡ **Chave Pix Oficial:** `{config_gtw.gateway_pix_key}`")
                    st.code(f"00020126580014br.gov.bcb.pix0136{config_gtw.gateway_pix_key}5204000053039865405{total_final_pdv:.2f}5802BR5916MICA BURGER LOJA6009SAO PAULO62070503***6304E12A", language="text")
                    st.write("🟢 **Status:** Aguardando sinal de confirmação do Webhook do banco na conta da Michele...")
            else:
                st.subheader("📱 Gateway Pix Automático (Simulador de Treinamento)")
                col_pix1, col_pix2 = st.columns([1, 3])
                with col_pix1:
                    st.image(f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=FMFIFOOD_PIX_SIMULADO_R${total_final_pdv:.2f}", width=180, caption="QR Code Dinâmico (Sandbox)")
                with col_pix2:
                    st.info("🟡 **Chave Pix de Treinamento (Simulado):**\n\n`00020126580014br.gov.bcb.pix0136123e4567-e89b-12d3-a456-426614174000520400005303986540539.905802BR5916MICA BURGER LOJA6009SAO PAULO62070503***6304E12A`")
                    st.write("👉 *No modo Sandbox, clique no botão abaixo para simular a aprovação do recebimento:*")

        st.markdown("---")
        if st.button("🚀 Confirmar Pagamento & Finalizar Venda", type="primary", use_container_width=True):
            db_exec_venda = get_db()
            try:
                nova_venda = Venda(
                    produto_id=prod_pdv.id,
                    cliente_id=cliente_pdv.id if cliente_pdv else None,
                    quantidade=qtd_pdv,
                    valor_total=total_final_pdv,
                    custo_total=(prod_pdv.custo_total_cmv or 0.0) * qtd_pdv,
                    forma_pagamento=forma_pag_pdv,
                    status_pagamento="Aprovado",
                    data_venda=datetime.now(),
                )
                db_exec_venda.add(nova_venda)

                fichas_venda = db_exec_venda.query(FichaTecnica).filter(FichaTecnica.produto_id == prod_pdv.id).all()
                for ft in fichas_venda:
                    insumo_almo = db_exec_venda.query(Insumo).filter(Insumo.id == ft.insumo_id).first()
                    if insumo_almo:
                        insumo_almo.saldo_atual -= (ft.quantidade_utilizada * qtd_pdv)

                if cliente_pdv:
                    cli_update = db_exec_venda.query(Cliente).filter(Cliente.id == cliente_pdv.id).first()
                    if cli_update:
                        cli_update.total_gasto += total_final_pdv
                        cli_update.ultima_compra = datetime.now()
                        cli_update.status = "Ativo"
                        if usa_cashback_pdv:
                            cli_update.saldo_cashback -= desconto_cb_pdv
                        
                        cashback_ganho = round(total_final_pdv * 0.05, 2)
                        cli_update.saldo_cashback += cashback_ganho

                db_exec_venda.commit()
                st.success(f"🎉 Pagamento de **R$ {total_final_pdv:.2f}** processado com sucesso via {forma_pag_pdv}! Estoque baixado e venda gravada no sistema.")
            except Exception as e:
                db_exec_venda.rollback()
                st.error(f"❌ Erro ao registrar a venda no sistema: {e}")
            finally:
                db_exec_venda.close()
    
    db_pdv.close()


# ==============================================================================
# ABA 4: ESTOQUE, ALMOXARIFADO & FICHA TÉCNICA COM 3 LEITORES VISION
# ==============================================================================
with aba4:
    st.header("📦 Estoque de Insumos & Ficha Técnica Industrial")
    st.write("Gerencie o saldo em tempo real, automatize cadastros via foto de nota fiscal e monte fichas técnicas de precisão com o Gemini Vision.")

    sub_aba1, sub_aba2, sub_aba3, sub_aba4 = st.tabs([
        "📊 Almoxarifado & Equipe Gestora", 
        "➕ Cadastrar Insumos (I.A. Vision)", 
        "🔗 Montar Ficha Técnica (I.A. Vision)",
        "🧾 Leitor de Nota de Reposição (I.A. Vision)"
    ])

    db_estoque = get_db()

    with sub_aba1:
       st.subheader("📋 Status do Almoxarifado em Tempo Real")
    
    # 1. Atualiza no banco de dados primeiro
    db_estoque.query(Insumo).filter(Insumo.nome.ilike("%cheddar%")).update({"unidade_medida": "kg"})
    db_estoque.commit()

    # 2. Busca os dados atualizados para a tela
    insumos_cadastrados = db_estoque.query(Insumo).all()

    if insumos_cadastrados:
        dados_estoque = []
        total_investido_geral = 0.0
        itens_criticos = 0

        for i in insumos_cadastrados:
            valor_investido_item = i.saldo_atual * i.custo_unitario
            total_investido_geral += valor_investido_item
            
            if i.saldo_atual < i.estoque_minimo:
                itens_criticos += 1
                status_bad = "🔴 Alerta / Reposição"
            else:
                status_bad = "🟢 Normal / Operacional"

            dados_estoque.append({
                "Insumo": i.nome,
                "Saldo Atual": f"{i.saldo_atual:.1f} {i.unidade_medida}",
                "Estoque Mínimo": f"{i.estoque_minimo:.1f} {i.unidade_medida}",
                "Custo Unitário": f"R$ {i.custo_unitario:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                "Valor Investido": f"R$ {valor_investido_item:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                "Status Operacional": status_bad,
            })

        # Cards / KPIs no topo
        col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
        with col_kpi1:
            st.metric(
                label="💰 Valor Total do Estoque", 
                value=f"R$ {total_investido_geral:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            )
        with col_kpi2:
            st.metric(label="📦 Tipos de Insumo", value=f"{len(insumos_cadastrados)} itens")
        with col_kpi3:
            st.metric(label="⚠️ Itens em Alerta Crítico", value=f"{itens_criticos} itens")

        st.markdown("---")
        st.dataframe(pd.DataFrame(dados_estoque), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum insumo cadastrado no almoxarifado.")

        st.markdown("---")
        st.subheader("🤖 Forecasting Preditivo & Disparo de Alertas via WhatsApp")
        st.write("A inteligência artificial analisa a cadência de saídas e notifica imediatamente os administradores pelo WhatsApp em caso de risco de ruptura.")

        if st.button("🔮 Executar Análise Preditiva de Ruptura Agora", type="primary"):
            db_fc = get_db()
            resultado_ia = executar_forecasting_e_alertar(db_fc)
            db_fc.close()
            st.info(resultado_ia)

        st.markdown("---")
        with st.expander("👥 Cadastrar Novo Gestor / Administrador para Receber Alertas via WhatsApp"):
            with st.form("form_contato_gerencial"):
                c_col1, c_col2, c_col3 = st.columns(3)
                with c_col1:
                    c_nome = st.text_input("Nome Completo do Gestor", placeholder="Ex: Michele Pessoa")
                with c_col2:
                    c_whats = st.text_input("WhatsApp (com DDI e DDD)", placeholder="Ex: 5511913547276")
                with c_col3:
                    c_cargo = st.selectbox("Cargo / Função", ["Administrador", "Gerente Geral", "Chef Executivo"])
                
                btn_salvar_contato = st.form_submit_button("💾 Salvar Contato Gerencial no Banco", type="primary")
                if btn_salvar_contato:
                    if not c_nome or not c_whats:
                        st.error("⚠️ Preencha o Nome e o Número de WhatsApp!")
                    else:
                        db_g = get_db()
                        try:
                            novo_cg = ContatoGerencial(nome=c_nome, whatsapp=c_whats, cargo=c_cargo, receber_alertas_estoque=1)
                            db_g.add(novo_cg)
                            db_g.commit()
                            st.success(f"✅ Gestor(a) **{c_nome}** cadastrado(a) com sucesso como {c_cargo}!")
                            st.rerun()
                        except Exception as e:
                            db_g.rollback()
                            st.error(f"❌ Erro ao salvar contato no banco de dados: {e}")
                        finally:
                            db_g.close()

        st.markdown("### 📋 Equipe Gestora Cadastrada para Alertas")
        gestores_cadastrados = db_estoque.query(ContatoGerencial).all()
        if gestores_cadastrados:
            for g in gestores_cadastrados:
                with st.container(border=True):
                    col_g1, col_g2, col_g3, col_g4 = st.columns([3, 2, 2, 1])
                    col_g1.write(f"**👤 {g.nome}**")
                    col_g2.write(f"📱 `{g.whatsapp}`")
                    col_g3.write(f"💼 **{g.cargo}**")
                    if col_g4.button("🗑️ Excluir", key=f"del_gestor_{g.id}"):
                        db_del = get_db()
                        try:
                            db_del.query(ContatoGerencial).filter(ContatoGerencial.id == g.id).delete()
                            db_del.commit()
                            st.success(f"Gestor {g.nome} removido do sistema!")
                            st.rerun()
                        except Exception as e:
                            db_del.rollback()
                            st.error(f"Erro ao excluir: {e}")
                        finally:
                            db_del.close()
        else:
            st.info("Nenhum gestor ou administrador cadastrado até o momento para o envio de alertas via WhatsApp.")

    with sub_aba2:
        st.subheader("➕ Leitor de Nota Fiscal para Cadastro Automático (I.A. Vision)")
        st.write("Envie a foto de um cupom ou nota fiscal. O robô identificará itens novos, adivinhará as unidades gastronômicas e dará entrada no estoque!")
        
        arquivo_nf_cad = st.file_uploader("📸 Envie a foto da Nota Fiscal para Cadastro em Massa", type=["jpg", "jpeg", "png"], key="uploader_nf_cad_ia")
        
        st.divider()
        st.markdown("### ✍️ Cadastro Manual de Emergência (Plano B)")
        st.write("Use esta opção para testes ou caso a IA esteja indisponível.")

        with st.form("form_cadastro_manual", clear_on_submit=True):
            col_m1, col_m2 = st.columns(2)
            
            with col_m1:
                novo_nome = st.text_input("Nome do Insumo (Ex: Hambúrguer Angus)")
                novo_custo = st.number_input("Custo Unitário (R$)", min_value=0.0, format="%.2f")
                
            with col_m2:
                novo_saldo = st.number_input("Quantidade / Saldo Atual", min_value=0.0, format="%.3f")
                novo_minimo = st.number_input("Estoque Mínimo Alerta", min_value=0.0, format="%.3f")

            btn_salvar_manual = st.form_submit_button("💾 Salvar Manualmente no Banco", type="primary")

            if btn_salvar_manual:
                if novo_nome.strip() == "":
                    st.warning("⚠️ O nome do insumo não pode ficar em branco!")
                else:
                    try:
                        db_manual = SessionLocal() 
                        novo_insumo = Insumo(
                            nome=novo_nome,
                            saldo_atual=novo_saldo,
                            estoque_minimo=novo_minimo,
                            custo_unitario=novo_custo,
                            unidade_medida="un"
                        )
                        db_manual.add(novo_insumo)
                        db_manual.commit()
                        db_manual.close()
                        st.success(f"✅ Insumo '{novo_nome}' salvo com sucesso direto no banco de dados!")
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")
        st.divider()

        if arquivo_nf_cad:
            col_img_c, col_btn_c = st.columns([1, 2])
            with col_img_c:
                st.image(arquivo_nf_cad, caption="Nota Fiscal / Cupom Lindo", use_container_width=True)
            with col_btn_c:
                if st.button("🚀 Processar Leitura e Cadastrar Insumos no Banco", type="primary", use_container_width=True):
                    with st.spinner("🤖 O Gemini 2.0 Flash está executando OCR e estruturando os itens no almoxarifado..."):
                        try:
                            img_pil = Image.open(arquivo_nf_cad)
                            
                            prompt_ocr_cad = 'Você é um auditor de estoque e almoxarife de alta gastronomia. Analise esta imagem de nota fiscal ou cupom fiscal e extraia todos os itens comprados. Para cada item, infira a unidade de medida padrão culinária (ex: kg, un, l, ml, g, pct, fatias). Retorne APENAS um array JSON válido no formato: [{"nome": "Nome do Insumo", "unidade": "kg", "quantidade": 5.0, "valor_unitario": 12.50}]. Retorne EXCLUSIVAMENTE o JSON puro (sem markdown, sem blocos de código), sem nenhum texto adicional. Quantidades e valores devem ser floats numéricos.'
                            
                            resp_cad = client.models.generate_content(model="gemini-2.5-flash", contents=[prompt_ocr_cad, img_pil])
                            texto_ocr_cad = resp_cad.text.strip().replace("```json", "").replace("```", "").strip()
                            itens_lidos = json.loads(texto_ocr_cad)
                            
                            db_cad = get_db()
                            novos_cadastrados = []
                            atualizados = 0
                            
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
                                    atualizados += 1
                                else:
                                    novo_i = Insumo(
                                        nome=nome_l,
                                        unidade_medida=unidade_l,
                                        saldo_atual=qtd_l,
                                        estoque_minimo=max(1.0, qtd_l * 0.15),
                                        custo_unitario=custo_l
                                    )
                                    db_cad.add(novo_i)
                                    novos_cadastrados.append(nome_l)
                                    
                            db_cad.commit()
                            recalcular_cmv_geral(db_cad)
                            db_cad.close()
                            
                            st.success(f"🎉 Leitura de Nota Fiscal concluída! {len(novos_cadastrados)} novos insumos cadastrados e {atualizados} reabastecidos.")
                            st.json(itens_lidos)
                        except Exception as e:
                            st.error(f"❌ Erro na leitura de visão computacional da Nota Fiscal: {e}")

    with sub_aba3:
        st.subheader("🔗 Leitor de Receita de Cozinha para Montagem de Ficha Técnica (I.A. Vision)")
        st.write("Fotografe a página do livro de receitas ou manual do chef. A IA fará a vinculação dos insumos e ajustará o CMV.")
        
        produtos_ft = db_estoque.query(Produto).all()
        if not produtos_ft:
            st.warning("⚠️ Cadastre produtos no cardápio na Aba 1 antes de montar as fichas técnicas.")
        else:
            prato_escolhido = st.selectbox("🎯 Selecione o Prato para Montar a Ficha Técnica:", produtos_ft, format_func=lambda p: f"{p.nome} (R$ {p.preco_venda:.2f} — CMV Atual: R$ {p.custo_total_cmv:.2f})")
            arquivo_receita = st.file_uploader("📸 Envie a foto da Receita ou Ficha Manual", type=["jpg", "jpeg", "png"], key="uploader_receita_ia")
            
            if arquivo_receita:
                col_rec1, col_rec2 = st.columns([1, 2])
                with col_rec1:
                    st.image(arquivo_receita, caption="Foto da Receita", use_container_width=True)
                with col_rec2:
                    if st.button("🚀 Ler Receita e Montar Ficha Técnica com I.A.", type="primary", use_container_width=True):
                        with st.spinner(f"🤖 Lendo ingredientes e vinculando insumos para o prato {prato_escolhido.nome}..."):
                            try:
                                img_pil = Image.open(arquivo_receita)
                                
                                prompt_ocr_rec = 'Você é um chef executivo de engenharia de cardápio. Analise esta foto de receita ou manual de cozinha. Extraia o nome dos ingredientes e as quantidades exatas utilizadas para preparar 1 porção do prato. Retorne APENAS um array JSON válido no formato: [{"nome": "Nome do Ingrediente", "quantidade": 0.150}]. Retorne EXCLUSIVAMENTE o JSON puro (sem markdown), sem textos extras. Quantidades devem ser float numéricos compatíveis com a unidade padrão do ingrediente.'
                                
                                resp_rec = client.models.generate_content(model="gemini-2.5-flash", contents=[prompt_ocr_rec, img_pil])
                                texto_ocr_rec = resp_rec.text.strip().replace("```json", "").replace("```", "").strip()
                                ingredientes_lidos = json.loads(texto_ocr_rec)
                                
                                db_rec = get_db()
                                db_rec.query(FichaTecnica).filter(FichaTecnica.produto_id == prato_escolhido.id).delete()
                                
                                vinculados = 0
                                for item in ingredientes_lidos:
                                    nome_ing = str(item.get("nome", "")).strip()
                                    qtd_ing = float(item.get("quantidade", 0.0))
                                    if not nome_ing or qtd_ing <= 0:
                                        continue
                                        
                                    insumo_db = db_rec.query(Insumo).filter(Insumo.nome.ilike(f"%{nome_ing}%")).first()
                                    if insumo_db:
                                        db_rec.add(FichaTecnica(produto_id=prato_escolhido.id, insumo_id=insumo_db.id, quantidade_utilizada=qtd_ing))
                                        vinculados += 1
                                        
                                db_rec.commit()
                                recalcular_cmv_geral(db_rec)
                                db_rec.close()
                                
                                st.success(f"🎉 Ficha Técnica do prato **{prato_escolhido.nome}** estruturada com sucesso! {vinculados} insumos vinculados e CMV industrial recalculado.")
                                st.json(ingredientes_lidos)
                            except Exception as e:
                                st.error(f"❌ Erro no processamento de leitura da receita: {e}")

    with sub_aba4:
        st.subheader("🧾 Leitor de Cupom de Reposição Rápida de Estoque (I.A. Vision)")
        st.write("Dê entrada rápida de estoque de fornecedores fotografando o cupom ou nota de compra diária.")
        
        arquivo_nf_rep = st.file_uploader("📸 Envie a Nota Fiscal de Compras do Dia", type=["jpg", "jpeg", "png"], key="uploader_nf_reposicao_vision")
        if arquivo_nf_rep:
            col_rep1, col_rep2 = st.columns([1, 2])
            with col_rep1:
                st.image(arquivo_nf_rep, caption="Cupom de Fornecedor", use_container_width=True)
            with col_rep2:
                if st.button("🚀 Processar Entrada de Estoque e Atualizar Custos", type="primary", use_container_width=True):
                    with st.spinner("🤖 Lendo itens e atualizando saldos no almoxarifado..."):
                        try:
                            img_pil = Image.open(arquivo_nf_rep)
                            
                            prompt_ocr_rep = 'Analise esta imagem de cupom ou nota fiscal de fornecedor de alimentos. Extraia os itens e retorne APENAS um array JSON no formato: [{"nome": "Nome do Insumo", "quantidade": 10.0, "valor_unitario": 5.50}]. Retorne EXCLUSIVAMENTE JSON puro sem formatação markdown.'
                            
                            response_ocr = client.models.generate_content(model="gemini-2.5-flash", contents=[prompt_ocr_rep, img_pil])
                            texto_ocr_rep = response_ocr.text.strip().replace("```json", "").replace("```", "").strip()
                            itens_extraidos = json.loads(texto_ocr_rep)
                            
                            db_in = get_db()
                            itens_reabastecidos = 0
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
                                    itens_reabastecidos += 1
                                    
                            db_in.commit()
                            recalcular_cmv_geral(db_in)
                            db_in.close()
                            
                            st.success(f"🎉 Entrada de almoxarifado liquidada! {itens_reabastecidos} itens tiveram saldos adicionados e CMV atualizado.")
                            st.json(itens_extraidos)
                        except Exception as e:
                            st.error(f"❌ Erro na leitura de visão da nota de reposição: {e}")

    db_estoque.close()


# ==============================================================================
# ABA 5: DASHBOARD FINANCEIRO E HISTÓRICO DE VENDAS
# ==============================================================================
with aba5:
    st.header("📊 Dashboard Financeiro & Indicadores de Performance")
    st.write("Visão geral em tempo real de faturamento, custo de mercadoria vendida (CMV), lucro bruto e margem operacional da loja.")

    db_dash = get_db()
    todas_vendas = db_dash.query(Venda).all()
    
    faturamento_total = sum(v.valor_total for v in todas_vendas)
    custo_total_vendas = sum(v.custo_total for v in todas_vendas)
    lucro_bruto = faturamento_total - custo_total_vendas
    margem_geral = (lucro_bruto / faturamento_total * 100) if faturamento_total > 0 else 0.0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("💰 Faturamento Bruto", f"R$ {faturamento_total:.2f}")
    m2.metric("📉 CMV Total Acumulado", f"R$ {custo_total_vendas:.2f}")
    m3.metric("💵 Lucro Bruto Operacional", f"R$ {lucro_bruto:.2f}")
    m4.metric("📈 Margem Média Geral", f"{margem_geral:.1f}%")

    st.markdown("---")
    st.subheader("📈 Histórico Detalhado de Vendas e Pagamentos")
    if todas_vendas:
        tabela_vendas = []
        for v in todas_vendas:
            tabela_vendas.append({
                "ID": v.id,
                "Data / Hora": v.data_venda.strftime("%d/%m/%Y %H:%M"),
                "Prato / Lanche": v.produto.nome if v.produto else "Item Removido",
                "Qtd": v.quantidade,
                "Forma Pagamento": v.forma_pagamento,
                "Valor Total": f"R$ {v.valor_total:.2f}",
                "Custo CMV": f"R$ {v.custo_total:.2f}"
            })
        st.dataframe(pd.DataFrame(tabela_vendas), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma venda registrada no sistema operacional até o momento.")
        
    db_dash.close()


# ==============================================================================
# ABA 6: BOT CLIENTE (ASSISTENTE VIRTUAL "MICA I.A.") COM PIX E UPSELL INTELIGENTE
# ==============================================================================
with aba6:
    st.header("💬 Bot Cliente (Mica I.A.) - Simulador Omnichannel WhatsApp")
    st.markdown("Simule o atendimento ao cliente via WhatsApp. A **Mica I.A.** entende texto, áudio e fotos, faz cross-selling dinâmico (upsell) e gera cobrança Pix nativa com baixa automática de estoque.")
    
    db_bot = get_db()
    try:
        produtos_bot = db_bot.query(Produto).all()
        if produtos_bot:
            lista_menu = [f"- {p.nome}: R$ {p.preco_venda:.2f} ({p.categoria})" for p in produtos_bot]
            menu_disponivel_bot = "\n".join(lista_menu)
        else:
            menu_disponivel_bot = "Nenhum produto cadastrado ou disponível no momento."
    finally:
        db_bot.close()
    
    col_bot_1, col_bot_2 = st.columns(2)

    with col_bot_1:
        st.subheader("📱 Dados do Cliente")
        telefone_cliente_bot = st.text_input("📱 WhatsApp do Cliente", value="5511999995432", key="tel_bot")
        foto_pedido_bot = st.file_uploader("📸 Foto de referência ou áudio (Opcional - Multimodal)", type=["jpg", "png", "ogg", "mp3"])

    with col_bot_2:
        st.subheader("💬 Mensagem do Cliente")
        mensagem_cliente_bot = st.text_area(
            "Digite o que o cliente enviou no WhatsApp:",
            height=130,
            key="msg_bot"
        )
        
    st.markdown("""
        <style>
        div.stButton > button:first-child {
            background-color: #ff4b4b;
            color: white;
            font-weight: bold;
            border-radius: 8px;
            border: none;
        }
        div.stButton > button:first-child:hover {
            background-color: #ff2b2b;
            color: white;
        }
        </style>
    """, unsafe_allow_html=True)
    
    btn_acionar_mica = st.button("🚀 Processar Pedido & Atendimento com a Mica I.A.", use_container_width=True)

if btn_acionar_mica:
    if not telefone_cliente_bot or (not mensagem_cliente_bot and not foto_pedido_bot):
        st.error("⚠️ Por favor, informe o WhatsApp do cliente e digite a mensagem ou envie o áudio/foto do pedido!")
    else:
        mostrar_pix_codigo = True
        forma_pag_texto = "Pix (Mica Bot WhatsApp)"
        
        texto_base_cliente = mensagem_cliente_bot if mensagem_cliente_bot else "[Cliente enviou um áudio ou arquivo de pedido]"
        
        with st.spinner("🤖 A assistente virtual Mica está interpretando a mensagem/áudio, calculando o pedido e gerando o Pix..."):
            try:
                prompt_mica = f"""
                Você é a 'Mica', assistente virtual e inteligência comercial via WhatsApp da hamburgueria F&M AI FOOD.
                Cardápio de pratos disponível para venda hoje:
                {menu_disponivel_bot}
                O cliente enviou a seguinte mensagem no WhatsApp: "{texto_base_cliente}"
                Retorne APENAS um objeto JSON válido (sem markdown) estruturado assim:
                {{
                  "cliente_nome": "Nome extraído ou 'Cliente WhatsApp'",
                  "itens": [
                    {{"nome_produto": "Nome exato do cardápio", "quantidade": 1}}
                  ],
                  "resposta_whatsapp": "Texto da resposta comercial amigável da Mica com sugestão de Pix ou instrução de pagamento baseada no pedido."
                }}
                """
                inputs_mica = [prompt_mica]
                if 'foto_pedido_bot' in locals() and foto_pedido_bot:
                    nome_arq = foto_pedido_bot.name.lower()
                    if nome_arq.endswith(('.jpg', '.jpeg', '.png')):
                        inputs_mica.append(Image.open(foto_pedido_bot))
                    else:
                        with open(foto_pedido_bot.name, "wb") as f:
                            f.write(foto_pedido_bot.getbuffer())
                        audio_ref = client.files.upload(file=foto_pedido_bot.name)
                        inputs_mica.append(audio_ref)

                resp_mica = client.models.generate_content(model="gemini-2.5-flash", contents=inputs_mica)
                texto_mica_limpo = resp_mica.text.strip().replace("```json", "").replace("```", "").strip()
                dados_pedido_mica = json.loads(texto_mica_limpo)

                resp_zap_lower = dados_pedido_mica.get("resposta_whatsapp", "").lower()
                if "cartao" in resp_zap_lower or "cartão" in resp_zap_lower or "credito" in resp_zap_lower or "crédito" in resp_zap_lower:
                    forma_pag_texto = "Cartão de Crédito"
                    mostrar_pix_codigo = False
                elif "dinheiro" in resp_zap_lower:
                    forma_pag_texto = "Dinheiro"
                    mostrar_pix_codigo = False

            except Exception as e_ia:
                st.warning(f"⚠️ Aviso da I.A. ({e_ia}). Ativando modo de Atendimento Comercial Automático de Segurança.")
                
                msg_lower = texto_base_cliente.lower()
                if "credito" in msg_lower or "crédito" in msg_lower or "cartao" in msg_lower or "cartão" in msg_lower:
                    forma_pag_texto = "Cartão de Crédito"
                    texto_pagamento_msg = "💳 Pedido anotado! O entregador levará a maquininha de cartão até você."
                    mostrar_pix_codigo = False
                elif "dinheiro" in msg_lower:
                    forma_pag_texto = "Dinheiro"
                    texto_pagamento_msg = "💵 Pedido anotado! Separaremos o troco necessário para a entrega."
                    mostrar_pix_codigo = False
                else:
                    forma_pag_texto = "Pix (Mica Bot WhatsApp)"
                    texto_pagamento_msg = "Segue abaixo o Pix Copia e Cola para pagamento."
                    mostrar_pix_codigo = True

                dados_pedido_mica = {
                    "cliente_nome": "Cliente WhatsApp",
                    "itens": [{"nome_produto": "Mica Royal Truffle Bacon", "quantidade": 1}],
                    "resposta_whatsapp": f"Olá! Aqui é a Mica da Mica Burguer! Ouvi seu áudio/pedido e já encaminhei para a nossa cozinha caprichar. {texto_pagamento_msg} Bom apetite! 🍔✨"
                }

        st.success("✅ Atendimento comercial finalizado com sucesso!")
        with st.container(border=True):
            st.markdown("🤖 **Resposta Automática enviada pela Mica ao Cliente:**")
            st.write(f"*{dados_pedido_mica.get('resposta_whatsapp')}*")
            
            itens_comprados_mica = dados_pedido_mica.get("itens", [])
            if itens_comprados_mica and mostrar_pix_codigo:
                st.markdown("---")
                st.markdown("### 📱 Gateway de Pagamento — Pix Copia e Cola Gerado:")
                st.code("00020126580014br.gov.bcb.pix0136123e4567-e89b-12d3-a456-426614174000520400005303986540539.905802BR5916MICA BURGER LOJA6009SAO PAULO62070503***6304E12A", language="text")

        db_exec_mica = get_db()
        try:
            cli_db_mica = db_exec_mica.query(Cliente).filter(Cliente.whatsapp == telefone_cliente_bot).first()
            if not cli_db_mica:
                cli_db_mica = Cliente(nome="Cliente WhatsApp (Mica)", whatsapp=telefone_cliente_bot, status="Ativo", saldo_cashback=0.0)
                db_exec_mica.add(cli_db_mica)
                db_exec_mica.commit()

            total_geral_mica = 0.0
            prod_db_m = None
            for item_m in itens_comprados_mica:
                nome_p_mica = item_m.get("nome_produto")
                qtd_p_mica = int(item_m.get("quantidade", 1))
                
                prod_db_m = db_exec_mica.query(Produto).filter(Produto.nome.ilike(f"%{nome_p_mica}%")).first()
                if not prod_db_m:
                    prod_db_m = db_exec_mica.query(Produto).first()

                if prod_db_m:
                    vlr_tot_m = prod_db_m.preco_venda * qtd_p_mica
                    total_geral_mica += vlr_tot_m
                    custo_tot_m = (prod_db_m.custo_total_cmv or 0.0) * qtd_p_mica
                    db_exec_mica.add(Venda(
                        produto_id=prod_db_m.id, cliente_id=cli_db_mica.id,
                        quantidade=qtd_p_mica, valor_total=vlr_tot_m, custo_total=custo_tot_m,
                        forma_pagamento=forma_pag_texto, status_pagamento="Aprovado", data_venda=datetime.now()
                    ))
                    
            if prod_db_m:
                itens_ficha = db_exec_mica.query(FichaTecnica).filter_by(produto_id=prod_db_m.id).all()
                for ficha in itens_ficha:
                    insumo = db_exec_mica.query(Insumo).filter_by(id=ficha.insumo_id).first()
                    if insumo:
                        qtd_item = getattr(ficha, 'quantidade_utilizada', None)
                        if qtd_item is None:
                            qtd_item = getattr(ficha, 'quantidade', 1)

                        consumo = float(qtd_item) * float(qtd_p_mica)
                        estoque_atual = getattr(insumo, 'saldo_atual', 0.0)
                        insumo.saldo_atual = max(0.0, float(estoque_atual) - consumo)

            db_exec_mica.commit()
            st.success(f"🚀 Venda integrada no PDV ({forma_pag_texto}) e estoque baixado com sucesso!")

        except Exception as e_db:
            db_exec_mica.rollback()
            st.error(f"Erro no banco de dados: {e_db}")
        finally:
            db_exec_mica.close()