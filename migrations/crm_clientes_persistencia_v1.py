"""Persistência canônica dos clientes CRM V1.

O ClienteCRM pertence explicitamente ao escopo tenant/unidade.
Contatos são referências seguras (contact:// ou vault://), nunca dados
sensíveis copiados diretamente da tabela legada clientes.

Esta migration é aditiva e não realiza backfill automático.
Clientes históricos exigem regularização governada.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

_CLIENTES = "crm_clientes_v1"
_CONTATOS = "crm_cliente_contatos_v1"


def upgrade_crm_clientes_persistencia_v1(connection: Connection) -> None:
    tabelas = set(inspect(connection).get_table_names())

    if _CLIENTES not in tabelas:
        connection.execute(
            text(
                """
                CREATE TABLE crm_clientes_v1 (
                    tenant_id VARCHAR(64) NOT NULL,
                    unidade_id VARCHAR(64) NOT NULL,
                    cliente_id VARCHAR(64) NOT NULL,
                    origem VARCHAR(32) NOT NULL,
                    marketplace_origem VARCHAR(32),
                    criado_em TIMESTAMP NOT NULL,
                    versao INTEGER NOT NULL DEFAULT 1,

                    CONSTRAINT pk_crm_clientes_v1
                        PRIMARY KEY (
                            tenant_id,
                            unidade_id,
                            cliente_id
                        ),

                    CONSTRAINT ck_crm_clientes_versao_v1
                        CHECK (versao >= 1)
                )
                """
            )
        )

    tabelas = set(inspect(connection).get_table_names())

    if _CONTATOS not in tabelas:
        connection.execute(
            text(
                """
                CREATE TABLE crm_cliente_contatos_v1 (
                    tenant_id VARCHAR(64) NOT NULL,
                    unidade_id VARCHAR(64) NOT NULL,
                    cliente_id VARCHAR(64) NOT NULL,
                    canal VARCHAR(32) NOT NULL,
                    referencia VARCHAR(512) NOT NULL,

                    CONSTRAINT pk_crm_cliente_contatos_v1
                        PRIMARY KEY (
                            tenant_id,
                            unidade_id,
                            cliente_id,
                            canal
                        ),

                    CONSTRAINT fk_crm_cliente_contatos_cliente_v1
                        FOREIGN KEY (
                            tenant_id,
                            unidade_id,
                            cliente_id
                        )
                        REFERENCES crm_clientes_v1 (
                            tenant_id,
                            unidade_id,
                            cliente_id
                        )
                        ON DELETE CASCADE,

                    CONSTRAINT ck_crm_cliente_contato_referencia_v1
                        CHECK (
                            referencia LIKE 'contact://%'
                            OR referencia LIKE 'vault://%'
                        )
                )
                """
            )
        )

    indexes_clientes = {
        indice["name"]
        for indice in inspect(connection).get_indexes(_CLIENTES)
    }

    if "ix_crm_clientes_scope_v1" not in indexes_clientes:
        connection.execute(
            text(
                """
                CREATE INDEX ix_crm_clientes_scope_v1
                ON crm_clientes_v1 (
                    tenant_id,
                    unidade_id,
                    criado_em
                )
                """
            )
        )

    indexes_contatos = {
        indice["name"]
        for indice in inspect(connection).get_indexes(_CONTATOS)
    }

    if "ix_crm_cliente_contatos_scope_v1" not in indexes_contatos:
        connection.execute(
            text(
                """
                CREATE INDEX ix_crm_cliente_contatos_scope_v1
                ON crm_cliente_contatos_v1 (
                    tenant_id,
                    unidade_id,
                    cliente_id
                )
                """
            )
        )
