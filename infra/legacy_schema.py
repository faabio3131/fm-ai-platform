"""Schema relacional legado ainda consumido pelo app.py durante a migração V1.

A definição aqui existe para que produção crie/verifique essas tabelas por migration
versionada, sem depender do ``Base.metadata.create_all`` do módulo Streamlit.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    text,
)

legacy_metadata = MetaData()

usuarios = Table(
    "usuarios",
    legacy_metadata,
    Column("id", Integer, primary_key=True, index=True),
    Column("email", String, unique=True, index=True),
    Column("senha_hash", String),
)

clientes = Table(
    "clientes",
    legacy_metadata,
    Column("id", Integer, primary_key=True, index=True),
    Column("nome", String, index=True),
    Column("whatsapp", String, unique=True, index=True),
    Column("ultima_compra", DateTime),
    Column("total_gasto", Float),
    Column("saldo_cashback", Float),
    Column("status", String),
)

produtos = Table(
    "produtos",
    legacy_metadata,
    Column("id", Integer, primary_key=True, index=True),
    Column("nome", String, index=True),
    Column("categoria", String),
    Column("descricao_bruta", Text),
    Column("descricao_ai", Text),
    Column("preco_venda", Float),
    Column("custo_total_cmv", Float),
    Column("margem_exibicao", String),
    Column("imagem_path", String, nullable=True),
)

insumos = Table(
    "insumos",
    legacy_metadata,
    Column("id", Integer, primary_key=True, index=True),
    Column("nome", String, unique=True, index=True),
    Column("unidade_medida", String),
    Column("saldo_atual", Float),
    Column("estoque_minimo", Float),
    Column("custo_unitario", Float),
    Column("data_fabricacao", DateTime, nullable=True),
    Column("data_validade", DateTime, nullable=True),
    Column(
        "dias_alerta_vencimento",
        Integer,
        nullable=False,
        server_default=text("15"),
    ),
)

fichas_tecnicas = Table(
    "fichas_tecnicas",
    legacy_metadata,
    Column("id", Integer, primary_key=True, index=True),
    Column("produto_id", ForeignKey("produtos.id"), nullable=False),
    Column("insumo_id", ForeignKey("insumos.id"), nullable=False),
    Column("quantidade_utilizada", Float, nullable=False),
)

vendas = Table(
    "vendas",
    legacy_metadata,
    Column("id", Integer, primary_key=True, index=True),
    Column("produto_id", ForeignKey("produtos.id"), nullable=False),
    Column("cliente_id", ForeignKey("clientes.id"), nullable=True),
    Column("quantidade", Integer, nullable=False),
    Column("valor_total", Float, nullable=False),
    Column("custo_total", Float, nullable=False),
    Column("forma_pagamento", String),
    Column("status_pagamento", String),
    Column("data_venda", DateTime),
)

gateway_config = Table(
    "gateway_config",
    legacy_metadata,
    Column("id", Integer, primary_key=True),
    Column("gateway_provider", String(50)),
    Column("gateway_api_key", String(255), nullable=True),
    Column("gateway_pix_key", String(100), nullable=True),
    Column("ambiente", String(20)),
)

configuracoes_meta = Table(
    "configuracoes_meta",
    legacy_metadata,
    Column("id", Integer, primary_key=True, index=True),
    Column("meta_access_token", String, nullable=True),
    Column("facebook_page_id", String, nullable=True),
    Column("instagram_account_id", String, nullable=True),
    Column("whatsapp_token", String, nullable=True),
    Column("whatsapp_phone_id", String, nullable=True),
    Column("gateway_provider", String),
    Column("gateway_pix_key", String, nullable=True),
    Column("gateway_api_key", String, nullable=True),
)

contatos_gerenciais = Table(
    "contatos_gerenciais",
    legacy_metadata,
    Column("id", Integer, primary_key=True, index=True),
    Column("nome", String),
    Column("whatsapp", String, unique=True, index=True),
    Column("cargo", String),
    Column("receber_alertas_estoque", Integer),
)
