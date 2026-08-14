"""Persistência SQLAlchemy das identidades autenticáveis da V1."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from core.seguranca.autenticacao import IdentidadeUsuario, hash_password
from core.seguranca.permissoes import Papel

from .modelos_orm import UsuarioPapelORM, UsuarioSegurancaORM, UsuarioUnidadeORM


class RepositorioIdentidadesSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self._session = session

    def obter_por_email(self, email_normalizado: str) -> IdentidadeUsuario | None:
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
        papeis = frozenset(Papel(valor) for valor in papeis_raw)
        if not unidades:
            unidades = frozenset({usuario.unidade_padrao_id})

        return IdentidadeUsuario(
            usuario_id=usuario.usuario_id,
            email=usuario.email,
            senha_hash=usuario.senha_hash,
            tenant_id=usuario.tenant_id,
            unidade_id=usuario.unidade_padrao_id,
            papeis=papeis,
            unidades_permitidas=unidades,
            ativo=usuario.ativo,
        )

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
    ) -> IdentidadeUsuario:
        normalizado = email.strip().casefold()
        if not normalizado or "@" not in normalizado:
            raise ValueError("email invalido")
        papeis_set = frozenset(papeis)
        if not papeis_set:
            raise ValueError("usuario sem papel")
        unidades = frozenset(
            u.strip() for u in (unidades_permitidas or (unidade_padrao_id,)) if u.strip()
        )
        if unidade_padrao_id not in unidades:
            unidades = frozenset({*unidades, unidade_padrao_id})

        if self.obter_por_email(normalizado) is not None:
            raise ValueError("usuario ja cadastrado")

        uid = usuario_id or str(uuid4())
        usuario = UsuarioSegurancaORM(
            usuario_id=uid,
            email=normalizado,
            senha_hash=hash_password(password),
            tenant_id=tenant_id.strip(),
            unidade_padrao_id=unidade_padrao_id.strip(),
            ativo=True,
        )
        self._session.add(usuario)
        self._session.add_all(
            [UsuarioPapelORM(usuario_id=uid, papel=papel.value) for papel in papeis_set]
        )
        self._session.add_all(
            [UsuarioUnidadeORM(usuario_id=uid, unidade_id=unidade) for unidade in unidades]
        )
        self._session.flush()
        identidade = self.obter_por_email(normalizado)
        if identidade is None:  # pragma: no cover - defesa de consistência
            raise RuntimeError("falha ao reconstruir identidade persistida")
        return identidade

    def trocar_senha(self, *, usuario_id: str, nova_senha: str) -> None:
        usuario = self._session.get(UsuarioSegurancaORM, usuario_id)
        if usuario is None:
            raise ValueError("usuario inexistente")
        usuario.senha_hash = hash_password(nova_senha)
        self._session.flush()

    def definir_papeis(self, *, usuario_id: str, papeis: Iterable[Papel]) -> None:
        papeis_set = frozenset(papeis)
        if not papeis_set:
            raise ValueError("usuario sem papel")
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

    def definir_ativo(self, *, usuario_id: str, ativo: bool) -> None:
        usuario = self._session.get(UsuarioSegurancaORM, usuario_id)
        if usuario is None:
            raise ValueError("usuario inexistente")
        usuario.ativo = bool(ativo)
        self._session.flush()
