"""Persistência SQLAlchemy de identidade global e memberships KCA-02.

Mantém compatibilidade controlada com as tabelas fm_usuarios_v1 enquanto a
arquitetura operacional migra para identity_user + membership.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, inspect, select
from sqlalchemy.orm import Session

from core.seguranca.autenticacao import (
    IdentidadeUsuario,
    hash_admin_pin,
    hash_password,
    verify_admin_pin,
)
from core.seguranca.permissoes import Papel

from .modelos_orm import (
    IdentityMembershipORM,
    IdentityMembershipRoleORM,
    IdentityMembershipUnitORM,
    IdentityUserORM,
    UsuarioPapelORM,
    UsuarioSegurancaORM,
    UsuarioUnidadeORM,
)

_PRODUCT_CODE_KORDENA = "KORDENA"


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class RepositorioIdentidadesSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _global_disponivel(self) -> bool:
        bind = self._session.get_bind()
        return bool(bind is not None and inspect(bind).has_table("fm_identity_users_v1"))

    def _membership_para_identidade(
        self,
        membership: IdentityMembershipORM,
    ) -> IdentidadeUsuario:
        global_user = self._session.get(IdentityUserORM, membership.identity_user_id)
        if global_user is None:
            raise RuntimeError("identidade_global_ausente_para_membership")
        papeis_raw = self._session.scalars(
            select(IdentityMembershipRoleORM.papel).where(
                IdentityMembershipRoleORM.membership_id == membership.membership_id
            )
        ).all()
        unidades = frozenset(
            str(item)
            for item in self._session.scalars(
                select(IdentityMembershipUnitORM.unidade_id).where(
                    IdentityMembershipUnitORM.membership_id == membership.membership_id
                )
            ).all()
        )
        if not unidades:
            unidades = frozenset({membership.unidade_padrao_id})
        return IdentidadeUsuario(
            usuario_id=membership.membership_id,
            email=global_user.email,
            senha_hash=global_user.senha_hash,
            tenant_id=membership.tenant_id,
            unidade_id=membership.unidade_padrao_id,
            papeis=frozenset(Papel(valor) for valor in papeis_raw),
            unidades_permitidas=unidades,
            ativo=bool(global_user.ativo and membership.ativo),
            acesso_admin_sensivel=bool(membership.acesso_admin_sensivel),
            identity_user_id=global_user.identity_user_id,
            membership_id=membership.membership_id,
            product_code=membership.product_code,
        )

    def _legacy_por_email(self, email_normalizado: str) -> IdentidadeUsuario | None:
        usuario = self._session.scalar(
            select(UsuarioSegurancaORM).where(
                UsuarioSegurancaORM.email == email_normalizado.strip().casefold()
            )
        )
        if usuario is None:
            return None
        papeis_raw = self._session.scalars(
            select(UsuarioPapelORM.papel).where(
                UsuarioPapelORM.usuario_id == usuario.usuario_id
            )
        ).all()
        unidades = frozenset(
            self._session.scalars(
                select(UsuarioUnidadeORM.unidade_id).where(
                    UsuarioUnidadeORM.usuario_id == usuario.usuario_id
                )
            ).all()
        )
        if not unidades:
            unidades = frozenset({usuario.unidade_padrao_id})
        return IdentidadeUsuario(
            usuario_id=usuario.usuario_id,
            email=usuario.email,
            senha_hash=usuario.senha_hash,
            tenant_id=usuario.tenant_id,
            unidade_id=usuario.unidade_padrao_id,
            papeis=frozenset(Papel(valor) for valor in papeis_raw),
            unidades_permitidas=unidades,
            ativo=usuario.ativo,
            acesso_admin_sensivel=bool(usuario.acesso_admin_sensivel),
        )

    def _membership_por_id(
        self,
        membership_id: str,
    ) -> IdentityMembershipORM | None:
        if not self._global_disponivel():
            return None
        membership = self._session.get(IdentityMembershipORM, membership_id)
        if membership is not None:
            return membership
        return self._session.scalar(
            select(IdentityMembershipORM).where(
                IdentityMembershipORM.legacy_usuario_id == membership_id
            )
        )

    def listar_por_tenant(self, *, tenant_id: str) -> tuple[IdentidadeUsuario, ...]:
        tenant = tenant_id.strip()
        if not tenant:
            raise ValueError("tenant_id obrigatorio")
        if not self._global_disponivel():
            emails = self._session.scalars(
                select(UsuarioSegurancaORM.email)
                .where(UsuarioSegurancaORM.tenant_id == tenant)
                .order_by(UsuarioSegurancaORM.email)
            ).all()
            return tuple(
                identidade
                for email in emails
                if (identidade := self._legacy_por_email(str(email))) is not None
            )
        memberships = self._session.scalars(
            select(IdentityMembershipORM)
            .where(
                IdentityMembershipORM.tenant_id == tenant,
                IdentityMembershipORM.product_code == _PRODUCT_CODE_KORDENA,
            )
            .order_by(IdentityMembershipORM.membership_id)
        ).all()
        return tuple(self._membership_para_identidade(item) for item in memberships)

    def listar_memberships(
        self,
        *,
        identity_user_id: str,
        product_code: str = _PRODUCT_CODE_KORDENA,
    ) -> tuple[IdentidadeUsuario, ...]:
        identity_id = identity_user_id.strip()
        product = product_code.strip().upper()
        if not identity_id or not product:
            raise ValueError("identity_user_id e product_code obrigatorios")
        if not self._global_disponivel():
            legacy = self.obter_por_id(usuario_id=identity_id)
            return (legacy,) if legacy is not None else ()
        memberships = self._session.scalars(
            select(IdentityMembershipORM)
            .where(
                IdentityMembershipORM.identity_user_id == identity_id,
                IdentityMembershipORM.product_code == product,
            )
            .order_by(
                IdentityMembershipORM.padrao.desc(),
                IdentityMembershipORM.membership_id,
            )
        ).all()
        return tuple(self._membership_para_identidade(item) for item in memberships)

    def obter_por_id(self, *, usuario_id: str) -> IdentidadeUsuario | None:
        if self._global_disponivel():
            membership = self._membership_por_id(usuario_id.strip())
            if membership is not None:
                return self._membership_para_identidade(membership)
        usuario = self._session.get(UsuarioSegurancaORM, usuario_id)
        if usuario is None:
            return None
        return self._legacy_por_email(usuario.email)

    def obter_por_email(self, email_normalizado: str) -> IdentidadeUsuario | None:
        email = email_normalizado.strip().casefold()
        if self._global_disponivel():
            global_user = self._session.scalar(
                select(IdentityUserORM).where(IdentityUserORM.email == email)
            )
            if global_user is not None:
                membership = self._session.scalar(
                    select(IdentityMembershipORM)
                    .where(
                        IdentityMembershipORM.identity_user_id
                        == global_user.identity_user_id,
                        IdentityMembershipORM.product_code == _PRODUCT_CODE_KORDENA,
                        IdentityMembershipORM.ativo.is_(True),
                    )
                    .order_by(
                        IdentityMembershipORM.padrao.desc(),
                        IdentityMembershipORM.membership_id,
                    )
                )
                if membership is None:
                    return None
                return self._membership_para_identidade(membership)
        return self._legacy_por_email(email)

    def criar_usuario(
        self,
        *,
        email: str,
        password: str,
        tenant_id: str,
        unidade_padrao_id: str,
        papeis: Iterable[Papel],
        unidades_permitidas: Iterable[str] | None = None,
        usuario_id: str | None = None,
        admin_pin: str | None = None,
        acesso_admin_sensivel: bool = False,
    ) -> IdentidadeUsuario:
        normalizado = email.strip().casefold()
        if not normalizado or "@" not in normalizado:
            raise ValueError("email invalido")
        papeis_set = frozenset(papeis)
        if not papeis_set:
            raise ValueError("usuario sem papel")
        unidades = frozenset(
            u.strip()
            for u in (unidades_permitidas or (unidade_padrao_id,))
            if u.strip()
        )
        padrao = unidade_padrao_id.strip()
        tenant = tenant_id.strip()
        if not tenant or not padrao:
            raise ValueError("tenant/unidade obrigatorios")
        if padrao not in unidades:
            unidades = frozenset({*unidades, padrao})

        if self.obter_por_email(normalizado) is not None:
            raise ValueError("usuario ja cadastrado")

        uid = usuario_id or str(uuid4())
        senha_hash = hash_password(password)
        pin_hash = hash_admin_pin(admin_pin) if admin_pin is not None else None

        if self._global_disponivel():
            agora = _agora()
            self._session.add(
                IdentityUserORM(
                    identity_user_id=uid,
                    email=normalizado,
                    senha_hash=senha_hash,
                    admin_pin_hash=pin_hash,
                    ativo=True,
                    criado_em=agora,
                    atualizado_em=agora,
                )
            )
            self._session.flush()
            self._session.add(
                IdentityMembershipORM(
                    membership_id=uid,
                    identity_user_id=uid,
                    product_code=_PRODUCT_CODE_KORDENA,
                    tenant_id=tenant,
                    unidade_padrao_id=padrao,
                    ativo=True,
                    acesso_admin_sensivel=bool(acesso_admin_sensivel),
                    padrao=True,
                    legacy_usuario_id=uid,
                    criado_em=agora,
                    atualizado_em=agora,
                )
            )
            self._session.flush()
            self._session.add_all(
                [
                    IdentityMembershipRoleORM(
                        membership_id=uid,
                        papel=papel.value,
                    )
                    for papel in papeis_set
                ]
            )
            self._session.add_all(
                [
                    IdentityMembershipUnitORM(
                        membership_id=uid,
                        unidade_id=unidade,
                    )
                    for unidade in sorted(unidades)
                ]
            )

        self._session.add(
            UsuarioSegurancaORM(
                usuario_id=uid,
                email=normalizado,
                senha_hash=senha_hash,
                admin_pin_hash=pin_hash,
                acesso_admin_sensivel=bool(acesso_admin_sensivel),
                tenant_id=tenant,
                unidade_padrao_id=padrao,
                ativo=True,
            )
        )
        self._session.flush()
        self._session.add_all(
            [UsuarioPapelORM(usuario_id=uid, papel=papel.value) for papel in papeis_set]
        )
        self._session.add_all(
            [
                UsuarioUnidadeORM(usuario_id=uid, unidade_id=unidade)
                for unidade in sorted(unidades)
            ]
        )
        self._session.flush()
        identidade = self.obter_por_id(usuario_id=uid)
        if identidade is None:
            raise RuntimeError("falha ao reconstruir identidade persistida")
        return identidade

    def criar_membership_existente(
        self,
        *,
        identity_user_id: str,
        tenant_id: str,
        unidade_padrao_id: str,
        papeis: Iterable[Papel],
        unidades_permitidas: Iterable[str],
        product_code: str = _PRODUCT_CODE_KORDENA,
        membership_id: str | None = None,
        acesso_admin_sensivel: bool = False,
        padrao: bool = False,
    ) -> IdentidadeUsuario:
        if not self._global_disponivel():
            raise RuntimeError("global_identity_schema_ausente")
        identity_id = identity_user_id.strip()
        tenant = tenant_id.strip()
        product = product_code.strip().upper()
        unidade_padrao = unidade_padrao_id.strip()
        papeis_set = frozenset(papeis)
        unidades = frozenset(str(item).strip() for item in unidades_permitidas if str(item).strip())
        if (
            not identity_id
            or not tenant
            or not product
            or not unidade_padrao
            or not papeis_set
            or not unidades
            or unidade_padrao not in unidades
        ):
            raise ValueError("membership_invalida")
        global_user = self._session.get(IdentityUserORM, identity_id)
        if global_user is None:
            raise ValueError("identidade_global_inexistente")
        existente = self._session.scalar(
            select(IdentityMembershipORM).where(
                IdentityMembershipORM.identity_user_id == identity_id,
                IdentityMembershipORM.product_code == product,
                IdentityMembershipORM.tenant_id == tenant,
            )
        )
        if existente is not None:
            raise ValueError("membership_ja_cadastrada")

        mid = membership_id or str(uuid4())
        agora = _agora()
        if padrao:
            atuais = self._session.scalars(
                select(IdentityMembershipORM).where(
                    IdentityMembershipORM.identity_user_id == identity_id,
                    IdentityMembershipORM.product_code == product,
                )
            ).all()
            for item in atuais:
                item.padrao = False
                item.atualizado_em = agora
        elif not self._session.scalar(
            select(IdentityMembershipORM.membership_id).where(
                IdentityMembershipORM.identity_user_id == identity_id,
                IdentityMembershipORM.product_code == product,
            )
        ):
            padrao = True

        membership = IdentityMembershipORM(
            membership_id=mid,
            identity_user_id=identity_id,
            product_code=product,
            tenant_id=tenant,
            unidade_padrao_id=unidade_padrao,
            ativo=True,
            acesso_admin_sensivel=bool(acesso_admin_sensivel),
            padrao=bool(padrao),
            legacy_usuario_id=None,
            criado_em=agora,
            atualizado_em=agora,
        )
        self._session.add(membership)
        self._session.flush()
        self._session.add_all(
            [
                IdentityMembershipRoleORM(
                    membership_id=mid,
                    papel=papel.value,
                )
                for papel in papeis_set
            ]
        )
        self._session.add_all(
            [
                IdentityMembershipUnitORM(
                    membership_id=mid,
                    unidade_id=unidade,
                )
                for unidade in sorted(unidades)
            ]
        )
        self._session.flush()
        return self._membership_para_identidade(membership)

    def definir_membership_padrao(
        self,
        *,
        identity_user_id: str,
        membership_id: str,
    ) -> None:
        if not self._global_disponivel():
            raise RuntimeError("global_identity_schema_ausente")
        alvo = self._session.get(IdentityMembershipORM, membership_id)
        if alvo is None or alvo.identity_user_id != identity_user_id.strip():
            raise ValueError("membership_inexistente")
        agora = _agora()
        memberships = self._session.scalars(
            select(IdentityMembershipORM).where(
                IdentityMembershipORM.identity_user_id == alvo.identity_user_id,
                IdentityMembershipORM.product_code == alvo.product_code,
            )
        ).all()
        for item in memberships:
            item.padrao = item.membership_id == alvo.membership_id
            item.atualizado_em = agora
        self._session.flush()

    def _global_e_membership(
        self,
        *,
        usuario_id: str,
    ) -> tuple[IdentityUserORM, IdentityMembershipORM] | None:
        membership = self._membership_por_id(usuario_id)
        if membership is None:
            return None
        global_user = self._session.get(IdentityUserORM, membership.identity_user_id)
        if global_user is None:
            return None
        return global_user, membership

    def _legacy_do_membership(
        self,
        membership: IdentityMembershipORM,
    ) -> UsuarioSegurancaORM | None:
        if not membership.legacy_usuario_id:
            return None
        return self._session.get(UsuarioSegurancaORM, membership.legacy_usuario_id)

    def trocar_senha(self, *, usuario_id: str, nova_senha: str) -> None:
        novo_hash = hash_password(nova_senha)
        par = self._global_e_membership(usuario_id=usuario_id)
        if par is not None:
            global_user, membership = par
            global_user.senha_hash = novo_hash
            global_user.atualizado_em = _agora()
            legacy = self._legacy_do_membership(membership)
            if legacy is not None:
                legacy.senha_hash = novo_hash
            self._session.flush()
            return
        usuario = self._session.get(UsuarioSegurancaORM, usuario_id)
        if usuario is None:
            raise ValueError("usuario inexistente")
        usuario.senha_hash = novo_hash
        self._session.flush()

    def definir_pin_admin(self, *, usuario_id: str, novo_pin: str) -> None:
        novo_hash = hash_admin_pin(novo_pin)
        par = self._global_e_membership(usuario_id=usuario_id)
        if par is not None:
            global_user, membership = par
            global_user.admin_pin_hash = novo_hash
            global_user.atualizado_em = _agora()
            legacy = self._legacy_do_membership(membership)
            if legacy is not None:
                legacy.admin_pin_hash = novo_hash
            self._session.flush()
            return
        usuario = self._session.get(UsuarioSegurancaORM, usuario_id)
        if usuario is None:
            raise ValueError("usuario inexistente")
        usuario.admin_pin_hash = novo_hash
        self._session.flush()

    def definir_acesso_admin_sensivel(self, *, usuario_id: str, autorizado: bool) -> None:
        par = self._global_e_membership(usuario_id=usuario_id)
        if par is not None:
            _, membership = par
            membership.acesso_admin_sensivel = bool(autorizado)
            membership.atualizado_em = _agora()
            legacy = self._legacy_do_membership(membership)
            if legacy is not None:
                legacy.acesso_admin_sensivel = bool(autorizado)
            self._session.flush()
            return
        usuario = self._session.get(UsuarioSegurancaORM, usuario_id)
        if usuario is None:
            raise ValueError("usuario inexistente")
        usuario.acesso_admin_sensivel = bool(autorizado)
        self._session.flush()

    def possui_pin_admin(self, *, usuario_id: str) -> bool:
        par = self._global_e_membership(usuario_id=usuario_id)
        if par is not None:
            global_user, _ = par
            return bool(global_user.admin_pin_hash)
        usuario = self._session.get(UsuarioSegurancaORM, usuario_id)
        return bool(usuario is not None and usuario.admin_pin_hash)

    def verificar_pin_admin(self, *, usuario_id: str, pin: str) -> bool:
        par = self._global_e_membership(usuario_id=usuario_id)
        if par is not None:
            global_user, membership = par
            if not global_user.ativo or not membership.ativo:
                return False
            return verify_admin_pin(pin, global_user.admin_pin_hash)
        usuario = self._session.get(UsuarioSegurancaORM, usuario_id)
        if usuario is None or not usuario.ativo:
            return False
        return verify_admin_pin(pin, usuario.admin_pin_hash)

    def definir_papeis(self, *, usuario_id: str, papeis: Iterable[Papel]) -> None:
        papeis_set = frozenset(papeis)
        if not papeis_set:
            raise ValueError("usuario sem papel")
        par = self._global_e_membership(usuario_id=usuario_id)
        if par is not None:
            _, membership = par
            self._session.execute(
                delete(IdentityMembershipRoleORM).where(
                    IdentityMembershipRoleORM.membership_id == membership.membership_id
                )
            )
            self._session.add_all(
                [
                    IdentityMembershipRoleORM(
                        membership_id=membership.membership_id,
                        papel=papel.value,
                    )
                    for papel in papeis_set
                ]
            )
            legacy = self._legacy_do_membership(membership)
            if legacy is not None:
                self._session.execute(
                    delete(UsuarioPapelORM).where(
                        UsuarioPapelORM.usuario_id == legacy.usuario_id
                    )
                )
                self._session.add_all(
                    [
                        UsuarioPapelORM(
                            usuario_id=legacy.usuario_id,
                            papel=papel.value,
                        )
                        for papel in papeis_set
                    ]
                )
            self._session.flush()
            return
        self._session.execute(
            delete(UsuarioPapelORM).where(UsuarioPapelORM.usuario_id == usuario_id)
        )
        self._session.add_all(
            [
                UsuarioPapelORM(usuario_id=usuario_id, papel=papel.value)
                for papel in papeis_set
            ]
        )
        self._session.flush()

    def definir_unidades(
        self,
        *,
        usuario_id: str,
        unidades_permitidas: Iterable[str],
        unidade_padrao_id: str,
    ) -> None:
        unidades = frozenset(
            str(unidade).strip()
            for unidade in unidades_permitidas
            if str(unidade).strip()
        )
        padrao = unidade_padrao_id.strip()
        if not unidades or not padrao or padrao not in unidades:
            raise ValueError("escopo de unidades invalido")

        par = self._global_e_membership(usuario_id=usuario_id)
        if par is not None:
            _, membership = par
            self._session.execute(
                delete(IdentityMembershipUnitORM).where(
                    IdentityMembershipUnitORM.membership_id == membership.membership_id
                )
            )
            self._session.add_all(
                [
                    IdentityMembershipUnitORM(
                        membership_id=membership.membership_id,
                        unidade_id=unidade,
                    )
                    for unidade in sorted(unidades)
                ]
            )
            membership.unidade_padrao_id = padrao
            membership.atualizado_em = _agora()
            legacy = self._legacy_do_membership(membership)
            if legacy is not None:
                self._session.execute(
                    delete(UsuarioUnidadeORM).where(
                        UsuarioUnidadeORM.usuario_id == legacy.usuario_id
                    )
                )
                self._session.add_all(
                    [
                        UsuarioUnidadeORM(
                            usuario_id=legacy.usuario_id,
                            unidade_id=unidade,
                        )
                        for unidade in sorted(unidades)
                    ]
                )
                legacy.unidade_padrao_id = padrao
            self._session.flush()
            return

        usuario = self._session.get(UsuarioSegurancaORM, usuario_id)
        if usuario is None:
            raise ValueError("usuario inexistente")
        self._session.execute(
            delete(UsuarioUnidadeORM).where(
                UsuarioUnidadeORM.usuario_id == usuario_id
            )
        )
        self._session.add_all(
            [
                UsuarioUnidadeORM(usuario_id=usuario_id, unidade_id=unidade)
                for unidade in sorted(unidades)
            ]
        )
        usuario.unidade_padrao_id = padrao
        self._session.flush()

    def definir_ativo(self, *, usuario_id: str, ativo: bool) -> None:
        par = self._global_e_membership(usuario_id=usuario_id)
        if par is not None:
            _, membership = par
            membership.ativo = bool(ativo)
            membership.atualizado_em = _agora()
            legacy = self._legacy_do_membership(membership)
            if legacy is not None:
                legacy.ativo = bool(ativo)
            self._session.flush()
            return
        usuario = self._session.get(UsuarioSegurancaORM, usuario_id)
        if usuario is None:
            raise ValueError("usuario inexistente")
        usuario.ativo = bool(ativo)
        self._session.flush()
