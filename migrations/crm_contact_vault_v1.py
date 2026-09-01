"""Vault cifrado de contatos CRM por tenant/unidade.

Armazena dados de contato protegidos e expõe somente referências
`contact://...` ao domínio CRM.

Não realiza backfill automático de clientes legados.
"""

from __future__ import annotations

from sqlalchemy.engine import Connection

from infra.crm.contatos_orm import ContactVaultBase


def upgrade_crm_contact_vault_v1(connection: Connection) -> None:
    ContactVaultBase.metadata.create_all(
        bind=connection,
        checkfirst=True,
    )
