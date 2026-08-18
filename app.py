# ruff: noqa: E402
import os
from typing import Any
from uuid import uuid4

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError
from core.runtime import (
    build_engine as build_runtime_engine,
    load_runtime_settings,
)
from infra.streamlit_app.auth_ui import (
    render_identity_sidebar,
    require_authentication,
)
from infra.seguranca.session_guard import build_session_factory
from migrations.runner import assert_schema_current, run_migrations

# Patch: ensure compatibility with custom keyword args used across the app
try:
    if not hasattr(st, "_orig_container"):
        setattr(st, "_orig_container", st.container)

        def _container_compat(*args: Any, **kwargs: Any) -> Any:
            kwargs.pop("border", None)
            kwargs.pop("bordered", None)
            return getattr(st, "_orig_container")(*args, **kwargs)

        st.container = _container_compat
except Exception:
    pass

# --- 0. CONFIGURAÇÃO DE SEGURANÇA E AMBIENTE ---
try:
    if "GEMINI_API_KEY" in st.secrets:
        os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]
except StreamlitSecretNotFoundError:
    pass

# Compatibilidade com teste estático: from gemini_config import generate_content, upload_file
from gemini_config import (
    generate_content as real_generate_content,
    upload_file as real_upload_file,
)
from test_mode import (
    build_runtime,
    is_test_mode,
    mock_generate_content,
    mock_upload_file,
    mock_whatsapp_send,
    reset_database,
    seed_database,
)

generate_content = mock_generate_content if is_test_mode() else real_generate_content
upload_file = mock_upload_file if is_test_mode() else real_upload_file
from pdv_utils import (
    CLIENTE_BALCAO_ID,
    FORMAS_PAGAMENTO_PERMITIDAS,
    calcular_troco,
    deve_exibir_troco,
    deve_exibir_valor_recebido,
    formatar_moeda_br,
    formatar_opcao_cliente_pdv,
    indice_cliente_pdv,
    aplicar_reset_pendente_pdv,
    consumir_flash_sucesso_pdv,
    marcar_reset_pdv_apos_sucesso,
    montar_linha_total_pdv,
    montar_mensagem_sucesso_pdv,
    montar_payload_pix_simulado,
    normalizar_cliente_id_pdv,
    preparar_cliente_id_pdv,
    montar_url_qrcode_pix,
    pagamento_dinheiro_suficiente,
    validar_finalizacao_pdv,
    valor_faltante_pagamento,
)

from datetime import datetime, timedelta, date
import json
from dotenv import load_dotenv
import pandas as pd  # type: ignore[import-untyped]
from PIL import Image
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.exc import SQLAlchemyError
import io

from core.pdv.adaptadores_sqlalchemy import (
    LegacyPDVSQLAlchemyAdapter,
    RegistroFalhaShadowSQLAlchemy,
    RepositorioPDVSQLAlchemy,
    SQLAlchemyPDVUnitOfWork,
)
from core.pdv.configuracao import carregar_rollout_ambiente
from core.pdv.contexto import contexto_caixa_pdv
from core.pdv.executores import (
    ExecutorAutoritativoSQLAlchemy,
    EscritorShadowSQLAlchemy,
    id_deterministico,
)
from core.pdv.modelos import EntradaPDV, dinheiro_legado
from core.pdv.roteamento import ModoPDV, decidir_modo
from core.pdv.servicos import finalizar_venda_pdv
from core.central_pedidos.flags import order_center_v1_enabled
from core.central_pedidos.ui_streamlit import render_central_pedidos
from core.kds.flags import kds_v1_enabled
from core.kds.ui_streamlit import render_kds
from core.salao.flags import salao_v1_enabled
from core.salao.ui_streamlit import render_salao
from core.assistente_atendimento.modelos import ConfiguracaoIdentidadeAssistente
from core.assistente_atendimento.ui_streamlit import render_assistente_atendimento_v1
from infra.gerente_ia.persistencia_sqlalchemy import (
    RepositorioIdentidadeAssistenteSQLAlchemy,
)

try:
    import pypdf
except ImportError:
    pass

# --- 1. CONFIGURAÇÃO DA PÁGINA E ESTILIZAÇÃO ---
st.set_page_config(
    page_title="F&M AI FOOD — ERP Gastronômico & PDV Inteligente",
    page_icon="🍔",
    layout="wide",
    initial_sidebar_state="expanded",
)

if is_test_mode():
    st.session_state["_fm_ai_e2e_run"] = (
        int(st.session_state.get("_fm_ai_e2e_run", 0)) + 1
    )

# --- 2. BANCO DE DADOS E CONFIGURAÇÃO ORM ---
load_dotenv()
TEST_RUNTIME = build_runtime()
os.makedirs(TEST_RUNTIME.files_dir, exist_ok=True)

RUNTIME_SETTINGS = load_runtime_settings(
    test_database_url=TEST_RUNTIME.database_url if is_test_mode() else None
)
DATABASE_URL = RUNTIME_SETTINGS.database_url
engine = build_runtime_engine(RUNTIME_SETTINGS)
SessionLocal = build_session_factory(
    engine=engine, commercial=RUNTIME_SETTINGS.commercial
)
Base = declarative_base()


# --- 3. MODELOS DAS TABELAS DO BANCO DE DADOS ---
class Usuario(Base):  # type: ignore[misc, valid-type]
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    senha_hash = Column(String)


class Cliente(Base):  # type: ignore[misc, valid-type]
    __tablename__ = "clientes"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, index=True)
    whatsapp = Column(String, unique=True, index=True)
    ultima_compra = Column(DateTime, default=datetime.now)
    total_gasto = Column(Float, default=0.0)
    saldo_cashback = Column(Float, default=0.0)
    status = Column(String, default="Ativo")


class Produto(Base):  # type: ignore[misc, valid-type]
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


class Insumo(Base):  # type: ignore[misc, valid-type]
    __tablename__ = "insumos"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, unique=True, index=True)
    unidade_medida = Column(String, default="un")
    saldo_atual = Column(Float, default=0.0)
    estoque_minimo = Column(Float, default=0.0)
    custo_unitario = Column(Float, default=0.0)
    data_fabricacao = Column(DateTime, nullable=True)
    data_validade = Column(DateTime, nullable=True)
    dias_alerta_vencimento = Column(Integer, default=15)


class FichaTecnica(Base):  # type: ignore[misc, valid-type]
    __tablename__ = "fichas_tecnicas"
    id = Column(Integer, primary_key=True, index=True)
    produto_id = Column(Integer, ForeignKey("produtos.id"), nullable=False)
    insumo_id = Column(Integer, ForeignKey("insumos.id"), nullable=False)
    quantidade_utilizada = Column(Float, nullable=False, default=0.0)

    produto = relationship("Produto", backref="fichas_tecnicas")
    insumo = relationship("Insumo", backref="fichas_tecnicas")


class Venda(Base):  # type: ignore[misc, valid-type]
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


class GatewayConfig(Base):  # type: ignore[misc, valid-type]
    __tablename__ = "gateway_config"
    id = Column(Integer, primary_key=True)
    gateway_provider = Column(String(50), default="Mercado Pago")
    gateway_api_key = Column(String(255), nullable=True)
    gateway_pix_key = Column(String(100), nullable=True)
    ambiente = Column(String(20), default="Sandbox")


class ConfiguracaoMeta(Base):  # type: ignore[misc, valid-type]
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


class ContatoGerencial(Base):  # type: ignore[misc, valid-type]
    __tablename__ = "contatos_gerenciais"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String)
    whatsapp = Column(String, unique=True, index=True)
    cargo = Column(String)
    receber_alertas_estoque = Column(Integer, default=1)


# Desenvolvimento/teste podem criar schema local; runtime comercial exige migration.
try:
    if is_test_mode() and os.getenv("FM_AI_TEST_RESET_ON_START") == "1":
        reset_database(engine, Base)
    elif RUNTIME_SETTINGS.commercial:
        assert_schema_current(engine)
    else:
        Base.metadata.create_all(bind=engine, checkfirst=True)
except Exception as e:
    st.error(f"❌ Erro ao inicializar o banco de dados: {e}")
    if RUNTIME_SETTINGS.commercial:
        st.stop()

# Schemas V1 nunca sao criados automaticamente fora do banco temporario E2E.
_pdv_rollout = carregar_rollout_ambiente()
if is_test_mode() and _pdv_rollout.modo is not ModoPDV.LEGACY:
    from migrations.pdv_v1 import upgrade as upgrade_pdv_v1

    if _pdv_rollout.modo is ModoPDV.AUTHORITATIVE_CANARY:
        # O E2E autoritativo usa a mesma trilha canônica do runtime comercial:
        # Pedido, Pagamento, Estoque, Event Bus e Auditoria.
        run_migrations(engine)
    else:
        from migrations.orders_v1 import upgrade as upgrade_orders_v1

        upgrade_orders_v1(engine)
    upgrade_pdv_v1(engine)


CURRENT_IDENTITY = require_authentication(
    session_factory=SessionLocal,
    settings=RUNTIME_SETTINGS,
)


def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()


def recalcular_cmv_geral(db_session):
    try:
        produtos = db_session.query(Produto).all()
        for prod in produtos:
            fichas = (
                db_session.query(FichaTecnica)
                .filter(FichaTecnica.produto_id == prod.id)
                .all()
            )
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
    except Exception:
        db_session.rollback()


def render_cadastro_ficha_tecnica(
    db_session, Insumo, Produto, FichaTecnica, client=None, GENAI_DISPONIVEL=False
):
    st.subheader("👨‍🍳 Engenharia de Cardápio & Ficha Técnica (Pratos do Menu)")
    st.caption(
        "Cadastre os pratos do cardápio utilizando exclusivamente os insumos já cadastrados e validados no Almoxarifado (Aba 4)."
    )

    modo = st.radio(
        "Escolha como deseja cadastrar o prato:",
        [
            "✍️ Cadastro Manual de Prato",
            "🤖 Importação Automática de Cardápio via IA (Foto/PDF/Texto)",
        ],
        horizontal=True,
    )

    st.markdown("---")

    if modo == "✍️ Cadastro Manual de Prato":
        col_nome, col_cat = st.columns([2, 1])
        with col_nome:
            nome_produto = st.text_input(
                "Nome do Prato / Lanche", placeholder="Ex: Mica Royal Truffle Bacon"
            )
        with col_cat:
            categoria = st.selectbox(
                "Categoria no Cardápio",
                ["Hambúrgueres", "Porções", "Bebidas", "Sobremesas"],
            )

        st.write("### 🥗 Composição da Ficha Técnica (Puxando do Almoxarifado)")
        insumos_disponiveis = db_session.query(Insumo).all()

        if not insumos_disponiveis:
            st.warning(
                "⚠️ Nenhum insumo encontrado no Almoxarifado. Cadastre os insumos e validades na Aba 4 primeiro!"
            )
            return

        if "itens_ficha_tecnica" not in st.session_state:
            st.session_state.itens_ficha_tecnica = []

        c1, c2, c3 = st.columns([3, 2, 1])
        with c1:
            insumo_selecionado = st.selectbox(
                "Selecione o Insumo do Almoxarifado",
                options=insumos_disponiveis,
                format_func=lambda x: (
                    f"{x.nome} (Custo: R$ {x.custo_unitario:.2f} / {x.unidade_medida} | Validade: {x.data_validade.strftime('%d/%m/%Y') if x.data_validade else 'N/A'})"
                ),
                key="sel_insumo",
            )
        with c2:
            label_qtd = (
                "Quantidade em GRAMAS (g)"
                if insumo_selecionado.unidade_medida == "kg"
                else f"Quantidade ({insumo_selecionado.unidade_medida})"
            )
            qtd_usada = st.number_input(
                label_qtd, min_value=0.1, value=100.0, step=10.0, key="num_qtd"
            )

        with c3:
            st.write(" ")
            st.write(" ")
            if st.button("➕ Adicionar à Receita", use_container_width=True):
                custo_item = (
                    (qtd_usada / 1000.0) * insumo_selecionado.custo_unitario
                    if insumo_selecionado.unidade_medida == "kg"
                    else qtd_usada * insumo_selecionado.custo_unitario
                )
                st.session_state.itens_ficha_tecnica.append(
                    {
                        "insumo_id": insumo_selecionado.id,
                        "nome": insumo_selecionado.nome,
                        "quantidade": qtd_usada,
                        "unidade": "g"
                        if insumo_selecionado.unidade_medida == "kg"
                        else insumo_selecionado.unidade_medida,
                        "custo_calculado": custo_item,
                    }
                )
                st.rerun()

        cmv_total_calculado = 0.0
        if st.session_state.itens_ficha_tecnica:
            st.write("#### 📜 Receita Montada para este Prato:")
            tabela_dados = []
            for item in st.session_state.itens_ficha_tecnica:
                cmv_total_calculado += item["custo_calculado"]
                tabela_dados.append(
                    {
                        "Insumo": item["nome"],
                        "Qtd na Receita": f"{item['quantidade']} {item['unidade']}",
                        "Custo Residual (R$)": f"R$ {item['custo_calculado']:.2f}",
                    }
                )
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
            margem_pretendida = st.number_input(
                "Margem Desejada (%)",
                min_value=5.0,
                max_value=300.0,
                value=60.0,
                step=5.0,
            )

        preco_sugerido = (
            (cmv_total_calculado / (1 - (margem_pretendida / 100.0)))
            if margem_pretendida < 100
            else (cmv_total_calculado * (1 + (margem_pretendida / 100.0)))
        )

        with col_preco:
            preco_venda_final = st.number_input(
                "Preço de Venda Final (R$)",
                min_value=0.0,
                value=float(round(preco_sugerido, 2)),
                step=0.50,
            )

        with col_lucro:
            margem_real = (
                ((preco_venda_final - cmv_total_calculado) / preco_venda_final * 100)
                if preco_venda_final > 0
                else 0
            )
            st.metric(
                "Lucro Bruto / Prato",
                f"R$ {(preco_venda_final - cmv_total_calculado):.2f}",
                delta=f"{margem_real:.1f}% Margem Real",
            )

        if st.button("💾 Salvar Prato no Cardápio & Ficha Técnica", type="primary"):
            if not nome_produto:
                st.error("❌ Digite o nome do prato.")
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
                        quantidade_utilizada=item["quantidade"],
                    )
                    db_session.add(nova_ft)
                db_session.commit()

                st.success(
                    f"✅ Prato **{nome_produto}** cadastrado com sucesso no Cardápio!"
                )
                st.session_state.itens_ficha_tecnica = []
                st.rerun()

    else:
        st.write(
            "### 📄 Importação Automática de Cardápio Real (Foto, PDF ou Colar Texto) via Gemini"
        )
        st.caption(
            "Carregue o arquivo com seu cardápio oficial que a IA extrairá todos os pratos e cadastrará no menu."
        )

        opcao_fonte = st.radio(
            "Origem do arquivo:",
            ["📁 Upload de Arquivo (Imagem/PDF)", "📝 Colar Texto do Cardápio"],
            horizontal=True,
        )

        texto_cardapio = ""
        arquivo_upload = None

        if opcao_fonte == "📁 Upload de Arquivo (Imagem/PDF)":
            arquivo_upload = st.file_uploader(
                "Arraste a foto do cardápio ou PDF aqui",
                type=["png", "jpg", "jpeg", "pdf"],
            )
        else:
            texto_cardapio = st.text_area(
                "Cole aqui o texto do seu cardápio com nomes e preços:", height=150
            )

        if st.button("🚀 Processar Cardápio com IA", type="primary"):
            genai_ativo = GENAI_DISPONIVEL or globals().get("GENAI_DISPONIVEL", False)

            if not genai_ativo:
                st.error(
                    "❌ Integração com Google GenAI/Gemini não configurada no servidor."
                )
                return

            if not arquivo_upload and not texto_cardapio.strip():
                st.error("❌ Por favor, envie um arquivo ou cole o texto do cardápio.")
                return

            with st.spinner("🤖 O Gemini está analisando o cardápio real..."):
                try:
                    prompt = """
                    Você é um especialista em ERP gastronômico. Analise o cardápio fornecido e extraia todos os produtos/pratos cadastráveis.
                    Retorne EXATAMENTE um JSON no seguinte formato (sem formatação markdown ```json, apenas a string json pura):
                    [
                        {
                            "nome": "Nome do Prato",
                            "categoria": "Hambúrgueres",
                            "preco": 39.90,
                            "ingredientes": "Descrição ou ingredientes"
                        }
                    ]
                    """

                    if arquivo_upload:
                        bytes_data = arquivo_upload.getvalue()
                        mime = arquivo_upload.type
                        try:
                            from google.genai import types

                            part_arquivo = types.Part.from_bytes(
                                data=bytes_data, mime_type=mime
                            )
                            contents = [part_arquivo, prompt]
                            response = generate_content(contents=contents)
                        except Exception as api_err:
                            if mime == "application/pdf":
                                st.warning(
                                    "⚠️ API rejeitou o arquivo direto. Extraindo texto via PyPDF em contingência..."
                                )
                                leitor_pdf = pypdf.PdfReader(io.BytesIO(bytes_data))
                                texto_extraido = ""
                                for pagina in leitor_pdf.pages:
                                    texto_extraido += pagina.extract_text() + "\n"

                                response = generate_content(
                                    contents=f"{prompt}\n\nTexto extraído do PDF:\n{texto_extraido}"
                                )
                            else:
                                raise api_err
                    else:
                        response = generate_content(
                            contents=f"{prompt}\n\n{texto_cardapio}"
                        )

                    texto_limpo = (
                        response.text.strip().replace("```json", "").replace("```", "")
                    )
                    produtos_extraidos = json.loads(texto_limpo)

                    qtd_cadastrados = 0
                    for prod in produtos_extraidos:
                        cmv_est = round(float(prod.get("preco", 0)) * 0.32, 2)
                        novo_prod = Produto(
                            nome=prod.get("nome"),
                            categoria=prod.get("categoria", "Geral"),
                            preco_venda=float(prod.get("preco", 0)),
                            custo_total_cmv=cmv_est,
                            descricao_bruta=prod.get("ingredientes", ""),
                        )
                        db_session.add(novo_prod)
                        qtd_cadastrados += 1

                    db_session.commit()
                    st.success(
                        f"🎉 Sucesso! **{qtd_cadastrados} pratos** foram extraídos pelo Gemini e salvos diretamente no cardápio!"
                    )

                except Exception as e:
                    st.error(f"❌ Erro ao processar cardápio com IA: {e}")


def executar_forecasting_e_alertar(db_session):
    insumos = db_session.query(Insumo).all()
    destinatarios = (
        db_session.query(ContatoGerencial)
        .filter(ContatoGerencial.receber_alertas_estoque == 1)
        .all()
    )

    if not destinatarios:
        return "⚠️ Nenhum gerente ou administrador está configurado para receber alertas na Aba 4."

    resumo_estoque = ""
    for i in insumos:
        val_info = (
            f", Validade: {i.data_validade.strftime('%d/%m/%Y')} (Aviso {i.dias_alerta_vencimento} dias antes)"
            if i.data_validade
            else ""
        )
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
        resp = generate_content(contents=prompt_forecast)
        texto_limpo = (
            resp.text.strip().replace("```json", "").replace("```", "").strip()
        )
        alertas_ia = json.loads(texto_limpo)

        if not alertas_ia:
            return "✅ Estoque operacional seguro e validades sob controle. Nenhum alerta preditivo gerado."

        total_enviados = 0
        for alerta in alertas_ia:
            texto_msg = f"🚨 *ALERTA PREDITIVO DE ESTOQUE (F&M AI FOOD)* 🚨\n\nItem: *{alerta['insumo']}*\nRisco/Previsão: *{alerta['previsao_esgotamento']}*\nStatus: {alerta['mensagem_alerta']}\n\n*Acesse o painel para reposição ou criar promoção de queima.*"

            for contato in destinatarios:
                if is_test_mode():
                    envio_mock = mock_whatsapp_send(contato.whatsapp, texto_msg)
                    if envio_mock["ok"]:
                        total_enviados += 1
                else:
                    mensagem_id = _enviar_whatsapp_control_plane(
                        destinatario=contato.whatsapp,
                        texto=texto_msg,
                        idempotency_key=(
                            f"estoque-{contato.id}-{date.today().isoformat()}"
                        ),
                    )
                    if mensagem_id:
                        total_enviados += 1

        return f"🚀 Análise concluída com sucesso! {len(alertas_ia)} alertas preditivos (Estoque/Validade) disparados para {total_enviados} gestores via WhatsApp."
    except Exception:
        return (
            "❌ Não foi possível concluir o forecasting ou enviar os alertas. "
            "Verifique as integrações Gemini e Meta/WhatsApp desta unidade."
        )


def popular_dados_iniciais():
    db = SessionLocal()
    try:
        if is_test_mode() and db.query(ConfiguracaoMeta).count() == 0:
            db.add(ConfiguracaoMeta(gateway_provider="Mercado Pago"))
            db.commit()

        if db.query(Insumo).count() == 0:
            insumos_padrao = [
                Insumo(
                    nome="Hambúrguer 180g Angus",
                    unidade_medida="un",
                    saldo_atual=500.0,
                    estoque_minimo=50.0,
                    custo_unitario=6.50,
                    data_validade=datetime.now() + timedelta(days=90),
                ),
                Insumo(
                    nome="Queijo Provolone / Cheddar",
                    unidade_medida="fatias",
                    saldo_atual=400.0,
                    estoque_minimo=60.0,
                    custo_unitario=1.20,
                    data_validade=datetime.now() + timedelta(days=30),
                ),
                Insumo(
                    nome="Pão Brioche Artesanal",
                    unidade_medida="un",
                    saldo_atual=120.0,
                    estoque_minimo=50.0,
                    custo_unitario=2.00,
                    data_validade=datetime.now() + timedelta(days=5),
                    dias_alerta_vencimento=3,
                ),
            ]
            db.add_all(insumos_padrao)
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


# Inicialização
popular_dados_iniciais()
seed_database(
    SessionLocal,
    {
        "Usuario": Usuario,
        "Cliente": Cliente,
        "Produto": Produto,
        "Insumo": Insumo,
        "FichaTecnica": FichaTecnica,
        "Venda": Venda,
        "ConfiguracaoMeta": ConfiguracaoMeta,
        "ContatoGerencial": ContatoGerencial,
    },
)

# Verificação da Inteligência Artificial Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


def _gemini_disponivel_no_runtime() -> bool:
    if is_test_mode():
        return True

    if not RUNTIME_SETTINGS.commercial:
        return bool(GEMINI_API_KEY)

    db = SessionLocal()
    try:
        from infra.integracoes import FabricaAdaptersExternos
        from infra.seguranca.segredos_sqlalchemy import (
            EncryptedSQLAlchemySecretStore,
        )

        vault = EncryptedSQLAlchemySecretStore(db)
        FabricaAdaptersExternos(
            session=db,
            secret_store=vault,
        ).gemini(
            contexto=CURRENT_IDENTITY.contexto(
                origem="app.gemini_availability"
            ),
            configuracao_id="ia.generativa--gemini",
        )
        return True
    except Exception:
        return False
    finally:
        db.close()


GENAI_DISPONIVEL = _gemini_disponivel_no_runtime()


def _enviar_whatsapp_control_plane(
    *,
    destinatario: str,
    texto: str,
    idempotency_key: str,
) -> str:
    db = SessionLocal()
    try:
        from infra.integracoes import FabricaAdaptersExternos
        from infra.seguranca.segredos_sqlalchemy import (
            EncryptedSQLAlchemySecretStore,
        )

        vault = EncryptedSQLAlchemySecretStore(db)
        adapter = FabricaAdaptersExternos(
            session=db,
            secret_store=vault,
        ).meta(
            contexto=CURRENT_IDENTITY.contexto(
                origem="app.whatsapp_runtime"
            ),
            configuracao_id="mensageria.whatsapp--meta",
        )
        return adapter.enviar_whatsapp(
            destinatario=destinatario,
            texto=texto,
            idempotency_key=idempotency_key,
        )
    finally:
        db.close()


# --- 6. BARRA LATERAL (SIDEBAR CORPORATIVA) ---
with st.sidebar:
    if os.path.exists("logo.png"):
        st.image("logo.png", use_container_width=True)
    else:
        st.image(
            "[https://cdn-icons-png.flaticon.com/512/3075/3075977.png](https://cdn-icons-png.flaticon.com/512/3075/3075977.png)",
            use_container_width=True,
        )

    st.title("F&M AI FOOD")
    st.caption("Professional Gastronomy ERP & AI")
    st.markdown("---")
    st.subheader("🔐 Acesso Corporativo")
    render_identity_sidebar(CURRENT_IDENTITY, RUNTIME_SETTINGS)

    if GENAI_DISPONIVEL:
        if is_test_mode():
            st.markdown(
                "🧪 **Modo de teste isolado ativo — banco temporário e mocks externos**"
            )
        else:
            st.markdown("🟢 **Google GenAI Ativo (modelo validado pelo gateway)**")
    else:
        st.markdown("⚠️ **Modo Offline / Sem Chave API**")

# --- 7. CABEÇALHO DO PAINEL PRINCIPAL ---
st.title("🍔 F&M AI FOOD — Painel de Gestão, PDV & Gateway")
st.markdown("---")

# --- 8. ESTRUTURA DAS 6 ABAS PRINCIPAIS ---
_nomes_abas = [
    "🤖 Engenharia de Cardápio",
    "📢 CRM, Resgate & Cashback",
    "🛒 Frente de Caixa (PDV & Pix)",
    "📦 Estoque & Validades (Novo!)",
    "📊 Dashboard Financeiro",
    "💬 Assistente de Atendimento",
]
if order_center_v1_enabled():
    _nomes_abas.append("\U0001F4CB Central de Pedidos")
if kds_v1_enabled():
    _nomes_abas.append("\U0001F373 KDS por Setor")
if salao_v1_enabled():
    _nomes_abas.append("🪑 Mesas e Comandas")

_abas = st.tabs(_nomes_abas)
aba1, aba2, aba3, aba4, aba5, aba6 = _abas[:6]

_indice_extra = 6

aba_central = None
if order_center_v1_enabled():
    aba_central = _abas[_indice_extra]
    _indice_extra += 1

aba_kds = None
if kds_v1_enabled():
    aba_kds = _abas[_indice_extra]
    _indice_extra += 1

aba_salao = None
if salao_v1_enabled():
    aba_salao = _abas[_indice_extra]

if aba_central is not None:
    with aba_central:
        render_central_pedidos(
            engine=engine,
            session_factory=SessionLocal,
        )

if aba_kds is not None:
    with aba_kds:
        render_kds(
            engine=engine,
            session_factory=SessionLocal,
        )

if aba_salao is not None:
    with aba_salao:
        render_salao(
            engine=engine,
            session_factory=SessionLocal,
        )

# ==============================================================================
# ABA 1: ENGENHARIA DE CARD?PIO
# ==============================================================================
with aba1:
    render_cadastro_ficha_tecnica(
        db_session=get_db(),
        Insumo=Insumo,
        Produto=Produto,
        FichaTecnica=FichaTecnica,
        GENAI_DISPONIVEL=GENAI_DISPONIVEL,
    )

# ==============================================================================
# ABA 2: CRM E WHATSAPP
# ==============================================================================
with aba2:
    st.header("📢 CRM, Campanhas de Resgate ('Oi, Sumido') & Fidelidade Cashback")
    st.write(
        "Engaje clientes inativos com cupons persuasivos gerados pela I.A. e administre saldos de cashback da sua base de consumidores."
    )

    sub_crm1, sub_crm2 = st.tabs(
        [
            "🔄 Recuperação de Clientes Inativos (Upsell)",
            "💳 Gestão de Fidelidade & Cashback",
        ]
    )

    db_crm_base = get_db()

    with sub_crm1:
        st.subheader("🤖 Automação de Resgate com Inteligência Artificial")
        st.write(
            "A plataforma identifica clientes sem compras há mais de 15 dias e sugere abordagens personalizadas com cupons de desconto para disparar no WhatsApp."
        )

        data_corte_inativos = datetime.now() - timedelta(days=15)
        clientes_inativos = (
            db_crm_base.query(Cliente)
            .filter(
                (Cliente.ultima_compra <= data_corte_inativos)
                | (Cliente.status == "Inativo")
            )
            .all()
        )

        st.markdown(
            f"### 👥 Clientes em risco de churn identificados: **{len(clientes_inativos)}**"
        )

        if clientes_inativos:
            for cli in clientes_inativos:
                with st.container():
                    c_col1, c_col2, c_col3 = st.columns([2, 2, 3])
                    with c_col1:
                        st.markdown(f"**👤 {cli.nome}**")
                        st.write(f"📱 WhatsApp: `{cli.whatsapp}`")
                        st.write(f"📌 Status: **{cli.status}**")

                    with c_col2:
                        st.write(
                            f"🕒 Última compra: **{cli.ultima_compra.strftime('%d/%m/%Y')}**"
                        )
                        st.write(f"💰 Total acumulado: **R$ {cli.total_gasto:.2f}**")
                        st.write(
                            f"💳 Cashback disponível: **R$ {cli.saldo_cashback:.2f}**"
                        )

                    msg_resgate_padrao = f"Olá {cli.nome}! Sentimos muito a sua falta aqui no Mica Burguer. Preparamos um cupom exclusivo de 15% de desconto para você pedir seu hambúrguer favorito hoje!"

                    if GENAI_DISPONIVEL:
                        try:
                            prompt_resg = f"Escreva uma mensagem curta, carinhosa e muito persuasiva de WhatsApp para resgatar o cliente '{cli.nome}', que não faz pedidos em nossa hamburgueria gourmet há semanas. Ofereça um cupom especial de 15% de desconto (CUPOM: VOLTAMICA15). Sem clichês em excesso."
                            resp_resg = generate_content(contents=prompt_resg)
                            if resp_resg and resp_resg.text:
                                msg_resgate_padrao = resp_resg.text.strip()
                        except Exception:
                            pass

                    with c_col3:
                        st.markdown("🤖 **Sugestão de Abordagem I.A.:**")
                        st.info(f'"{msg_resgate_padrao}"')
                        if st.button(
                            f"🚀 Disparar Campanha WhatsApp para {cli.nome}",
                            key=f"btn_zap_resgate_{cli.id}",
                            type="primary",
                        ):
                            try:
                                if is_test_mode():
                                    envio = mock_whatsapp_send(
                                        cli.whatsapp,
                                        msg_resgate_padrao,
                                    )
                                    if not envio.get("ok"):
                                        raise RuntimeError("envio_teste_falhou")
                                else:
                                    mensagem_id = _enviar_whatsapp_control_plane(
                                        destinatario=cli.whatsapp,
                                        texto=msg_resgate_padrao,
                                        idempotency_key=(
                                            f"crm-resgate-{cli.id}-"
                                            f"{date.today().isoformat()}"
                                        ),
                                    )
                                    if not mensagem_id:
                                        raise RuntimeError("envio_sem_confirmacao")

                                st.success(
                                    f"✅ Campanha de resgate enviada com sucesso para o número {cli.whatsapp}!"
                                )
                            except Exception:
                                st.error(
                                    "Não foi possível enviar a campanha pelo WhatsApp. "
                                    "Verifique se a integração Meta/WhatsApp desta unidade "
                                    "está configurada, habilitada e homologada."
                                )
        else:
            st.success(
                "🎉 Excelente notícia! Nenhum cliente inativo há mais de 15 dias foi identificado no momento. Sua base está altamente engajada!"
            )

    with sub_crm2:
        st.subheader("💳 Relatório Geral de Saldos de Cashback")
        st.write(
            "Acompanhe o saldo que cada cliente acumulou para utilizar como desconto em pedidos futuros na loja ou no delivery."
        )

        todos_clientes = db_crm_base.query(Cliente).all()
        if todos_clientes:
            dados_cb = []
            for cl in todos_clientes:
                dados_cb.append(
                    {
                        "ID": cl.id,
                        "Nome do Cliente": cl.nome,
                        "WhatsApp": cl.whatsapp,
                        "Total Gasto na Loja": f"R$ {cl.total_gasto:.2f}",
                        "Saldo Cashback": f"R$ {cl.saldo_cashback:.2f}",
                        "Status": cl.status,
                    }
                )
            st.dataframe(
                pd.DataFrame(dados_cb), use_container_width=True, hide_index=True
            )
        else:
            st.info("Nenhum cliente cadastrado no banco de dados até o momento.")

        if is_test_mode():
            st.markdown("---")
            with st.form("form_e2e_cliente_teste", clear_on_submit=True):
                st.markdown("### 🧪 Cadastro seguro de cliente para testes E2E")
                nome_cliente_e2e = st.text_input("Nome do Cliente E2E")
                whatsapp_cliente_e2e = st.text_input("WhatsApp do Cliente E2E")
                if st.form_submit_button("💾 Salvar Cliente E2E", type="secondary"):
                    if not nome_cliente_e2e.strip() or not whatsapp_cliente_e2e.strip():
                        st.error("Nome e WhatsApp do cliente E2E são obrigatórios.")
                    else:
                        db_cli_e2e = get_db()
                        try:
                            existente = (
                                db_cli_e2e.query(Cliente)
                                .filter(
                                    Cliente.whatsapp == whatsapp_cliente_e2e.strip()
                                )
                                .first()
                            )
                            if existente:
                                st.error("Cliente E2E já cadastrado com este WhatsApp.")
                            else:
                                db_cli_e2e.add(
                                    Cliente(
                                        nome=nome_cliente_e2e.strip(),
                                        whatsapp=whatsapp_cliente_e2e.strip(),
                                        status="Ativo",
                                        saldo_cashback=0.0,
                                    )
                                )
                                db_cli_e2e.commit()
                                st.success("Cliente E2E salvo com sucesso.")
                                st.rerun()
                        except Exception as exc:
                            db_cli_e2e.rollback()
                            st.error(f"Erro ao salvar cliente E2E: {exc}")
                        finally:
                            db_cli_e2e.close()

        st.markdown("---")
        with st.form("form_ajustar_cashback"):
            st.markdown("### ➕ Creditar Saldo de Cashback Manualmente")
            st.write(
                "Utilize esta função para premiar clientes vips ou conceder bônus promocionais."
            )
            col_cb1, col_cb2 = st.columns(2)
            with col_cb1:
                cli_escolhido = st.selectbox(
                    "Selecione o Cliente para o Crédito",
                    todos_clientes,
                    format_func=lambda x: (
                        f"{x.nome} (Saldo Atual: {formatar_moeda_br(x.saldo_cashback)})"
                    ),
                )
            with col_cb2:
                valor_add_cb = st.number_input(
                    "Valor do Crédito a Adicionar (R$)",
                    min_value=0.0,
                    value=10.0,
                    step=5.0,
                    format="%.2f",
                )

            btn_add_cb = st.form_submit_button(
                "💰 Confirmar Crédito de Cashback", type="primary"
            )
            if btn_add_cb and cli_escolhido:
                db_cb = get_db()
                try:
                    c_up = (
                        db_cb.query(Cliente)
                        .filter(Cliente.id == cli_escolhido.id)
                        .first()
                    )
                    if c_up:
                        c_up.saldo_cashback += valor_add_cb
                        db_cb.commit()
                        st.success(
                            f"✅ Crédito de {formatar_moeda_br(valor_add_cb)} adicionado com sucesso ao saldo de **{c_up.nome}**!"
                        )
                        st.rerun()
                except Exception as e:
                    db_cb.rollback()
                    st.error(f"Erro ao creditar cashback: {e}")
                finally:
                    db_cb.close()

    db_crm_base.close()

# ==============================================================================
# ABA 3: FRENTE DE CAIXA
# ==============================================================================
with aba3:
    st.header("🛒 Frente de Caixa — PDV com Gateway de Pagamento & Upsell")
    st.write(
        "Registre vendas de balcão ou delivery, aplique saldos de cashback, gere QR Code Pix instantâneo e dê baixa automática no estoque."
    )

    aplicar_reset_pendente_pdv(st.session_state)
    flash_sucesso_pdv = consumir_flash_sucesso_pdv(st.session_state)
    if flash_sucesso_pdv:
        st.success(flash_sucesso_pdv)

    db_pdv = get_db()
    lista_pratos_pdv = db_pdv.query(Produto).all()
    lista_clientes_pdv = db_pdv.query(Cliente).all()
    config_gtw = (
        db_pdv.query(ConfiguracaoMeta).first()
        if is_test_mode()
        else None
    )

    # A configuração legada só existe para E2E isolado. Nunca promove o PDV
    # comercial nem autoriza uso das colunas de segredo em texto puro.
    modo_producao_ativo = is_test_mode() and bool(
        config_gtw and config_gtw.gateway_api_key and config_gtw.gateway_pix_key
    )

    if modo_producao_ativo:
        st.success(
            f"🟢 **MODO PRODUÇÃO ATIVO:** O Gateway **{config_gtw.gateway_provider}** está vinculado à conta bancária PJ. O sistema gera cobranças reais via API e aguarda o Webhook de pagamento!"
        )
    else:
        st.warning(
            "🟡 **GATEWAY LEGADO DESATIVADO:** nenhuma credencial armazenada nas "
            "tabelas legadas autoriza pagamentos reais. Use a configuração segura "
            "por cliente e conclua a homologação do provedor."
        )

    with st.expander(
        "⚙️ Configurações do Gateway Bancário (Administrador — Virada de Chave PJ)"
    ):
        st.markdown("### Conectar Conta Bancária da Empresa para Baixa Automática")
        st.write(
            "Quando a Michele abrir a conta jurídica (PJ), cole as credenciais abaixo. O sistema desligará o simulador automaticamente."
        )

        with st.form("form_gateway_config"):
            g_col1, g_col2 = st.columns(2)
            with g_col1:
                g_provider = st.selectbox(
                    "Provedor / Fintech Bancária",
                    [
                        "Mercado Pago",
                        "Asaas",
                        "Stripe",
                        "PagSeguro",
                        "Gerencianet / Efí",
                    ],
                    index=0,
                    disabled=not is_test_mode(),
                )
                g_pix_key = st.text_input(
                    "Chave Pix CNPJ da Loja",
                    value=config_gtw.gateway_pix_key
                    if config_gtw and config_gtw.gateway_pix_key
                    else "",
                    placeholder="Ex: 12.345.678/0001-90",
                    disabled=not is_test_mode(),
                )
            with g_col2:
                g_api_key = st.text_input(
                    "Access Token / API Key de Produção",
                    value=config_gtw.gateway_api_key
                    if config_gtw and config_gtw.gateway_api_key
                    else "",
                    type="password",
                    placeholder="Cole o token secreto do banco aqui...",
                    disabled=not is_test_mode(),
                )
                st.caption(
                    "Formulário legado disponível somente no E2E isolado. Em runtime "
                    "normal, segredos são configurados por referência no control plane V1."
                )

            btn_salvar_gateway = st.form_submit_button(
                "💾 Salvar configuração simulada de teste",
                type="primary",
                disabled=not is_test_mode(),
            )
            if btn_salvar_gateway:
                if not is_test_mode():
                    st.error("Configuração legada bloqueada fora do ambiente de teste.")
                    st.stop()
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
                    st.success(
                        "✅ Configuração simulada salva no banco temporário de teste."
                    )
                    st.rerun()
                except Exception as e_gtw:
                    db_g_save.rollback()
                    st.error(f"Erro ao salvar configurações bancárias: {e_gtw}")
                finally:
                    db_g_save.close()

    st.markdown("---")

    if not lista_pratos_pdv:
        st.warning(
            "⚠️ Cadastre pratos na Aba 1 (Engenharia de Cardápio) para habilitar o Frente de Caixa."
        )
    else:
        col_pdv1, col_pdv2 = st.columns([3, 2])
        with col_pdv1:
            prod_pdv = st.selectbox(
                "🍔 Selecione o Prato / Lanche",
                lista_pratos_pdv,
                format_func=lambda x: f"{x.nome} — {formatar_moeda_br(x.preco_venda)}",
                key="pdv_produto",
            )
            qtd_pdv = st.number_input(
                "🔢 Quantidade de Itens", min_value=1, step=1, key="pdv_quantidade"
            )
            clientes_por_id_pdv = {
                int(cliente.id): cliente
                for cliente in lista_clientes_pdv
                if getattr(cliente, "id", None) is not None
            }
            opcoes_cliente_ids_pdv = [CLIENTE_BALCAO_ID, *clientes_por_id_pdv.keys()]
            cliente_id_estado_pdv = preparar_cliente_id_pdv(
                st.session_state, clientes_por_id_pdv
            )
            cliente_id_pdv = st.selectbox(
                "👤 Identificar Cliente (Opcional para acúmulo e resgate de Cashback)",
                opcoes_cliente_ids_pdv,
                index=indice_cliente_pdv(cliente_id_estado_pdv, opcoes_cliente_ids_pdv),
                format_func=lambda cliente_id: formatar_opcao_cliente_pdv(
                    cliente_id, clientes_por_id_pdv
                ),
                key="pdv_cliente_id",
                placeholder="Cliente Balcão / Não Identificado",
            )
            cliente_id_pdv = normalizar_cliente_id_pdv(
                cliente_id_pdv, clientes_por_id_pdv
            )
            cliente_pdv = (
                clientes_por_id_pdv.get(cliente_id_pdv)
                if cliente_id_pdv != CLIENTE_BALCAO_ID
                else None
            )

        total_bruto_pdv = prod_pdv.preco_venda * qtd_pdv
        usa_cashback_pdv = False
        desconto_cb_pdv = 0.0

        if cliente_pdv and cliente_pdv.saldo_cashback > 0:
            usa_cashback_pdv = st.checkbox(
                f"💳 Utilizar Saldo de Cashback deste cliente (Disponível: {formatar_moeda_br(cliente_pdv.saldo_cashback)})",
                key="pdv_usa_cashback",
            )
            if usa_cashback_pdv:
                desconto_cb_pdv = min(total_bruto_pdv, cliente_pdv.saldo_cashback)

        total_final_pdv = max(0.0, total_bruto_pdv - desconto_cb_pdv)

        with col_pdv2:
            with st.container():
                st.markdown("### 💰 Resumo Financeiro do Pedido")
                st.markdown(
                    f"**{montar_linha_total_pdv('Subtotal', total_bruto_pdv)}**"
                )
                if usa_cashback_pdv:
                    st.markdown(
                        f"📉 **{montar_linha_total_pdv('Desconto Fidelidade', desconto_cb_pdv, negativo=True)}**"
                    )
                st.markdown(
                    f"### ✅ {montar_linha_total_pdv('Total a Pagar', total_final_pdv)}"
                )

                forma_pag_pdv = st.selectbox(
                    "💳 Forma de Pagamento",
                    list(FORMAS_PAGAMENTO_PERMITIDAS),
                    key="pdv_forma_pagamento",
                )
                valor_recebido_pdv = total_final_pdv
                troco_pdv = calcular_troco(total_final_pdv, valor_recebido_pdv)
                pagamento_dinheiro_valido = True
                if deve_exibir_valor_recebido(forma_pag_pdv):
                    st.markdown("Valor recebido do cliente")
                    col_moeda_pdv, col_valor_recebido_pdv = st.columns([1, 8])
                    with col_moeda_pdv:
                        st.markdown("### R$")
                    with col_valor_recebido_pdv:
                        valor_recebido_pdv = st.number_input(
                            "Valor recebido do cliente",
                            min_value=0.0,
                            value=float(
                                st.session_state.get(
                                    "pdv_valor_recebido_dinheiro", total_final_pdv
                                )
                            ),
                            step=0.50,
                            format="%.2f",
                            key="pdv_valor_recebido_dinheiro",
                            help="Informe o valor recebido em reais; o campo permanece numérico para cálculo automático do troco.",
                            label_visibility="collapsed",
                        )
                    troco_pdv = calcular_troco(total_final_pdv, valor_recebido_pdv)
                    pagamento_dinheiro_valido = pagamento_dinheiro_suficiente(
                        total_final_pdv, valor_recebido_pdv
                    )
                    if pagamento_dinheiro_valido:
                        st.success(f"💵 Troco: {formatar_moeda_br(troco_pdv)}")
                    else:
                        falta_pdv = valor_faltante_pagamento(
                            total_final_pdv, valor_recebido_pdv
                        )
                        st.error(
                            f"Pagamento insuficiente. Ainda faltam {formatar_moeda_br(falta_pdv)} para finalizar a venda."
                        )

        with st.container():
            st.markdown(
                "💡 **Sugestão Inteligente de Upsell para o Operador falar no Balcão:**"
            )
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
                    resp_up = generate_content(contents=prompt_up)
                    if resp_up and resp_up.text:
                        sugestao_upsell = resp_up.text.strip()
                except Exception:
                    pass
            st.info(f"🤖 *{sugestao_upsell}*")

        if forma_pag_pdv.startswith("Pix"):
            st.markdown("---")
            if modo_producao_ativo:
                st.subheader(
                    f"📱 Cobrança Pix Real Gerada via API ({config_gtw.gateway_provider})"
                )
                payload_pix = f"00020126580014br.gov.bcb.pix0136{config_gtw.gateway_pix_key}5204000053039865405{float(total_final_pdv):.2f}5802BR5916MICA BURGER LOJA6009SAO PAULO62070503***6304E12A"
                col_pix1, col_pix2 = st.columns([1, 3])
                with col_pix1:
                    try:
                        st.image(
                            montar_url_qrcode_pix(payload_pix),
                            width=180,
                            caption="QR Code Oficial da Conta PJ",
                        )
                    except Exception:
                        st.warning(
                            "Não foi possível exibir o QR Code Pix agora. Use a chave/código Pix abaixo para concluir o pagamento."
                        )
                with col_pix2:
                    st.success(
                        f"⚡ **Chave Pix Oficial:** `{config_gtw.gateway_pix_key}`"
                    )
                    st.code(payload_pix, language="text")
                    st.write(
                        "🟢 **Status:** Aguardando sinal de confirmação do Webhook do banco na conta da Michele..."
                    )
            else:
                st.subheader("📱 Gateway Pix Automático (Simulador de Treinamento)")
                payload_pix = montar_payload_pix_simulado(total_final_pdv)
                col_pix1, col_pix2 = st.columns([1, 3])
                with col_pix1:
                    try:
                        st.image(
                            montar_url_qrcode_pix(payload_pix),
                            width=180,
                            caption="QR Code Dinâmico (Sandbox)",
                        )
                    except Exception:
                        st.warning(
                            "Não foi possível exibir o QR Code Pix agora. Use a chave/código Pix abaixo para concluir o pagamento."
                        )
                with col_pix2:
                    st.info(
                        "🟡 **Chave Pix de Treinamento (Simulado):**\n\n`00020126580014br.gov.bcb.pix0136123e4567-e89b-12d3-a456-426614174000520400005303986540539.905802BR5916MICA BURGER LOJA6009SAO PAULO62070503***6304E12A`"
                    )
                    st.code(payload_pix, language="text")
                    st.write(
                        "👉 *No modo Sandbox, clique no botão abaixo para simular a aprovação do recebimento:*"
                    )

        st.markdown("---")
        if "pdv_checkout_id" not in st.session_state:
            st.session_state["pdv_checkout_id"] = str(uuid4())
        _terminal_pdv = os.getenv("FM_AI_TEST_TERMINAL", "pdv-default")
        _canary_pdv = _pdv_rollout.modo is ModoPDV.AUTHORITATIVE_CANARY
        botao_finalizar_pdv = st.button(
            "🚀 Confirmar Pagamento & Finalizar Venda",
            type="primary",
            use_container_width=True,
            disabled=bool(st.session_state.get("pdv_processando", False)),
        )
        if botao_finalizar_pdv:
            if st.session_state.get("pdv_processando", False):
                st.warning(
                    "Venda já está em processamento. Aguarde a atualização da tela."
                )
                st.stop()
            st.session_state["pdv_processando"] = True
            cliente_id_selecionado = (
                getattr(cliente_pdv, "id", None) if cliente_pdv else None
            )
            cliente_existe_pdv = True
            if cliente_id_selecionado is not None:
                cliente_existe_pdv = any(
                    c.id == cliente_id_selecionado for c in lista_clientes_pdv
                )

            validacao_pdv = validar_finalizacao_pdv(
                produto=prod_pdv,
                quantidade=qtd_pdv,
                forma_pagamento=forma_pag_pdv,
                valor_recebido=valor_recebido_pdv
                if deve_exibir_valor_recebido(forma_pag_pdv)
                else None,
                cliente_selecionado=cliente_pdv,
                cliente_existe=cliente_existe_pdv,
                usar_cashback=usa_cashback_pdv,
                desconto_cashback=desconto_cb_pdv,
                pix_confirmado=not modo_producao_ativo or _canary_pdv,
                pix_producao=modo_producao_ativo,
            )
            if not validacao_pdv.valido:
                st.session_state["pdv_processando"] = False
                st.error(
                    validacao_pdv.mensagem
                    or "Corrija os campos obrigatórios antes de finalizar."
                )
                st.stop()

            db_exec_venda = SessionLocal()
            db_shadow_pdv = (
                SessionLocal() if _pdv_rollout.modo is ModoPDV.SHADOW else None
            )
            try:
                produto_db = (
                    db_exec_venda.query(Produto)
                    .filter(Produto.id == prod_pdv.id)
                    .first()
                )
                cliente_db = (
                    db_exec_venda.query(Cliente)
                    .filter(Cliente.id == cliente_id_selecionado)
                    .first()
                    if cliente_id_selecionado
                    else None
                )
                validacao_banco = validar_finalizacao_pdv(
                    produto=produto_db,
                    quantidade=qtd_pdv,
                    forma_pagamento=forma_pag_pdv,
                    valor_recebido=valor_recebido_pdv
                    if deve_exibir_valor_recebido(forma_pag_pdv)
                    else None,
                    cliente_selecionado=cliente_pdv,
                    cliente_existe=cliente_id_selecionado is None
                    or cliente_db is not None,
                    usar_cashback=usa_cashback_pdv,
                    desconto_cashback=desconto_cb_pdv,
                    pix_confirmado=not modo_producao_ativo or _canary_pdv,
                    pix_producao=modo_producao_ativo,
                )
                if not validacao_banco.valido:
                    st.session_state["pdv_processando"] = False
                    st.error(
                        validacao_banco.mensagem
                        or "Corrija os campos obrigatórios antes de finalizar."
                    )
                    st.stop()

                if (
                    cliente_db
                    and usa_cashback_pdv
                    and float(validacao_banco.desconto_cashback)
                    > float(cliente_db.saldo_cashback or 0.0)
                ):
                    st.session_state["pdv_processando"] = False
                    st.error(
                        "Cashback não pode ser maior que o saldo disponível do cliente."
                    )
                    st.stop()

                contexto_pdv = contexto_caixa_pdv(
                    tenant_id=_pdv_rollout.tenant_id,
                    unidade_id=_pdv_rollout.unidade_id,
                    usuario_id="caixa-e2e" if is_test_mode() else "caixa-local",
                    correlation_id=str(uuid4()),
                    instante=datetime.now().astimezone(),
                    origem="test" if is_test_mode() else "streamlit-local",
                )
                entrada_pdv = EntradaPDV(
                    produto_id=int(produto_db.id),
                    produto_nome=str(produto_db.nome),
                    quantidade=int(qtd_pdv),
                    preco_unitario=dinheiro_legado(produto_db.preco_venda),
                    custo_total=dinheiro_legado(
                        (produto_db.custo_total_cmv or 0) * qtd_pdv
                    ),
                    forma_pagamento=forma_pag_pdv,
                    terminal_id=_terminal_pdv,
                    checkout_id=str(st.session_state["pdv_checkout_id"]),
                    cliente_id=int(cliente_db.id) if cliente_db else None,
                    valor_recebido=dinheiro_legado(valor_recebido_pdv)
                    if deve_exibir_valor_recebido(forma_pag_pdv)
                    else None,
                    usar_cashback=usa_cashback_pdv,
                    desconto_cashback=dinheiro_legado(
                        validacao_banco.desconto_cashback
                    ),
                    pix_sandbox=forma_pag_pdv.startswith("Pix")
                    and not modo_producao_ativo
                    and is_test_mode(),
                    confirmacao_presencial=forma_pag_pdv.startswith("Cartão"),
                )
                modo_resolvido = decidir_modo(
                    contexto=contexto_pdv,
                    terminal_id=_terminal_pdv,
                    config=_pdv_rollout,
                )
                pedido_id_pdv = id_deterministico(
                    f"{contexto_pdv.tenant_id}:{contexto_pdv.unidade_id}:"
                    f"{entrada_pdv.idempotency_key}:pedido"
                )
                rastrear = modo_resolvido is not ModoPDV.LEGACY
                repo_pdv = RepositorioPDVSQLAlchemy(db_exec_venda) if rastrear else None
                legado_pdv = LegacyPDVSQLAlchemyAdapter(
                    session=db_exec_venda,
                    venda_cls=Venda,
                    cliente_cls=Cliente,
                    insumo_cls=Insumo,
                    ficha_tecnica_cls=FichaTecnica,
                    tenant_id=contexto_pdv.tenant_id,
                    unidade_id=contexto_pdv.unidade_id,
                    pedido_id=pedido_id_pdv,
                    rastrear_efeitos=rastrear,
                    repositorio_pdv=repo_pdv,
                )
                uow_legado = SQLAlchemyPDVUnitOfWork(
                    SessionLocal, fechar=False, session=db_exec_venda
                )
                shadow_writer = None
                shadow_uow = None
                falha_shadow = None
                if db_shadow_pdv is not None:
                    shadow_writer = EscritorShadowSQLAlchemy(
                        db_shadow_pdv, contexto_pdv
                    )
                    shadow_uow = SQLAlchemyPDVUnitOfWork(
                        SessionLocal, fechar=False, session=db_shadow_pdv
                    )
                    falha_shadow = RegistroFalhaShadowSQLAlchemy(
                        SessionLocal,
                        contexto_pdv.tenant_id,
                        contexto_pdv.unidade_id,
                        contexto_pdv.correlation_id,
                    )
                autoritativo_pdv = (
                    ExecutorAutoritativoSQLAlchemy(
                        session=db_exec_venda,
                        contexto=contexto_pdv,
                        legado=legado_pdv,
                    )
                    if modo_resolvido is ModoPDV.AUTHORITATIVE_CANARY
                    else None
                )
                resultado_pdv = finalizar_venda_pdv(
                    entrada=entrada_pdv,
                    contexto=contexto_pdv,
                    config=_pdv_rollout,
                    legado=legado_pdv,
                    uow_legado=uow_legado,
                    shadow=shadow_writer,
                    uow_shadow=shadow_uow,
                    reconciliacao=falha_shadow,
                    autoritativo=autoritativo_pdv,
                    uow_autoritativo=uow_legado
                    if autoritativo_pdv is not None
                    else None,
                )
                if not resultado_pdv.sucesso:
                    st.session_state["pdv_processando"] = False
                    st.info(
                        "Pagamento registrado. Aguardando confirmação financeira válida."
                    )
                    st.stop()
                mensagem_sucesso_pdv = montar_mensagem_sucesso_pdv(
                    total_final=validacao_banco.total_final,
                    forma_pagamento=forma_pag_pdv,
                    valor_recebido=validacao_banco.valor_recebido
                    if deve_exibir_troco(forma_pag_pdv)
                    else None,
                    troco=validacao_banco.troco
                    if deve_exibir_troco(forma_pag_pdv)
                    else None,
                )
                st.session_state["pdv_checkout_id"] = str(uuid4())
                marcar_reset_pdv_apos_sucesso(st.session_state, mensagem_sucesso_pdv)
                st.rerun()
            except Exception as e:
                st.session_state["pdv_processando"] = False
                db_exec_venda.rollback()
                st.error(f"❌ Erro ao registrar a venda no sistema: {e}")
            finally:
                db_exec_venda.close()
                if db_shadow_pdv is not None:
                    db_shadow_pdv.close()

    db_pdv.close()


# ==============================================================================
# ABA 4: ESTOQUE, ALMOXARIFADO & VALIDADES COM I.A.
# ==============================================================================
with aba4:
    st.header("📦 Estoque de Insumos & Controle Inteligente de Validades")
    st.write(
        "Gerencie o saldo em tempo real, automatize cadastros via foto e receba alertas de produtos próximos do vencimento."
    )

    sub_aba1, sub_aba2, sub_aba3 = st.tabs(
        [
            "📊 Almoxarifado & Gestão",
            "➕ Cadastrar Insumos (I.A. / Manual)",
            "🔗 Fichas Técnicas & Receitas",
        ]
    )

    db_estoque = get_db()

    with sub_aba1:
        st.subheader("📋 Status do Almoxarifado em Tempo Real")

        insumos_cadastrados = db_estoque.query(Insumo).all()

        if insumos_cadastrados:
            dados_estoque = []
            valor_total_geral = 0.0

            for i in insumos_cadastrados:
                valor_total_item = i.saldo_atual * i.custo_unitario
                valor_total_geral += valor_total_item

                status_validade = "🟢 No Prazo"
                if i.data_validade:
                    dias_restantes = (i.data_validade.date() - date.today()).days
                    if dias_restantes <= 0:
                        status_validade = "🔴 VENCIDO!"
                    elif dias_restantes <= i.dias_alerta_vencimento:
                        status_validade = f"🟡 Vence em {dias_restantes} dias!"

                status_estoque = (
                    "🔴 Reposição" if i.saldo_atual < i.estoque_minimo else "🟢 Ok"
                )

                dados_estoque.append(
                    {
                        "Insumo": i.nome,
                        "Saldo Atual": f"{i.saldo_atual:.1f} {i.unidade_medida}",
                        "Custo Unit.": f"R$ {i.custo_unitario:.2f}",
                        "Valor Total": f"R$ {valor_total_item:.2f}",
                        "Estoque Mínimo": f"{i.estoque_minimo:.1f} {i.unidade_medida}",
                        "Status Estoque": status_estoque,
                        "Data Validade": i.data_validade.strftime("%d/%m/%Y")
                        if i.data_validade
                        else "N/A",
                        "Status Validade": status_validade,
                    }
                )

            st.dataframe(
                pd.DataFrame(dados_estoque), use_container_width=True, hide_index=True
            )
            st.metric(
                label="💰 Valor Total Geral do Estoque",
                value=f"R$ {valor_total_geral:.2f}",
            )
        else:
            st.info("Nenhum insumo cadastrado no almoxarifado.")

        st.markdown("---")
        st.subheader("🗑️ Excluir Insumo do Estoque")
        if insumos_cadastrados:
            nomes_insumos = [i.nome for i in insumos_cadastrados]
            insumo_para_deletar = st.selectbox(
                "Selecione o insumo para remover:", nomes_insumos, key="del_insumo"
            )

            if st.button("Excluir Insumo Permanentemente", type="primary"):
                item_obj = (
                    db_estoque.query(Insumo).filter_by(nome=insumo_para_deletar).first()
                )
                if item_obj:
                    db_estoque.delete(item_obj)
                    db_estoque.commit()
                    st.success(f"Insumo '{insumo_para_deletar}' excluído com sucesso!")
                    st.rerun()

        st.markdown("---")
        st.subheader("🤖 Forecasting Preditivo & Alertas de Vencimento (WhatsApp)")
        if st.button(
            "🔮 Executar Varredura de Estoque e Validades Agora", type="primary"
        ):
            db_fc = get_db()
            resultado_ia = executar_forecasting_e_alertar(db_fc)
            db_fc.close()
            st.info(resultado_ia)

    with sub_aba2:
        st.subheader("➕ Leitor de Nota Fiscal/Rótulo (I.A. Vision)")
        st.write(
            "Envie a foto de um cupom ou a caixa do produto. O robô lerá o nome, quantidade e as DATAS DE VALIDADE."
        )

        arquivo_nf_cad = st.file_uploader(
            "📸 Foto da Nota Fiscal ou Rótulo",
            type=["jpg", "jpeg", "png"],
            key="uploader_nf_cad_ia",
        )

        if arquivo_nf_cad:
            if st.button(
                "🚀 Processar Leitura com Inteligência Artificial", type="primary"
            ):
                with st.spinner(
                    "🤖 O Gemini está lendo os produtos e as datas de validade..."
                ):
                    try:
                        img_pil = Image.open(arquivo_nf_cad)
                        prompt_ocr = """Você é um auditor de estoque. Analise esta imagem.
                        Extraia os itens e retorne APENAS um array JSON válido no formato: 
                        [{"nome": "Produto", "unidade": "kg", "quantidade": 5.0, "valor_unitario": 12.50, "data_validade": "YYYY-MM-DD"}]
                        Se não encontrar a validade na imagem, preencha o campo data_validade com null.
                        Retorne EXCLUSIVAMENTE o JSON puro (sem markdown)."""

                        resp_cad = generate_content(contents=[prompt_ocr, img_pil])
                        texto_ocr = (
                            resp_cad.text.strip()
                            .replace("```json", "")
                            .replace("```", "")
                            .strip()
                        )
                        itens_lidos = json.loads(texto_ocr)

                        db_cad = get_db()
                        for item in itens_lidos:
                            nome_l = str(item.get("nome", "")).strip()
                            qtd_l = float(item.get("quantidade", 0.0))
                            val_str = item.get("data_validade")

                            val_obj = None
                            if val_str:
                                try:
                                    val_obj = datetime.strptime(val_str, "%Y-%m-%d")
                                except ValueError:
                                    pass

                            if nome_l and qtd_l > 0:
                                ins_db = (
                                    db_cad.query(Insumo)
                                    .filter(Insumo.nome.ilike(f"%{nome_l}%"))
                                    .first()
                                )
                                if ins_db:
                                    ins_db.saldo_atual += qtd_l
                                    if val_obj:
                                        ins_db.data_validade = val_obj
                                else:
                                    novo_i = Insumo(
                                        nome=nome_l,
                                        unidade_medida=item.get("unidade", "un"),
                                        saldo_atual=qtd_l,
                                        estoque_minimo=qtd_l * 0.15,
                                        data_validade=val_obj,
                                        dias_alerta_vencimento=15,
                                    )
                                    db_cad.add(novo_i)

                        db_cad.commit()
                        st.success(
                            "🎉 Leitura concluída! Validades salvas no banco de dados."
                        )
                        st.json(itens_lidos)
                    except Exception as e:
                        st.error(f"❌ Erro na leitura: {e}")

        st.divider()
        st.markdown("### ✍️ Cadastro Manual de Insumo (Com Validade e Lote)")

        with st.form("form_cadastro_manual", clear_on_submit=True):
            col_m1, col_m2, col_m3 = st.columns(3)

            with col_m1:
                novo_nome = st.text_input("Nome do Insumo (Ex: Pão Australiano)")
                unidade_medida = st.selectbox(
                    "Unidade de Medida", ["kg", "g", "L", "ml", "un", "cx", "fatias"]
                )
            with col_m2:
                novo_saldo = st.number_input(
                    "Quantidade Inicial", min_value=0.0, value=0.0
                )
                estoque_minimo = st.number_input(
                    "Estoque Mínimo", min_value=0.0, value=10.0
                )
            with col_m3:
                novo_custo = st.number_input(
                    "Custo Unitário (R$)", min_value=0.0, value=0.0
                )
                dias_alerta = st.number_input(
                    "🚨 Alerta Vencimento (Dias)", min_value=1, value=15
                )

            col_m4, col_m5 = st.columns(2)
            with col_m4:
                nova_fab = st.date_input("Data de Fabricação (Opcional)", value=None)
            with col_m5:
                nova_val = st.date_input(
                    "Data de Validade (Controle de Lote)",
                    value=date.today() + timedelta(days=30),
                )

            if st.form_submit_button(
                "💾 Salvar Insumo no Almoxarifado", type="primary"
            ):
                if novo_nome.strip() != "":
                    db_m = get_db()
                    try:
                        novo_insumo = Insumo(
                            nome=novo_nome.strip(),
                            unidade_medida=unidade_medida,
                            saldo_atual=novo_saldo,
                            estoque_minimo=estoque_minimo,
                            custo_unitario=novo_custo,
                            data_fabricacao=nova_fab,
                            data_validade=nova_val,
                            dias_alerta_vencimento=dias_alerta,
                        )
                        db_m.add(novo_insumo)
                        db_m.commit()
                        st.success(
                            f"✅ Insumo '{novo_nome}' salvo no Almoxarifado com controle de validade!"
                        )
                        st.rerun()
                    except Exception:
                        db_m.rollback()
                        st.error(
                            f"❌ Erro ao salvar: Já existe um insumo cadastrado com o nome '{novo_nome}' ou ocorreu um conflito."
                        )
                    finally:
                        db_m.close()
                else:
                    st.warning("⚠️ O nome do insumo não pode estar vazio.")

    with sub_aba3:
        st.subheader("🔗 Fichas Técnicas & Receitas Vinculadas")
        st.write("Gerencie os vínculos entre insumos e produtos do cardápio.")

# ==============================================================================
# ABA 5: DASHBOARD FINANCEIRO E HISTÓRICO DE VENDAS
# ==============================================================================
with aba5:
    st.header("📊 Dashboard Financeiro & Indicadores de Performance")
    st.write(
        "Visão geral em tempo real de faturamento, custo de mercadoria vendida (CMV), lucro bruto e margem operacional da loja."
    )

    db_dash = get_db()
    todas_vendas = db_dash.query(Venda).all()

    faturamento_total = sum(v.valor_total for v in todas_vendas)
    custo_total_vendas = sum(v.custo_total for v in todas_vendas)
    lucro_bruto = faturamento_total - custo_total_vendas
    margem_geral = (
        (lucro_bruto / faturamento_total * 100) if faturamento_total > 0 else 0.0
    )

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
            tabela_vendas.append(
                {
                    "ID": v.id,
                    "Data / Hora": v.data_venda.strftime("%d/%m/%Y %H:%M"),
                    "Prato / Lanche": v.produto.nome if v.produto else "Item Removido",
                    "Qtd": v.quantidade,
                    "Forma Pagamento": v.forma_pagamento,
                    "Valor Total": f"R$ {v.valor_total:.2f}",
                    "Custo CMV": f"R$ {v.custo_total:.2f}",
                }
            )
        st.dataframe(
            pd.DataFrame(tabela_vendas), use_container_width=True, hide_index=True
        )
    else:
        st.info("Nenhuma venda registrada no sistema operacional até o momento.")

    db_dash.close()


# ==============================================================================
# ABA 6: ASSISTENTE DE ATENDIMENTO V1 — FLUXO SEGURO
# ==============================================================================
with aba6:
    db_identidade_assistente = SessionLocal()
    try:
        identidade_assistente = RepositorioIdentidadeAssistenteSQLAlchemy(
            db_identidade_assistente
        ).obter(
            tenant_id=CURRENT_IDENTITY.tenant_id,
            unidade_id=CURRENT_IDENTITY.unidade_id,
        ) or ConfiguracaoIdentidadeAssistente.fallback(
            tenant_id=CURRENT_IDENTITY.tenant_id,
            unidade_id=CURRENT_IDENTITY.unidade_id,
        )
    except SQLAlchemyError:  # compatibilidade local antes da migration 0013
        identidade_assistente = ConfiguracaoIdentidadeAssistente.fallback(
            tenant_id=CURRENT_IDENTITY.tenant_id,
            unidade_id=CURRENT_IDENTITY.unidade_id,
        )
    finally:
        db_identidade_assistente.close()
    render_assistente_atendimento_v1(
        session_factory=SessionLocal,
        produto_cls=Produto,
        generate_content=generate_content,
        nome_publico=identidade_assistente.nome_publico,
    )

# Contrato técnico de prontidão dos testes browser-driven. Ele é emitido apenas
# depois que o script inteiro construiu a interface e nunca aparece em produção.
if is_test_mode():
    st.markdown(
        f'<span data-fm-ai-e2e-ready="true" data-fm-ai-e2e-run="{st.session_state["_fm_ai_e2e_run"]}" style="display:none" aria-hidden="true"></span>',
        unsafe_allow_html=True,
    )
