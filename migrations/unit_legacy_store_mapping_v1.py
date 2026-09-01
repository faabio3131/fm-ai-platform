"""Mapeamento canônico entre tenant/unidade V1 e a loja legada.

A tabela ``lojas`` pertence ao schema histórico e não possui tenant_id/unidade_id.
Nenhum código novo pode inferir esse vínculo pela quantidade de lojas existentes.

Esta migration cria uma ponte explícita, aditiva e governada.
Não realiza backfill automático: associações históricas exigem evidência determinística.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

_TABLE = "fm_unidade_loja_legacy_v1"


def upgrade_unit_legacy_store_mapping_v1(connection: Connection) -> None:
    inspector = inspect(connection)

    if "lojas" not in inspector.get_table_names():
        raise RuntimeError(
            "tabela lojas ausente antes da migration de mapeamento unidade/loja"
        )

    if _TABLE not in inspector.get_table_names():
        connection.execute(
            text(
                """
                CREATE TABLE fm_unidade_loja_legacy_v1 (
                    tenant_id VARCHAR(64) NOT NULL,
                    unidade_id VARCHAR(64) NOT NULL,
                    loja_id INTEGER NOT NULL,
                    ativo BOOLEAN NOT NULL DEFAULT TRUE,
                    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

                    CONSTRAINT pk_fm_unidade_loja_legacy_v1
                        PRIMARY KEY (tenant_id, unidade_id),

                    CONSTRAINT uq_fm_unidade_loja_legacy_loja_v1
                        UNIQUE (loja_id),

                    CONSTRAINT fk_fm_unidade_loja_legacy_loja_v1
                        FOREIGN KEY (loja_id)
                        REFERENCES lojas(id)
                )
                """
            )
        )

    indexes = {
        index["name"]
        for index in inspect(connection).get_indexes(_TABLE)
    }

    if "ix_fm_unidade_loja_legacy_escopo_v1" not in indexes:
        connection.execute(
            text(
                """
                CREATE INDEX ix_fm_unidade_loja_legacy_escopo_v1
                ON fm_unidade_loja_legacy_v1
                (tenant_id, unidade_id, ativo)
                """
            )
        )
