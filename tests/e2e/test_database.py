from __future__ import annotations

import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import URL

SCHEMA = """
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

LEGACY_REQUIRED_TABLES = frozenset(
    {
        "usuarios",
        "clientes",
        "produtos",
        "insumos",
        "fichas_tecnicas",
        "vendas",
        "configuracoes_meta",
    }
)

KDS_CANONICAL_REQUIRED_TABLES = frozenset(
    {
        "pedidos_v1",
        "itens_pedido_v1",
        "adicionais_item_pedido_v1",
        "observacoes_pedido_v1",
        "eventos_pedido_v1",
        "setores_producao_v1",
        "producao_itens_v1",
        "eventos_producao_v1",
    }
)

KDS_CANONICAL_DELETE_ORDER = (
    "eventos_producao_v1",
    "producao_itens_v1",
    "setores_producao_v1",
    "eventos_pedido_v1",
    "observacoes_pedido_v1",
    "adicionais_item_pedido_v1",
    "itens_pedido_v1",
    "pedidos_v1",
)

DELETE_ORDER = (
    "fichas_tecnicas",
    "vendas",
    "gateway_config",
    "configuracoes_meta",
    "contatos_gerenciais",
    "produtos",
    "insumos",
    "clientes",
    "usuarios",
)


def _kds_schema_enabled() -> bool:
    return (
        os.environ.get("FM_AI_TEST_MODE") == "1"
        and os.environ.get("FM_AI_KDS_V1") == "1"
    )


def required_tables() -> frozenset[str]:
    if _kds_schema_enabled():
        return LEGACY_REQUIRED_TABLES | KDS_CANONICAL_REQUIRED_TABLES
    return LEGACY_REQUIRED_TABLES


def _prepare_canonical_schema_if_enabled(db_path: Path) -> None:
    if not _kds_schema_enabled():
        return

    project_root = str(Path(__file__).resolve().parents[2])
    added_project_root = project_root not in sys.path
    if added_project_root:
        sys.path.insert(0, project_root)
    try:
        from core.kds import preparar_schema_teste
    finally:
        if added_project_root:
            sys.path.remove(project_root)

    engine = create_engine(URL.create("sqlite", database=str(db_path)))
    try:
        preparar_schema_teste(engine)
    finally:
        engine.dispose()


def _validate_required_schema(cursor: sqlite3.Cursor) -> None:
    existing = {
        row[0]
        for row in cursor.execute("select name from sqlite_master where type='table'")
    }
    missing = sorted(required_tables() - existing)
    if missing:
        raise RuntimeError(f"Schema de teste incompleto; tabelas ausentes: {missing}")


def seed_database(cursor: sqlite3.Cursor) -> None:
    """Restore the complete E2E fixture with stable primary keys."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    cursor.execute(
        "insert into usuarios (id, email, senha_hash) values (1, ?, ?)",
        ("admin.test@fm.ai", "test-only"),
    )
    cursor.execute(
        "insert into clientes (id, nome, whatsapp, ultima_compra, total_gasto, saldo_cashback, status) values (1, ?, ?, ?, ?, ?, ?)",
        (
            "Cliente Teste",
            "5511999990001",
            (now - timedelta(days=30)).isoformat(),
            100,
            10,
            "Inativo",
        ),
    )
    cursor.execute(
        "insert into produtos (id, nome, categoria, preco_venda, custo_total_cmv, margem_exibicao) values (1, ?, ?, ?, ?, ?)",
        ("Burger Teste", "Hambúrgueres", 29.90, 9.0, "69.9%"),
    )
    cursor.executemany(
        "insert into insumos (id, nome, unidade_medida, saldo_atual, estoque_minimo, custo_unitario, data_fabricacao, data_validade, dias_alerta_vencimento) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                1,
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
                2,
                "Pão Teste",
                "un",
                50,
                5,
                2,
                None,
                (now + timedelta(days=5)).isoformat(),
                7,
            ),
        ],
    )
    cursor.executemany(
        "insert into fichas_tecnicas (id, produto_id, insumo_id, quantidade_utilizada) values (?, 1, ?, 1)",
        [(1, 1), (2, 2)],
    )
    cursor.execute(
        "insert into vendas (id, produto_id, cliente_id, quantidade, valor_total, custo_total, forma_pagamento, status_pagamento, data_venda) values (1, 1, 1, 1, 29.90, 9.0, ?, ?, ?)",
        ("Dinheiro Em Espécie", "Aprovado", now.isoformat()),
    )
    cursor.execute(
        "insert into configuracoes_meta (id, gateway_provider, gateway_pix_key, gateway_api_key) values (1, ?, ?, ?)",
        ("Mercado Pago", "sandbox-pix", None),
    )
    cursor.execute(
        "insert into gateway_config (id, gateway_provider, gateway_pix_key, gateway_api_key, ambiente) values (1, ?, ?, ?, ?)",
        ("Mercado Pago", "sandbox-pix", None, "Sandbox"),
    )
    cursor.execute(
        "insert into contatos_gerenciais (id, nome, whatsapp, cargo, receber_alertas_estoque) values (1, ?, ?, ?, ?)",
        ("Gerente Teste", "5511999990002", "Gerente", 1),
    )


def validate_foreign_keys(cursor: sqlite3.Cursor) -> None:
    violations = cursor.execute("pragma foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(
            f"Banco E2E contém violações de chave estrangeira: {violations}"
        )


def initialize_database(db_path: Path) -> None:
    """Create a fresh database before the Streamlit server starts."""
    if db_path.exists():
        db_path.unlink()
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()
    try:
        cursor.executescript(SCHEMA)
        seed_database(cursor)
        validate_foreign_keys(cursor)
        connection.commit()
    finally:
        cursor.close()
        connection.close()

    _prepare_canonical_schema_if_enabled(db_path)

    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()
    try:
        _validate_required_schema(cursor)
        validate_foreign_keys(cursor)
    finally:
        cursor.close()
        connection.close()


def reset_database_in_place(
    db_path: Path, *, attempts: int = 4, retry_delay: float = 0.2
) -> None:
    """Reset an active E2E database without replacing its Windows file handle."""
    _prepare_canonical_schema_if_enabled(db_path)
    delete_order = (
        KDS_CANONICAL_DELETE_ORDER + DELETE_ORDER
        if _kds_schema_enabled()
        else DELETE_ORDER
    )
    for attempt in range(1, attempts + 1):
        connection = sqlite3.connect(db_path, timeout=0)
        cursor = connection.cursor()
        try:
            cursor.execute("pragma foreign_keys = on")
            cursor.execute("begin immediate")
            for table in delete_order:
                cursor.execute(f'delete from "{table}"')
            seed_database(cursor)
            _validate_required_schema(cursor)
            validate_foreign_keys(cursor)
            connection.commit()
            return
        except sqlite3.OperationalError as error:
            connection.rollback()
            if "database is locked" not in str(error).lower() or attempt == attempts:
                raise
        finally:
            cursor.close()
            connection.close()
        time.sleep(retry_delay)
