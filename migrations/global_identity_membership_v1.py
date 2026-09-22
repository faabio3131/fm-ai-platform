"""Migration 0050 — identidade global e memberships KCA-02."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from sqlalchemy import Table, inspect, select
from sqlalchemy.engine import Connection

from infra.seguranca.modelos_orm import (
    GlobalIdentityBase,
    IdentityMembershipORM,
    IdentityMembershipRoleORM,
    IdentityMembershipUnitORM,
    IdentityUserORM,
    UsuarioPapelORM,
    UsuarioSegurancaORM,
    UsuarioUnidadeORM,
)


def upgrade_global_identity_membership_v1(connection: Connection) -> None:
    GlobalIdentityBase.metadata.create_all(bind=connection, checkfirst=True)
    if not inspect(connection).has_table("fm_usuarios_v1"):
        return

    agora = datetime.now(timezone.utc)
    usuarios = connection.execute(
        select(
            UsuarioSegurancaORM.usuario_id,
            UsuarioSegurancaORM.email,
            UsuarioSegurancaORM.senha_hash,
            UsuarioSegurancaORM.admin_pin_hash,
            UsuarioSegurancaORM.acesso_admin_sensivel,
            UsuarioSegurancaORM.tenant_id,
            UsuarioSegurancaORM.unidade_padrao_id,
            UsuarioSegurancaORM.ativo,
            UsuarioSegurancaORM.criado_em,
            UsuarioSegurancaORM.atualizado_em,
        )
    ).all()

    for usuario in usuarios:
        identity_user_id = str(usuario.usuario_id)
        membership_id = str(usuario.usuario_id)

        identidade_existe = connection.scalar(
            select(IdentityUserORM.identity_user_id).where(
                IdentityUserORM.identity_user_id == identity_user_id
            )
        )
        if identidade_existe is None:
            connection.execute(
                cast(Table, IdentityUserORM.__table__).insert().values(
                    identity_user_id=identity_user_id,
                    email=str(usuario.email).strip().casefold(),
                    senha_hash=str(usuario.senha_hash),
                    admin_pin_hash=usuario.admin_pin_hash,
                    ativo=bool(usuario.ativo),
                    criado_em=usuario.criado_em or agora,
                    atualizado_em=usuario.atualizado_em or agora,
                )
            )

        membership_existe = connection.scalar(
            select(IdentityMembershipORM.membership_id).where(
                IdentityMembershipORM.membership_id == membership_id
            )
        )
        if membership_existe is None:
            connection.execute(
                cast(Table, IdentityMembershipORM.__table__).insert().values(
                    membership_id=membership_id,
                    identity_user_id=identity_user_id,
                    product_code="KORDENA",
                    tenant_id=str(usuario.tenant_id),
                    unidade_padrao_id=str(usuario.unidade_padrao_id),
                    ativo=bool(usuario.ativo),
                    acesso_admin_sensivel=bool(usuario.acesso_admin_sensivel),
                    padrao=True,
                    legacy_usuario_id=str(usuario.usuario_id),
                    criado_em=usuario.criado_em or agora,
                    atualizado_em=usuario.atualizado_em or agora,
                )
            )

        papeis = connection.scalars(
            select(UsuarioPapelORM.papel).where(
                UsuarioPapelORM.usuario_id == usuario.usuario_id
            )
        ).all()
        for papel in papeis:
            existe = connection.scalar(
                select(IdentityMembershipRoleORM.id).where(
                    IdentityMembershipRoleORM.membership_id == membership_id,
                    IdentityMembershipRoleORM.papel == str(papel),
                )
            )
            if existe is None:
                connection.execute(
                    cast(Table, IdentityMembershipRoleORM.__table__).insert().values(
                        membership_id=membership_id,
                        papel=str(papel),
                    )
                )

        unidades = connection.scalars(
            select(UsuarioUnidadeORM.unidade_id).where(
                UsuarioUnidadeORM.usuario_id == usuario.usuario_id
            )
        ).all()
        unidades_normalizadas = {
            str(unidade).strip() for unidade in unidades if str(unidade).strip()
        }
        unidades_normalizadas.add(str(usuario.unidade_padrao_id))
        for unidade_id in sorted(unidades_normalizadas):
            existe = connection.scalar(
                select(IdentityMembershipUnitORM.id).where(
                    IdentityMembershipUnitORM.membership_id == membership_id,
                    IdentityMembershipUnitORM.unidade_id == unidade_id,
                )
            )
            if existe is None:
                connection.execute(
                    cast(Table, IdentityMembershipUnitORM.__table__).insert().values(
                        membership_id=membership_id,
                        unidade_id=unidade_id,
                    )
                )
