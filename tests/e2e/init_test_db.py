from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TMPDIR = Path(os.environ["FM_AI_TEST_TMPDIR"]).resolve()
DB_PATH = TMPDIR / "fm_ai_test.sqlite3"
REAL_DB = ROOT / "banco_erp_local.db"

if DB_PATH.resolve() == REAL_DB.resolve():
    raise RuntimeError(f"Banco de teste resolveu para o banco real: {DB_PATH}")

TMPDIR.mkdir(parents=True, exist_ok=True)
if DB_PATH.exists():
    DB_PATH.unlink()


def initialize_database() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.executescript(
            """
            create table usuarios (id integer primary key, email varchar unique, senha_hash varchar);
            create table clientes (id integer primary key, nome varchar, whatsapp varchar unique, ultima_compra datetime, total_gasto float, saldo_cashback float, status varchar);
            create table produtos (id integer primary key, nome varchar, categoria varchar, descricao_bruta text, descricao_ai text, preco_venda float, custo_total_cmv float, margem_exibicao varchar, imagem_path varchar);
            create table insumos (id integer primary key, nome varchar unique, unidade_medida varchar, saldo_atual float, estoque_minimo float, custo_unitario float, data_fabricacao datetime, data_validade datetime, dias_alerta_vencimento integer);
            create table fichas_tecnicas (id integer primary key, produto_id integer not null, insumo_id integer not null, quantidade_utilizada float not null);
            create table vendas (id integer primary key, produto_id integer not null, cliente_id integer, quantidade integer not null, valor_total float not null, custo_total float not null, forma_pagamento varchar, status_pagamento varchar, data_venda datetime);
            create table gateway_config (id integer primary key, gateway_provider varchar(50), gateway_api_key varchar(255), gateway_pix_key varchar(100), ambiente varchar(20));
            create table configuracoes_meta (id integer primary key, meta_access_token varchar, facebook_page_id varchar, instagram_account_id varchar, whatsapp_token varchar, whatsapp_phone_id varchar, gateway_provider varchar, gateway_pix_key varchar, gateway_api_key varchar);
            create table contatos_gerenciais (id integer primary key, nome varchar, whatsapp varchar unique, cargo varchar, receber_alertas_estoque integer);
            """
        )
        now = datetime.now()
        cur.execute(
            "insert into usuarios (email, senha_hash) values (?, ?)",
            ("admin.test@fm.ai", "test-only"),
        )
        cur.execute(
            "insert into clientes (nome, whatsapp, ultima_compra, total_gasto, saldo_cashback, status) values (?, ?, ?, ?, ?, ?)",
            (
                "Cliente Teste",
                "5511999990001",
                (now - timedelta(days=30)).isoformat(),
                100,
                10,
                "Inativo",
            ),
        )
        cur.execute(
            "insert into produtos (nome, categoria, preco_venda, custo_total_cmv, margem_exibicao) values (?, ?, ?, ?, ?)",
            ("Burger Teste", "Hambúrgueres", 29.90, 9.0, "69.9%"),
        )
        produto_id = cur.lastrowid
        insumos = [
            (
                "Carne Teste",
                "un",
                50,
                5,
                7,
                None,
                (now + timedelta(days=20)).isoformat(),
                15,
            ),
            (
                "Pão Teste",
                "un",
                50,
                5,
                2,
                None,
                (now + timedelta(days=5)).isoformat(),
                7,
            ),
        ]
        cur.executemany(
            "insert into insumos (nome, unidade_medida, saldo_atual, estoque_minimo, custo_unitario, data_fabricacao, data_validade, dias_alerta_vencimento) values (?, ?, ?, ?, ?, ?, ?, ?)",
            insumos,
        )
        cur.execute(
            "insert into fichas_tecnicas (produto_id, insumo_id, quantidade_utilizada) values (?, 1, 1)",
            (produto_id,),
        )
        cur.execute(
            "insert into fichas_tecnicas (produto_id, insumo_id, quantidade_utilizada) values (?, 2, 1)",
            (produto_id,),
        )
        cur.execute(
            "insert into vendas (produto_id, cliente_id, quantidade, valor_total, custo_total, forma_pagamento, status_pagamento, data_venda) values (?, 1, 1, 29.90, 9.0, ?, ?, ?)",
            (produto_id, "Dinheiro Em Espécie", "Aprovado", now.isoformat()),
        )
        cur.execute(
            "insert into configuracoes_meta (gateway_provider, gateway_pix_key, gateway_api_key) values (?, ?, ?)",
            ("Mercado Pago", "sandbox-pix", None),
        )
        cur.execute(
            "insert into gateway_config (gateway_provider, gateway_pix_key, gateway_api_key, ambiente) values (?, ?, ?, ?)",
            ("Mercado Pago", "sandbox-pix", None, "Sandbox"),
        )
        cur.execute(
            "insert into contatos_gerenciais (nome, whatsapp, cargo, receber_alertas_estoque) values (?, ?, ?, ?)",
            ("Gerente Teste", "5511999990002", "Gerente", 1),
        )
        conn.commit()
    finally:
        conn.close()


initialize_database()

required = {
    "usuarios",
    "clientes",
    "produtos",
    "insumos",
    "fichas_tecnicas",
    "vendas",
    "configuracoes_meta",
}
conn = sqlite3.connect(DB_PATH)
try:
    existing = {
        row[0]
        for row in conn.execute("select name from sqlite_master where type='table'")
    }
    missing = sorted(required - existing)
    if missing:
        raise RuntimeError(f"Schema de teste incompleto; tabelas ausentes: {missing}")
finally:
    conn.close()

if not DB_PATH.exists() or DB_PATH.stat().st_size <= 0:
    raise RuntimeError(f"Banco temporário não ficou pronto: {DB_PATH}")

print(DB_PATH)
