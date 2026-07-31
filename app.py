import os
import streamlit as st

# Patch: ensure compatibility with custom keyword args used across the app
try:
    if not hasattr(st, "_orig_container"):
        st._orig_container = st.container
        def _container_compat(*args, **kwargs):
            kwargs.pop("border", None)
            kwargs.pop("bordered", None)
            return st._orig_container(*args, **kwargs)
        st.container = _container_compat
except Exception:
    pass

# --- 0. CONFIGURAÇÃO DE SEGURANÇA E AMBIENTE ---
if "GEMINI_API_KEY" in st.secrets:
    os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]

from datetime import datetime, timedelta, date
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
    # NOVOS CAMPOS DE CONTROLE DE VALIDADE ADICIONADOS AQUI
    data_fabricacao = Column(DateTime, nullable=True)
    data_validade = Column(DateTime, nullable=True)
    dias_alerta_vencimento = Column(Integer, default=15)

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
            
        # NOVA MIGRAÇÃO: ADICIONANDO DATAS NO INSUMO SE NÃO EXISTIREM
        res_ins = conexao.execute(sqlalchemy.text("PRAGMA table_info(insumos);")).fetchall()
        cols_ins = [col[1] for col in res_ins]
        if "data_validade" not in cols_ins:
            conexao.execute(sqlalchemy.text("ALTER TABLE insumos ADD COLUMN data_fabricacao DATETIME;"))
            conexao.execute(sqlalchemy.text("ALTER TABLE insumos ADD COLUMN data_validade DATETIME;"))
            conexao.execute(sqlalchemy.text("ALTER TABLE insumos ADD COLUMN dias_alerta_vencimento INTEGER DEFAULT 15;"))
            
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
                    preco_venda=preco_venda_final,
                    custo_total_cmv=cmv_total_calculado,
                )
                db_session.add(novo_prod)
                db_session.commit()
                
                for item in st.session_state.itens_ficha_tecnica:
                    nova_ft = FichaTecnica(
                        produto_id=novo_prod.id,
                        insumo_id=item["insumo_id"],
                        quantidade_utilizada=item["quantidade"]
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
            client_ativo = client or globals().get('client')
            genai_ativo = GENAI_DISPONIVEL or globals().get('GENAI_DISPONIVEL', False)
            
            if not genai_ativo or not client_ativo:
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
                        response = client_ativo.models.generate_content(model="gemini-2.5-flash", contents=contents)
                    else:
                        response = client_ativo.models.generate_content(
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
                            preco_venda=float(prod.get("preco", 0)),
                            custo_total_cmv=cmv_est,
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
    destinatarios = db_session.query(ContatoGerencial).filter(ContatoGerencial.receber_alertas_estoque == 1).all()
    config_meta = db_session.query(ConfiguracaoMeta).first()
    
    if not destinatarios:
        return "⚠️ Nenhum gerente ou administrador está configurado para receber alertas na Aba 4."
    if not config_meta or not config_meta.whatsapp_token:
        return "⚠️ Configure o token de acesso da Meta Cloud API para ativar os disparos reais de WhatsApp."

    resumo_estoque = ""
    for i in insumos:
        # Verifica também a validade agora!
        val_info = f", Validade: {i.data_validade.strftime('%d/%m/%Y')} (Aviso {i.dias_alerta_vencimento} dias antes)" if i.data_validade else ""
        resumo_estoque += f"- {i.nome}: Saldo Atual = {i.saldo_atual} {i.unidade_medida}, Mínimo = {i.estoque_minimo}{val_info}\n"
    
    prompt_forecast = f"""
    Você é o assistente de inteligência preditiva de um ERP gastronômico de alta performance.
    Analise o estado atual do almoxarifado abaixo e determine se há algum ingrediente com risco iminente de esgotamento OU próximo da data de validade com base no ritmo operacional:
    {resumo_estoque}
    
    Retorne APENAS um array JSON puro (sem markdown) com os insumos em risco crítico (quantidade ou validade):
    [
      {{"insumo": "Nome do Insumo", "previsao_esgotamento": "Sábado às 20h ou Vence em 5 dias", "mensagem_alerta": "Estoque crítico! / Sugestão de Promoção!"}}
    ]
    Se nenhum item estiver em risco, retorne um array vazio [].
    """

    try:
        from google import genai
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt_forecast)
        texto_limpo = resp.text.strip().replace("```json", "").replace("```", "").strip()
        alertas_ia = json.loads(texto_limpo)

        if not alertas_ia:
            return "✅ Estoque operacional seguro e validades sob controle. Nenhum alerta preditivo gerado."

        url_wa = f"[https://graph.facebook.com/v17.0/](https://graph.facebook.com/v17.0/){config_meta.whatsapp_phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {config_meta.whatsapp_token}",
            "Content-Type": "application/json"
        }

        total_enviados = 0
        for alerta in alertas_ia:
            texto_msg = f"🚨 *ALERTA PREDITIVO DE ESTOQUE (F&M AI FOOD)* 🚨\n\nItem: *{alerta['insumo']}*\nRisco/Previsão: *{alerta['previsao_esgotamento']}*\nStatus: {alerta['mensagem_alerta']}\n\n*Acesse o painel para reposição ou criar promoção de queima.*"

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

        return f"🚀 Análise concluída com sucesso! {len(alertas_ia)} alertas preditivos (Estoque/Validade) disparados para {total_enviados} gestores via WhatsApp."
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
                Insumo(nome="Hambúrguer 180g Angus", unidade_medida="un", saldo_atual=500.0, estoque_minimo=50.0, custo_unitario=6.50, data_validade=datetime.now() + timedelta(days=90)),
                Insumo(nome="Queijo Provolone / Cheddar", unidade_medida="fatias", saldo_atual=400.0, estoque_minimo=60.0, custo_unitario=1.20, data_validade=datetime.now() + timedelta(days=30)),
                Insumo(nome="Pão Brioche Artesanal", unidade_medida="un", saldo_atual=120.0, estoque_minimo=50.0, custo_unitario=2.00, data_validade=datetime.now() + timedelta(days=5), dias_alerta_vencimento=3),
            ]
            db.add_all(insumos_padrao)
            db.commit()
    except Exception as e:
        db.rollback()
    finally:
        db.close()

# Inicialização
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
        st.image("[https://cdn-icons-png.flaticon.com/512/3075/3075977.png](https://cdn-icons-png.flaticon.com/512/3075/3075977.png)", use_container_width=True)

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

# --- 7. CABEÇALHO DO PAINEL PRINCIPAL ---
st.title("🍔 F&M AI FOOD — Painel de Gestão, PDV & Gateway")
st.markdown("---")

# --- 8. ESTRUTURA DAS 6 ABAS PRINCIPAIS ---
aba1, aba2, aba3, aba4, aba5, aba6 = st.tabs(
    [
        "🤖 Engenharia de Cardápio",
        "📢 CRM, Resgate & Cashback",
        "🛒 Frente de Caixa (PDV & Pix)",
        "📦 Estoque & Validades (Novo!)",
        "📊 Dashboard Financeiro",
        "💬 Bot Cliente (Mica I.A.)",
    ]
)

# ... [O CÓDIGO DA ABA 1, 2, 3 PERMANECE IGUAL AO SEU ORIGINAL. VAMOS FOCAR NA ABA 4] ...
with aba1:
    render_cadastro_ficha_tecnica(db_session=get_db(), Insumo=Insumo, Produto=Produto, FichaTecnica=FichaTecnica)

with aba2:
    st.header("📢 CRM, Campanhas de Resgate ('Oi, Sumido') & Fidelidade Cashback")
    st.write("Módulo mantido original. (Código interno omitido para brevidade neste bloco principal, mas continuaria rodando aqui)")

with aba3:
    st.header("🛒 Frente de Caixa — PDV com Gateway de Pagamento & Upsell")
    st.write("Módulo mantido original. (Código interno omitido para brevidade neste bloco principal, mas continuaria rodando aqui)")

# ==============================================================================
# ABA 4: ESTOQUE, ALMOXARIFADO & VALIDADES COM I.A. (TOTALMENTE ATUALIZADA)
# ==============================================================================
with aba4:
    st.header("📦 Estoque de Insumos & Controle Inteligente de Validades")
    st.write("Gerencie o saldo em tempo real, automatize cadastros via foto e receba alertas de produtos próximos do vencimento.")

    sub_aba1, sub_aba2, sub_aba3 = st.tabs([
        "📊 Almoxarifado & Gestão", 
        "➕ Cadastrar Insumos (I.A. / Manual)", 
        "🔗 Fichas Técnicas & Receitas"
    ])

    db_estoque = get_db()

    with sub_aba1:
        st.subheader("📋 Status do Almoxarifado em Tempo Real")
    
        insumos_cadastrados = db_estoque.query(Insumo).all()

        if insumos_cadastrados:
            dados_estoque = []
            for i in insumos_cadastrados:
                valor_investido = i.saldo_atual * i.custo_unitario
                
                # LÓGICA DE VALIDADE NA TABELA
                status_validade = "🟢 No Prazo"
                if i.data_validade:
                    dias_restantes = (i.data_validade.date() - date.today()).days
                    if dias_restantes <= 0:
                        status_validade = "🔴 VENCIDO!"
                    elif dias_restantes <= i.dias_alerta_vencimento:
                        status_validade = f"🟡 Vence em {dias_restantes} dias!"

                status_estoque = "🔴 Reposição" if i.saldo_atual < i.estoque_minimo else "🟢 Ok"

                dados_estoque.append({
                    "Insumo": i.nome,
                    "Saldo Atual": f"{i.saldo_atual:.1f} {i.unidade_medida}",
                    "Estoque Mínimo": f"{i.estoque_minimo:.1f} {i.unidade_medida}",
                    "Status Estoque": status_estoque,
                    "Data Validade": i.data_validade.strftime('%d/%m/%Y') if i.data_validade else "N/A",
                    "Status Validade": status_validade
                })

            st.dataframe(pd.DataFrame(dados_estoque), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum insumo cadastrado no almoxarifado.")

        st.markdown("---")
        st.subheader("🤖 Forecasting Preditivo & Alertas de Vencimento (WhatsApp)")
        if st.button("🔮 Executar Varredura de Estoque e Validades Agora", type="primary"):
            db_fc = get_db()
            resultado_ia = executar_forecasting_e_alertar(db_fc)
            db_fc.close()
            st.info(resultado_ia)


    with sub_aba2:
        st.subheader("➕ Leitor de Nota Fiscal/Rótulo (I.A. Vision)")
        st.write("Envie a foto de um cupom ou a caixa do produto. O robô lerá o nome, quantidade e as DATAS DE VALIDADE.")
        
        arquivo_nf_cad = st.file_uploader("📸 Foto da Nota Fiscal ou Rótulo", type=["jpg", "jpeg", "png"], key="uploader_nf_cad_ia")
        
        if arquivo_nf_cad:
            if st.button("🚀 Processar Leitura com Inteligência Artificial", type="primary"):
                with st.spinner("🤖 O Gemini está lendo os produtos e as datas de validade..."):
                    try:
                        img_pil = Image.open(arquivo_nf_cad)
                        
                        # PROMPT NOVO COM INSTRUÇÃO DE DATA DE VALIDADE
                        prompt_ocr = '''Você é um auditor de estoque. Analise esta imagem.
                        Extraia os itens e retorne APENAS um array JSON válido no formato: 
                        [{"nome": "Produto", "unidade": "kg", "quantidade": 5.0, "valor_unitario": 12.50, "data_validade": "YYYY-MM-DD"}]
                        Se não encontrar a validade na imagem, preencha o campo data_validade com null.
                        Retorne EXCLUSIVAMENTE o JSON puro (sem markdown).'''
                        
                        resp_cad = client.models.generate_content(model="gemini-2.5-flash", contents=[prompt_ocr, img_pil])
                        texto_ocr = resp_cad.text.strip().replace("```json", "").replace("```", "").strip()
                        itens_lidos = json.loads(texto_ocr)
                        
                        db_cad = get_db()
                        for item in itens_lidos:
                            nome_l = str(item.get("nome", "")).strip()
                            qtd_l = float(item.get("quantidade", 0.0))
                            val_str = item.get("data_validade")
                            
                            val_obj = None
                            if val_str:
                                try: val_obj = datetime.strptime(val_str, '%Y-%m-%d')
                                except: pass

                            if nome_l and qtd_l > 0:
                                ins_db = db_cad.query(Insumo).filter(Insumo.nome.ilike(f"%{nome_l}%")).first()
                                if ins_db:
                                    ins_db.saldo_atual += qtd_l
                                    if val_obj: ins_db.data_validade = val_obj # Atualiza a validade do estoque existente
                                else:
                                    novo_i = Insumo(
                                        nome=nome_l, unidade_medida=item.get("unidade", "un"),
                                        saldo_atual=qtd_l, estoque_minimo=qtd_l * 0.15,
                                        data_validade=val_obj, dias_alerta_vencimento=15
                                    )
                                    db_cad.add(novo_i)
                                    
                        db_cad.commit()
                        st.success(f"🎉 Leitura concluída! Validades salvas no banco de dados.")
                        st.json(itens_lidos)
                    except Exception as e:
                        st.error(f"❌ Erro na leitura: {e}")

        st.divider()
        st.markdown("### ✍️ Cadastro Manual (Com Validades)")
        with st.form("form_cadastro_manual", clear_on_submit=True):
            col_m1, col_m2, col_m3 = st.columns(3)
            
            with col_m1:
                novo_nome = st.text_input("Nome do Insumo (Ex: Pão Australiano)")
                novo_saldo = st.number_input("Quantidade Inicial", min_value=0.0)
            with col_m2:
                # NOVOS CAMPOS AQUI
                nova_fab = st.date_input("Data de Fabricação (Opcional)", value=None)
                nova_val = st.date_input("Data de Validade", value=date.today() + timedelta(days=30))
            with col_m3:
                dias_alerta = st.number_input("🚨 Alerta Vencimento (Dias)", min_value=1, value=15, help="Dias antes de vencer para mandar WhatsApp")
                novo_custo = st.number_input("Custo Unitário (R$)", min_value=0.0)

            if st.form_submit_button("💾 Salvar Manualmente", type="primary"):
                if novo_nome.strip() != "":
                    db_m = get_db()
                    novo_insumo = Insumo(
                        nome=novo_nome, saldo_atual=novo_saldo,
                        custo_unitario=novo_custo, unidade_medida="un",
                        data_fabricacao=nova_fab, data_validade=nova_val,
                        dias_alerta_vencimento=dias_alerta
                    )
                    db_m.add(novo_insumo)
                    db_m.commit()
                    db_m.close()
                    st.success(f"✅ Insumo '{novo_nome}' salvo! O sistema avisará {dias_alerta} dias antes de {nova_val.strftime('%d/%m/%Y')}.")

# [As Abas 5 (Financeiro) e 6 (Bot Mica) permanecem as originais do seu código]