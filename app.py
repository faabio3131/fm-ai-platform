from datetime import datetime, timedelta
import hashlib
import json
import os
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
import streamlit as st

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="F&M AI FOOD — Mica Burguer & Restaurante ERP", page_icon="🍔", layout="wide"
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

# --- AUTO-CORREÇÃO E ATUALIZAÇÃO DO SQLITE ---
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


def recalcular_cmv_geral(db_session):
    try:
        produtos = db_session.query(Produto).all()
        for prod in produtos:
            fichas = db_session.query(FichaTecnica).filter(FichaTecnica.produto_id == prod.id).all()
            if fichas:
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


# --- MOTOR DE CARREGAMENTO REAL DA MICA BURGUER & MARMITAS ---
def popular_dados_iniciais():
    db = SessionLocal()
    try:
        # Verifica se o cardápio com Marmitas já foi carregado
        mica_teste = db.query(Produto).filter(Produto.nome.like("%Feijoada Completa%")).first()
        
        if not mica_teste:
            db.query(FichaTecnica).delete()
            db.query(Venda).delete()
            db.query(Produto).delete()
            db.query(Insumo).delete()
            db.commit()

            # 1. ALMOXARIFADO INDUSTRIAL COMPLETO (Burgers + Cozinha Quente/Marmitas)
            insumos_mica = [
                # Insumos Hamburgueria
                Insumo(nome="Carne Angus 150g (Artesanal)", unidade_medida="un", saldo_atual=300.0, estoque_minimo=40.0, custo_unitario=5.80),
                Insumo(nome="Carne Angus 120g (Artesanal)", unidade_medida="un", saldo_atual=300.0, estoque_minimo=40.0, custo_unitario=4.60),
                Insumo(nome="Carne Bovino 90g (Smash)", unidade_medida="un", saldo_atual=400.0, estoque_minimo=50.0, custo_unitario=3.50),
                Insumo(nome="Hambúrguer Perdigão (Tradicional)", unidade_medida="un", saldo_atual=500.0, estoque_minimo=80.0, custo_unitario=1.80),
                Insumo(nome="Frango Crocante 120g", unidade_medida="un", saldo_atual=150.0, estoque_minimo=30.0, custo_unitario=3.90),
                Insumo(nome="Pão Brioche Artesanal", unidade_medida="un", saldo_atual=350.0, estoque_minimo=50.0, custo_unitario=1.80),
                Insumo(nome="Pão Tradicional com Gergelim", unidade_medida="un", saldo_atual=400.0, estoque_minimo=60.0, custo_unitario=1.20),
                Insumo(nome="Queijo Provolone / Cheddar Fatiado", unidade_medida="fatias", saldo_atual=800.0, estoque_minimo=100.0, custo_unitario=1.10),
                Insumo(nome="Queijo Mussarela Fatiado", unidade_medida="fatias", saldo_atual=600.0, estoque_minimo=80.0, custo_unitario=0.90),
                Insumo(nome="Catupiry Original", unidade_medida="kg", saldo_atual=15.0, estoque_minimo=3.0, custo_unitario=45.00),
                Insumo(nome="Bacon Artesanal em Tiras", unidade_medida="kg", saldo_atual=25.0, estoque_minimo=5.0, custo_unitario=35.00),
                Insumo(nome="Calabresa Fatiada / Grelhada", unidade_medida="kg", saldo_atual=30.0, estoque_minimo=4.0, custo_unitario=28.00),
                Insumo(nome="Ovo Fresco (Egg / Omelete)", unidade_medida="un", saldo_atual=300.0, estoque_minimo=50.0, custo_unitario=0.70),
                Insumo(nome="Batata Frita Congelada", unidade_medida="kg", saldo_atual=80.0, estoque_minimo=15.0, custo_unitario=14.00),
                Insumo(nome="Anéis de Cebola (Orions)", unidade_medida="kg", saldo_atual=30.0, estoque_minimo=5.0, custo_unitario=22.00),
                Insumo(nome="Alface Americana / Mix de Salada", unidade_medida="kg", saldo_atual=20.0, estoque_minimo=4.0, custo_unitario=8.00),
                Insumo(nome="Tomate Carmem Fresco", unidade_medida="kg", saldo_atual=25.0, estoque_minimo=5.0, custo_unitario=7.00),
                Insumo(nome="Maionese Caseira da Casa", unidade_medida="kg", saldo_atual=20.0, estoque_minimo=4.0, custo_unitario=15.00),
                Insumo(nome="Coca-Cola Lata 350ml", unidade_medida="un", saldo_atual=240.0, estoque_minimo=48.0, custo_unitario=3.20),
                
                # Insumos Cozinha Quente / Marmitas Executivas
                Insumo(nome="Arroz Branco Agulhinha", unidade_medida="kg", saldo_atual=120.0, estoque_minimo=25.0, custo_unitario=4.50),
                Insumo(nome="Feijão Carioca / Feijão Preto", unidade_medida="kg", saldo_atual=80.0, estoque_minimo=15.0, custo_unitario=7.00),
                Insumo(nome="Contra Filé / Bife Bovino Selecionado", unidade_medida="kg", saldo_atual=45.0, estoque_minimo=10.0, custo_unitario=36.00),
                Insumo(nome="Peito de Frango / Filé Grelhado", unidade_medida="kg", saldo_atual=60.0, estoque_minimo=12.0, custo_unitario=18.00),
                Insumo(nome="Copa Lombo Suíno / Bisteca", unidade_medida="kg", saldo_atual=35.0, estoque_minimo=8.0, custo_unitario=22.00),
                Insumo(nome="Filé de Peixe (Merluza/Tilápia)", unidade_medida="kg", saldo_atual=25.0, estoque_minimo=5.0, custo_unitario=32.00),
                Insumo(nome="Espaguete / Massa Penne", unidade_medida="kg", saldo_atual=40.0, estoque_minimo=8.0, custo_unitario=6.00),
                Insumo(nome="Embalagem Marmitex Isopor/Alumínio nº 8", unidade_medida="un", saldo_atual=600.0, estoque_minimo=100.0, custo_unitario=1.20),
            ]
            db.add_all(insumos_mica)
            db.commit()

            # 2. CARDÁPIO COMPLETO (Burgers + Marmitas Executivas do PDF)
            produtos_mica = [
                # --- MARMITAS & PRATOS EXECUTIVOS (PDF MICA RESTAURANTE) ---
                Produto(nome="[Segunda] Copa Lombo com Feijão Tropeiro", categoria="Marmitas & Executivos", preco_venda=26.90, custo_total_cmv=8.80, margem_exibicao="67.3%", descricao_bruta="Copa lombo suculenta acompanhada de feijão tropeiro com bacon, linguiça, farinha artesanal e ovos. Acompanha arroz e salada.", descricao_ai="O almoço perfeito de segunda-feira! Copa lombo suculenta com o verdadeiro feijão tropeiro da casa, arroz branco e salada fresca."),
                Produto(nome="[Segunda] Filé de Frango Grelhado Executivo", categoria="Marmitas & Executivos", preco_venda=22.90, custo_total_cmv=7.10, margem_exibicao="69.0%", descricao_bruta="Filé de frango grelhado temperado com alho e limão. Acompanha arroz branco, feijão e salada fresca.", descricao_ai="Leve e saboroso para começar a semana: filé de frango grelhado ao toque de limão com arroz, feijão e salada."),
                Produto(nome="[Terça] Frango ao Molho com Purê de Batata", categoria="Marmitas & Executivos", preco_venda=24.90, custo_total_cmv=7.60, margem_exibicao="69.5%", descricao_bruta="Pedacinhos de frango ao molho rústico de tomate acompanhados de purê de batata cremoso, arroz, feijão e salada.", descricao_ai="Sabor de comida caseira de verdade! Frango ao molho especial servido com nosso purê cremoso de batatas."),
                Produto(nome="[Quarta] Contra Filé Acebolado com Vinagrete", categoria="Marmitas & Executivos", preco_venda=29.90, custo_total_cmv=10.50, margem_exibicao="64.9%", descricao_bruta="Bife de contra filé macio grelhado com cebolas, acompanhado de vinagrete fresco, arroz branco, feijão e salada.", descricao_ai="O queridinho da quarta-feira! Contra filé macio e acebolado com vinagrete fresco, arroz e feijão."),
                Produto(nome="[Quarta] Bife a Cavalo Executivo", categoria="Marmitas & Executivos", preco_venda=28.90, custo_total_cmv=9.80, margem_exibicao="66.1%", descricao_bruta="Bife de contra filé grelhado coberto com ovo frito na hora. Acompanha arroz branco, feijão e salada.", descricao_ai="O clássico Bife a Cavalo: contra filé selecionado com ovo frito perfeito, arroz agulhinha e feijão."),
                Produto(nome="[Quinta] Espaguete à Bolonhesa (Massa da Semana)", categoria="Marmitas & Executivos", preco_venda=25.90, custo_total_cmv=7.50, margem_exibicao="71.0%", descricao_bruta="Espaguete italiano ao molho bolonhesa com carne moída selecionada, tomate fresco, alho e queijo parmesão.", descricao_ai="Quinta é dia de massa na Mica! Espaguete al dente coberto com nosso generoso molho à bolonhesa caseiro."),
                Produto(nome="[Quinta] Lasanha de Frango à Bolonhesa", categoria="Marmitas & Executivos", preco_venda=27.90, custo_total_cmv=8.40, margem_exibicao="69.9%", descricao_bruta="Lasanha artesanal em camadas com frango desfiado, molho branco cremoso, molho bolonhesa e muito queijo gratinado.", descricao_ai="Lasanha artesanal irresistível! Camadas cremosas de frango, molho especial e queijo gratinado no forno."),
                Produto(nome="[Sexta] Filé de Peixe com Purê de Mandioquinha", categoria="Marmitas & Executivos", preco_venda=28.90, custo_total_cmv=9.50, margem_exibicao="67.1%", descricao_bruta="Filé de peixe branco grelhado na manteiga com limão, acompanhado de purê cremoso de mandioquinha, arroz e salada.", descricao_ai="O toque gourmet da sexta-feira: filé de peixe grelhado na manteiga servido com purê de mandioquinha exclusivo."),
                Produto(nome="[Sexta] Strogonoff de Carne com Batata Palha", categoria="Marmitas & Executivos", preco_venda=26.90, custo_total_cmv=8.20, margem_exibicao="69.5%", descricao_bruta="Iscas macias de carne ao molho cremoso de strogonoff com champignon. Acompanha arroz branco e batata palha crocante.", descricao_ai="O estrogonofe que todo mundo ama! Iscas de carne macia em molho cremoso com muito arroz e batata palha."),
                Produto(nome="[Sábado] Feijoada Completa da Casa", categoria="Marmitas & Executivos", preco_venda=38.90, custo_total_cmv=13.50, margem_exibicao="65.3%", descricao_bruta="Feijoada completa com feijão preto, carne seca, costelinha, linguiça paio e bacon. Acompanha arroz, couve e farofa.", descricao_ai="A tradição de sábado na Mica! Feijoada completa rica em carnes nobres, servida com arroz branco, couve e farofa."),
                Produto(nome="[Sábado] Bife à Parmegiana Executivo", categoria="Marmitas & Executivos", preco_venda=34.90, custo_total_cmv=11.20, margem_exibicao="67.9%", descricao_bruta="Contra filé empanado e crocante coberto com molho de tomate caseiro e muito queijo derretido. Acompanha arroz e batatas.", descricao_ai="Parmegiana de respeito! Bife empanado super crocante gratinado com queijo e molho de tomates frescos."),

                # --- COMBOS HAMBURGUERIA ---
                Produto(nome="Combo 1 / Mica Cheddar Bacon", categoria="Combos", preco_venda=42.90, custo_total_cmv=13.50, margem_exibicao="68.5%", descricao_bruta="Hambúrguer suculento 150g acompanhado de fatias generosas de bacon crocante, queijo cheddar derretido, batata e bebida.", descricao_ai="Um clássico irresistível da Mica Burguer! Hambúrguer suculento 150g com fatias generosas de bacon e queijo cheddar."),
                Produto(nome="Combo 2 / Mica - Salada", categoria="Combos", preco_venda=41.90, custo_total_cmv=12.80, margem_exibicao="69.4%", descricao_bruta="Hambúrguer artesanal 120g de carne selecionada, alface crocante, tomate fresco, maionese, batata e bebida.", descricao_ai="O equilíbrio perfeito! Burger artesanal 120g, alface crocante, tomate fresco e a nossa maionese especial."),
                
                # --- LANCHES GOURMET / ARTESANAIS ---
                Produto(nome="Mica Três Ladeiras", categoria="Lanches Gourmet", preco_venda=39.90, custo_total_cmv=12.40, margem_exibicao="68.9%", descricao_bruta="Hambúrguer bovino suculento 150g com mussarela derretida, cheddar cremoso e o irresistível Catupiry Original no pão brioche.", descricao_ai="A obra-prima da casa! Burger suculento com trindade de queijos: mussarela, cheddar cremoso e Catupiry Original."),
                Produto(nome="X - Salada Artesanal", categoria="Lanches Gourmet", preco_venda=24.90, custo_total_cmv=7.80, margem_exibicao="68.7%", descricao_bruta="Hambúrguer artesanal 120g de carne selecionada, queijo derretido, alface crocante, tomate fresco e maionese da casa.", descricao_ai="Um lanche feito com carinho e sabor de verdade! Burger artesanal 120g e vegetais selecionados."),
                Produto(nome="X - Bacon Artesanal", categoria="Lanches Gourmet", preco_venda=24.90, custo_total_cmv=8.20, margem_exibicao="67.1%", descricao_bruta="Hambúrguer artesanal suculento 120g, queijo derretido, bacon crocante, alface crocante, tomate fresco e maionese.", descricao_ai="A combinação perfeita do burger artesanal 120g com tiras crocantes de bacon artesanal."),
                
                # --- LANCHES TRADICIONAIS (PERDIGÃO) ---
                Produto(nome="X - Bacon Tradicional", categoria="Lanches Tradicionais", preco_venda=18.90, custo_total_cmv=5.80, margem_exibicao="69.3%", descricao_bruta="Hambúrguer Perdigão acompanhado de fatias de bacon crocante, queijo derretido, alface, tomate e maionese cremo.", descricao_ai="O queridinho tradicional! Hambúrguer Perdigão com bacon crocante e maionese especial."),
                Produto(nome="X - Salada Tradicional", categoria="Lanches Tradicionais", preco_venda=17.90, custo_total_cmv=5.20, margem_exibicao="70.9%", descricao_bruta="Hambúrguer Perdigão saboroso com queijo derretido, alface, tomate fresco e maionese cremo.", descricao_ai="Clássico e rápido: Hambúrguer Perdigão, queijo derretido, alface, tomate e maionese cremo."),

                # --- PORÇÕES & BEBIDAS ---
                Produto(nome="Porção de Batata Cheddar Bacon", categoria="Porções & Entradas", preco_venda=24.90, custo_total_cmv=7.50, margem_exibicao="69.9%", descricao_bruta="Uma porção de batatas fritas 300g com cheddar cremoso e bacon crocante, perfeita para compartilhar.", descricao_ai="300g de batatas fritas crocantes cobertas com muito queijo cheddar e bacon em tiras."),
                Produto(nome="Orions (Anéis de Cebola)", categoria="Porções & Entradas", preco_venda=24.90, custo_total_cmv=7.00, margem_exibicao="71.9%", descricao_bruta="Deliciosos anéis de cebola empanados e fritos até ficarem dourados e crocantes. Servidos com molho.", descricao_ai="Anéis de cebola Orions empanados e super crocantes. Acompanha molho da casa."),
                Produto(nome="Coca-Cola Lata 350ml", categoria="Bebidas", preco_venda=7.00, custo_total_cmv=3.20, margem_exibicao="54.3%", descricao_bruta="Lata 350ml tradicional gelada.", descricao_ai="Coca-Cola Lata 350ml gelada."),
                Produto(nome="Guaraná Antarctica Lata 350ml", categoria="Bebidas", preco_venda=7.00, custo_total_cmv=3.00, margem_exibicao="57.1%", descricao_bruta="Lata 350ml tradicional gelada.", descricao_ai="Guaraná Antarctica Lata 350ml gelada."),
            ]
            db.add_all(produtos_mica)
            db.commit()

            # 3. VINCULAÇÕES DE FICHA TÉCNICA (Marmitas + Burgers)
            p_feijoada = db.query(Produto).filter(Produto.nome.like("%Feijoada Completa%")).first()
            p_contra = db.query(Produto).filter(Produto.nome.like("%Contra Filé Acebolado%")).first()
            p_tres_lad = db.query(Produto).filter(Produto.nome == "Mica Três Ladeiras").first()
            p_coca = db.query(Produto).filter(Produto.nome == "Coca-Cola Lata 350ml").first()

            i_arroz = db.query(Insumo).filter(Insumo.nome.like("%Arroz%")).first()
            i_feijao = db.query(Insumo).filter(Insumo.nome.like("%Feijão%")).first()
            i_bife = db.query(Insumo).filter(Insumo.nome.like("%Contra Filé%")).first()
            i_bacon = db.query(Insumo).filter(Insumo.nome.like("%Bacon%")).first()
            i_calab = db.query(Insumo).filter(Insumo.nome.like("%Calabresa%")).first()
            i_marmitex = db.query(Insumo).filter(Insumo.nome.like("%Embalagem%")).first()
            i_carne150 = db.query(Insumo).filter(Insumo.nome.like("%150g%")).first()
            i_pao_brioche = db.query(Insumo).filter(Insumo.nome.like("%Brioche%")).first()
            i_cheddar = db.query(Insumo).filter(Insumo.nome.like("%Provolone / Cheddar%")).first()
            i_mussa = db.query(Insumo).filter(Insumo.nome.like("%Mussarela%")).first()
            i_catupiry = db.query(Insumo).filter(Insumo.nome.like("%Catupiry%")).first()
            i_coca_lata = db.query(Insumo).filter(Insumo.nome == "Coca-Cola Lata 350ml").first()

            fichas_iniciais = []
            if p_feijoada and i_feijao and i_bacon and i_calab and i_arroz and i_marmitex:
                fichas_iniciais.extend([
                    FichaTecnica(produto_id=p_feijoada.id, insumo_id=i_feijao.id, quantidade_utilizada=0.25), # 250g feijão/carnes
                    FichaTecnica(produto_id=p_feijoada.id, insumo_id=i_bacon.id, quantidade_utilizada=0.05),
                    FichaTecnica(produto_id=p_feijoada.id, insumo_id=i_calab.id, quantidade_utilizada=0.08),
                    FichaTecnica(produto_id=p_feijoada.id, insumo_id=i_arroz.id, quantidade_utilizada=0.20), # 200g arroz
                    FichaTecnica(produto_id=p_feijoada.id, insumo_id=i_marmitex.id, quantidade_utilizada=1.0),
                ])
            if p_contra and i_bife and i_arroz and i_feijao and i_marmitex:
                fichas_iniciais.extend([
                    FichaTecnica(produto_id=p_contra.id, insumo_id=i_bife.id, quantidade_utilizada=0.18), # 180g bife
                    FichaTecnica(produto_id=p_contra.id, insumo_id=i_arroz.id, quantidade_utilizada=0.20),
                    FichaTecnica(produto_id=p_contra.id, insumo_id=i_feijao.id, quantidade_utilizada=0.10),
                    FichaTecnica(produto_id=p_contra.id, insumo_id=i_marmitex.id, quantidade_utilizada=1.0),
                ])
            if p_tres_lad and i_carne150 and i_pao_brioche and i_cheddar and i_mussa and i_catupiry:
                fichas_iniciais.extend([
                    FichaTecnica(produto_id=p_tres_lad.id, insumo_id=i_pao_brioche.id, quantidade_utilizada=1.0),
                    FichaTecnica(produto_id=p_tres_lad.id, insumo_id=i_carne150.id, quantidade_utilizada=1.0),
                    FichaTecnica(produto_id=p_tres_lad.id, insumo_id=i_cheddar.id, quantidade_utilizada=2.0),
                    FichaTecnica(produto_id=p_tres_lad.id, insumo_id=i_mussa.id, quantidade_utilizada=2.0),
                    FichaTecnica(produto_id=p_tres_lad.id, insumo_id=i_catupiry.id, quantidade_utilizada=0.04),
                ])
            if p_coca and i_coca_lata:
                fichas_iniciais.append(FichaTecnica(produto_id=p_coca.id, insumo_id=i_coca_lata.id, quantidade_utilizada=1.0))
            
            if fichas_iniciais:
                db.add_all(fichas_iniciais)
                db.commit()
                recalcular_cmv_geral(db)

        if db.query(Cliente).count() == 0:
            clientes_padrao = [
                Cliente(nome="Carlos Eduardo (VIP)", whatsapp="11999991111", ultima_compra=datetime.now() - timedelta(days=2), total_gasto=450.0, status="Ativo"),
                Cliente(nome="Ana Souza", whatsapp="11988882222", ultima_compra=datetime.now() - timedelta(days=18), total_gasto=120.0, status="Inativo (15+ dias)"),
                Cliente(nome="Marcos Silva", whatsapp="11977773333", ultima_compra=datetime.now() - timedelta(days=35), total_gasto=89.0, status="Inativo (30+ dias)"),
                Cliente(nome="Juliana Mendes", whatsapp="11966664444", ultima_compra=datetime.now() - timedelta(days=60), total_gasto=210.0, status="Inativo (45+ dias)"),
            ]
            db.add_all(clientes_padrao)
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

# --- 4. BARRA LATERAL ---
with st.sidebar:
    if os.path.exists("logo.png"):
        st.image("logo.png", use_container_width=True)
    else:
        st.image("https://cdn-icons-png.flaticon.com/512/3075/3075977.png", use_container_width=True)

    st.title("F&M AI FOOD")
    st.caption("Mica Burguer & Restaurante ERP")
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
            nome_prato = st.text_input("🍔 Nome do Prato / Lanche", placeholder="Ex: [Sexta] Strogonoff de Carne ou Mica Royal")
            categoria = st.selectbox("📂 Categoria", ["Marmitas & Executivos", "Combos", "Lanches Gourmet", "Lanches Tradicionais", "Porções & Entradas", "Acompanhamentos", "Bebidas"])
            ingredientes_base = st.text_area("📝 Ingredientes Principais", placeholder="Ex: Iscas de carne ao molho cremoso com arroz branco e batata palha.")
        with col2:
            preco_venda = st.number_input("💲 Preço de Venda (R$)", min_value=0.0, value=26.90, step=0.50, format="%.2f")
            custo_cmv = round(preco_venda * 0.32, 2)
            margem_calc = round(((preco_venda - custo_cmv) / preco_venda) * 100, 1) if preco_venda > 0 else 0.0
            st.info(f"📉 CMV Teórico Estimado (32%): R$ {custo_cmv:.2f}\n📈 **Margem de Lucro Bruta:** {margem_calc}%")

        btn_gerar_ia = st.form_submit_button("🚀 Processar Texto & Imagem com Google I.A.", type="primary")

    if btn_gerar_ia:
        if not nome_prato or not ingredientes_base:
            st.error("⚠️ Por favor, preencha o Nome do Prato e os Ingredientes Principais!")
        else:
            db = get_db()
            desc_gerada = f"Experimente o magnífico {nome_prato}! Preparado com maestria utilizando {ingredientes_base.lower()}. Uma verdadeira experiência gastronômica da Mica!"
            caminho_imagem_salva = None

            if GENAI_DISPONIVEL:
                with st.spinner("🤖 A Inteligência Artificial está escrevendo a legenda gourmet e renderizando a fotografia..."):
                    try:
                        model_text = genai.GenerativeModel("gemini-1.5-flash")
                        prompt_texto = f"Escreva uma descrição publicitária curta, altamente persuasiva, gourmet e apetitosa para um cardápio de restaurante para o prato: '{nome_prato}'. Ingredientes: {ingredientes_base}."
                        resp_texto = model_text.generate_content(prompt_texto)
                        if resp_texto and resp_texto.text:
                            desc_gerada = resp_texto.text.strip()

                        try:
                            from google.generativeai import ImageGenerationModel
                            model_img = ImageGenerationModel("imagen-3.0-generate-002")
                            prompt_img = f"Professional studio food photography of a dish named {nome_prato}, containing {ingredientes_base}. 4k resolution, cinematic lighting, appetizing presentation."
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
    st.subheader("🖼️ Galeria de Pratos: Mica Burguer & Marmitas Executivas")
    db = get_db()
    produtos_cadastrados = db.query(Produto).order_by(Produto.categoria, Produto.nome).all()

    if produtos_cadastrados:
        cols = st.columns(4)
        for idx, prod in enumerate(produtos_cadastrados):
            with cols[idx % 4]:
                if prod.imagem_path and os.path.exists(prod.imagem_path):
                    st.image(prod.imagem_path, use_container_width=True)
                else:
                    st.image("https://cdn-icons-png.flaticon.com/512/3075/3075977.png", use_container_width=True)
                st.markdown(f"**{prod.nome}**")
                st.caption(f"📂 {prod.categoria} | R$ {prod.preco_venda:.2f}\n📉 CMV: R$ {prod.custo_total_cmv:.2f} | Margem: {prod.margem_exibicao}")
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
                    texto_mkt = f"🚨 ATENÇÃO GOURMET! 🚨\n\nVenha saborear o incrível **{prato_sel.nome}** na Mica por apenas R$ {prato_sel.preco_venda:.2f}!\n\n{prato_sel.descricao_ai}\n\n👇 Peça já pelo WhatsApp!"
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
                msg_resgate = f"Olá {{nome}}! 🍔 Estamos com saudades de você aqui na Mica Burguer & Restaurante! Notamos que faz um tempo desde seu último pedido. Para matar essa vontade, preparamos um cupom exclusivo de **{desconto_cupom}% DE DESCONTO** para você usar hoje no almoço ou no jantar! Use o código **MICA{desconto_cupom}** no nosso WhatsApp. Aproveite! 🔥"
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
    lista_pratos = db.query(Produto).order_by(Produto.categoria, Produto.nome).all()
    lista_clientes = db.query(Cliente).all()

    if not lista_pratos:
        st.warning("⚠️ Cadastre produtos na Aba 1 para habilitar o PDV.")
    else:
        col_p1, col_p2 = st.columns([1, 2])
        with col_p1:
            prod_pdv = st.selectbox("Prato / Marmita / Combo", lista_pratos, format_func=lambda x: f"[{x.categoria}] {x.nome} (R$ {x.preco_venda:.2f})")
            cliente_pdv = st.selectbox("Cliente (Opcional)", [None] + lista_clientes, format_func=lambda c: "👤 Consumidor Final (Sem Cadastro)" if c is None else f"⭐ {c.nome} ({c.whatsapp})")
            qtd = st.number_input("Quantidade", min_value=1, value=1, step=1)
            total = prod_pdv.preco_venda * qtd

            # --- MOTOR DE UPSELL INTELIGENTE (IA) ---
            with st.container(border=True):
                st.markdown("💡 **Dica de Upsell da I.A. para o Caixa:**")
                sugestao_upsell = "Ao registrar essa marmita ou lanche, ofereça adicionar uma **Coca-Cola Gelada** ou uma **Porção de Orions (Anéis de Cebola)** para aumentar o ticket médio!"
                if GENAI_DISPONIVEL and prod_pdv:
                    try:
                        model_up = genai.GenerativeModel("gemini-1.5-flash")
                        prompt_up = f"Atuo como caixa no restaurante Mica Burguer e Marmitas. O cliente está comprando '{prod_pdv.nome}'. Dê uma sugestão curta (1 frase) e persuasiva de acompanhamento ou bebida do nosso cardápio para eu oferecer agora e aumentar a venda."
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
# ABA 4: ESTOQUE & FICHA TÉCNICA (COM LEITOR DE NOTA FISCAL POR I.A.)
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
        st.subheader("📋 Almoxarifado em Tempo Real (Mica Burguer & Marmitas)")
        insumos_cadastrados = db_estoque.query(Insumo).order_by(Insumo.nome).all()
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
                        novo_ins = Insumo(nome=nome_ins, unidade_medida=unidade, saldo_atual=saldo_inicial, estoque_minimo=est_min, custo_unitario=custo_uni)
                        db_estoque.add(novo_ins)
                        db_estoque.commit()
                        st.success(f"🎉 Insumo **{nome_ins}** cadastrado com sucesso!")
                        st.rerun()
                    except Exception as e:
                        db_estoque.rollback()
                        st.error(f"❌ Erro ao cadastrar insumo: {e}")

    with sub_aba3:
        st.subheader("🔗 Montagem de Receitas em Massa (Ficha Técnica)")
        produtos_ft = db_estoque.query(Produto).order_by(Produto.categoria, Produto.nome).all()
        insumos_ft = db_estoque.query(Insumo).order_by(Insumo.nome).all()

        if not produtos_ft or not insumos_ft:
            st.warning("⚠️ Você precisa ter pelo menos um Produto e um Insumo cadastrados.")
        else:
            prato_escolhido = st.selectbox("🎯 Selecione o Prato ou Marmita para Montar/Editar:", produtos_ft, format_func=lambda p: f"[{p.categoria}] {p.nome} — R$ {p.preco_venda:.2f}")

            if prato_escolhido:
                st.markdown("---")
                st.markdown(f"### 📝 Ingredientes da Receita: **{prato_escolhido.nome}**")
                vinc_existentes = {f.insumo_id: f.quantidade_utilizada for f in db_estoque.query(FichaTecnica).filter(FichaTecnica.produto_id == prato_escolhido.id).all()}

                with st.form("form_ft_massa"):
                    quantidades_inputs = {}
                    cols_form = st.columns(3)
                    for idx, ins in enumerate(insumos_ft):
                        with cols_form[idx % 3]:
                            val_atual = vinc_existentes.get(ins.id, 0.0)
                            quantidades_inputs[ins.id] = st.number_input(
                                f"📦 {ins.nome} ({ins.unidade_medida})",
                                min_value=0.0,
                                value=float(val_atual),
                                step=0.05,
                                format="%.2f",
                                key=f"ins_input_{ins.id}"
                            )

                    st.markdown("---")
                    btn_salvar_massa = st.form_submit_button("💾 Salvar Receita Completa em 1 Clique", type="primary", use_container_width=True)

                if btn_salvar_massa:
                    try:
                        db_estoque.query(FichaTecnica).filter(FichaTecnica.produto_id == prato_escolhido.id).delete()
                        novas_fichas = [FichaTecnica(produto_id=prato_escolhido.id, insumo_id=ins_id, quantidade_utilizada=qtd_val) for ins_id, qtd_val in quantidades_inputs.items() if qtd_val > 0]
                        if novas_fichas:
                            db_estoque.add_all(novas_fichas)
                        db_estoque.commit()
                        recalcular_cmv_geral(db_estoque)
                        st.success(f"🎉 Receita do **{prato_escolhido.nome}** atualizada! O CMV foi reajustado em tempo real.")
                        st.rerun()
                    except Exception as e:
                        db_estoque.rollback()
                        st.error(f"❌ Erro ao salvar receita em massa: {e}")

            st.markdown("---")
            st.subheader("📖 Fichas Técnicas Cadastradas no Sistema")
            fichas_cadastradas = db_estoque.query(FichaTecnica).all()
            if fichas_cadastradas:
                dados_ft_lista = [{"Prato": f.produto.nome if f.produto else "-", "Insumo": f.insumo.nome if f.insumo else "-", "Consumo": f"{f.quantidade_utilizada} {f.insumo.unidade_medida if f.insumo else ''}"} for f in fichas_cadastradas]
                st.dataframe(pd.DataFrame(dados_ft_lista), use_container_width=True, hide_index=True)

    with sub_aba4:
        st.subheader("🧾 Entrada Automática via Foto de Nota Fiscal (I.A. Vision)")
        st.write("Suba a foto da Nota Fiscal / Cupom do fornecedor. A inteligência artificial extrairá os itens, cruzará com o almoxarifado e recalculará o CMV de todos os pratos!")

        col_up, col_vis = st.columns([1, 2])
        with col_up:
            arquivo_nf = st.file_uploader("📸 Tire uma foto ou suba o cupom fiscal (JPG/PNG)", type=["jpg", "jpeg", "png"])
            btn_processar_nf = st.button("🚀 Ler Nota com Inteligência Artificial", type="primary", use_container_width=True)

        if arquivo_nf:
            with col_vis:
                st.image(arquivo_nf, caption="Nota Fiscal Carregada", width=300)

        if btn_processar_nf:
            if not arquivo_nf:
                st.error("⚠️ Por favor, suba uma imagem da Nota Fiscal primeiro!")
            elif not GENAI_DISPONIVEL:
                st.error("❌ A chave de API do Google Gemini precisa estar ativa para usar a Visão Computacional!")
            else:
                with st.spinner("🤖 O Google Gemini está analisando os itens e preços na nota fiscal..."):
                    try:
                        img_pil = Image.open(arquivo_nf)
                        model_vision = genai.GenerativeModel("gemini-1.5-flash")
                        
                        prompt_ocr = """
                        Você é um auditor de estoque de restaurante. Analise a foto desta nota fiscal ou cupom.
                        Extraia os itens de mercadoria/alimentos comprados e retorne APENAS um bloco JSON no seguinte formato:
                        [
                          {"item": "Nome do produto na nota", "qtd": 10.0, "unidade": "kg", "preco_unitario": 35.00}
                        ]
                        Ajuste as unidades para 'un', 'kg', 'g', 'fatias' ou 'litros' conforme o padrão gastronômico. 
                        NÃO escreva nada antes ou depois do JSON. Retorne apenas o JSON puro.
                        """
                        
                        resposta_ocr = model_vision.generate_content([prompt_ocr, img_pil])
                        
                        if resposta_ocr and resposta_ocr.text:
                            texto_limpo = resposta_ocr.text.replace("```json", "").replace("```", "").strip()
                            itens_extraidos = json.loads(texto_limpo)
                            st.session_state["nf_itens_pendentes"] = itens_extraidos
                            st.success("✅ Nota Fiscal lida com sucesso! Confira os dados abaixo antes de integrar:")
                    except Exception as e:
                        st.error(f"❌ Erro ao processar imagem com a IA: {e}")

        if "nf_itens_pendentes" in st.session_state and st.session_state["nf_itens_pendentes"]:
            st.markdown("---")
            st.subheader("🕵️ Conciliação e Cruzamento com o Banco de Dados")
            
            insumos_banco = db_estoque.query(Insumo).all()
            opcoes_insumos = {i.nome: i for i in insumos_banco}
            nomes_opcoes = ["-- Ignorar / Novo Item --"] + list(opcoes_insumos.keys())

            itens_para_integrar = []
            
            with st.form("form_conciliacao_nf"):
                for index, item_nf in enumerate(st.session_state["nf_itens_pendentes"]):
                    st.markdown(f"**Item lido pela IA:** `{item_nf.get('item')}` | Qtd: **{item_nf.get('qtd')} {item_nf.get('unidade')}** | Preço Unit.: **R$ {item_nf.get('preco_unitario', 0.0):.2f}**")
                    
                    match_padrao = 0
                    for idx_op, nome_banco in enumerate(nomes_opcoes):
                        if any(palavra.lower() in nome_banco.lower() for palavra in str(item_nf.get('item')).split() if len(palavra) > 3):
                            match_padrao = idx_op
                            break
                    
                    c1, c2, c3 = st.columns([2, 1, 1])
                    with c1:
                        vinc_ins = st.selectbox("Vincular ao Insumo do Estoque:", nomes_opcoes, index=match_padrao, key=f"sel_nf_{index}")
                    with c2:
                        qtd_final = st.number_input("Quantidade de Entrada", value=float(item_nf.get("qtd", 0.0)), step=1.0, key=f"qtd_nf_{index}")
                    with c3:
                        custo_final = st.number_input("Novo Custo Unitário (R$)", value=float(item_nf.get("preco_unitario", 0.0)), step=0.10, format="%.2f", key=f"custo_nf_{index}")
                    
                    if vinc_ins != "-- Ignorar / Novo Item --":
                        itens_para_integrar.append({
                            "insumo_id": opcoes_insumos[vinc_ins].id,
                            "qtd": qtd_final,
                            "novo_custo": custo_final
                        })
                    st.divider()

                btn_confirmar_nf = st.form_submit_button("📦 Confirmar Entrada & Recalcular CMV do Cardápio", type="primary", use_container_width=True)

            if btn_confirmar_nf:
                if not itens_para_integrar:
                    st.warning("Nenhum item foi vinculado ao almoxarifado para integração.")
                else:
                    try:
                        for integracao in itens_para_integrar:
                            ins_atual = db_estoque.query(Insumo).filter(Insumo.id == integracao["insumo_id"]).first()
                            if ins_atual:
                                ins_atual.saldo_atual += integracao["qtd"]
                                ins_atual.custo_unitario = integracao["novo_custo"]
                        
                        db_estoque.commit()
                        recalcular_cmv_geral(db_estoque)
                        del st.session_state["nf_itens_pendentes"]
                        st.success("🎉 Estoque reabastecido e preços unitários atualizados! O CMV de todos os pratos foi reajustado automaticamente no cardápio.")
                        st.rerun()
                    except Exception as e:
                        db_estoque.rollback()
                        st.error(f"❌ Erro ao integrar nota ao banco de dados: {e}")

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
        df_g = pd.DataFrame([{"Produto": v.produto.nome if v.produto else "Item", "Total": v.valor_total} for v in todas_vendas])
        st.bar_chart(df_g.groupby("Produto")["Total"].sum().reset_index(), x="Produto", y="Total", use_container_width=True)