"""Baseline aditivo e imutável da tabela de lojas legadas.

Instalações antigas já podem possuir ``lojas``. Instalações novas precisam da
mesma dependência estrutural antes que a migration de vínculo unidade/loja crie
sua foreign key. A migration não altera tabelas existentes: apenas valida o
contrato mínimo necessário ou cria a estrutura ausente.
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, MetaData, String, Table, inspect
from sqlalchemy.engine import Connection

_metadata = MetaData()

lojas_legacy_v1 = Table(
    "lojas",
    _metadata,
    Column("id", Integer, primary_key=True),
    Column("nome_fantasia", String(255), nullable=False),
)


def upgrade_legacy_store_baseline_v1(connection: Connection) -> None:
    """Cria a dependência de 0021 ou valida um baseline legado compatível."""

    inspector = inspect(connection)

    if "lojas" not in inspector.get_table_names():
        lojas_legacy_v1.create(bind=connection, checkfirst=True)
        return

    columns = {column["name"] for column in inspector.get_columns("lojas")}
    missing = {"id", "nome_fantasia"} - columns

    if missing:
        raise RuntimeError(
            "tabela lojas existente possui colunas obrigatorias ausentes: "
            + ", ".join(sorted(missing))
        )

    primary_key = list(
        inspector.get_pk_constraint("lojas").get("constrained_columns") or []
    )

    if primary_key != ["id"]:
        raise RuntimeError("tabela lojas existente possui primary key divergente")
