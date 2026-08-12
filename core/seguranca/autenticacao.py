"""Autenticação e derivação de contexto para o runtime comercial.

A senha nunca é armazenada em texto puro. O formato versionado abaixo usa
PBKDF2-HMAC-SHA256 com salt aleatório e permite aumentar o custo no futuro sem
quebrar hashes já persistidos.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from .contexto import ContextoExecucao
from .erros import CredenciaisInvalidas, UsuarioInativo
from .permissoes import MATRIZ_PADRAO, Papel, Permissao

_ALGORITMO = "pbkdf2_sha256"
_ITERACOES_PADRAO = 390_000
_SALT_BYTES = 16


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str, *, iterations: int = _ITERACOES_PADRAO) -> str:
    if not isinstance(password, str) or len(password) < 10:
        raise ValueError("senha deve ter no minimo 10 caracteres")
    if iterations < 100_000:
        raise ValueError("custo PBKDF2 inseguro")
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return f"{_ALGORITMO}${iterations}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, raw_iterations, raw_salt, raw_digest = encoded.split("$", 3)
        if algorithm != _ALGORITMO:
            return False
        iterations = int(raw_iterations)
        if iterations < 100_000:
            return False
        salt = _unb64(raw_salt)
        expected = _unb64(raw_digest)
        calculated = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations
        )
        return hmac.compare_digest(calculated, expected)
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True)
class IdentidadeUsuario:
    usuario_id: str
    email: str
    senha_hash: str
    tenant_id: str
    unidade_id: str
    papeis: frozenset[Papel]
    unidades_permitidas: frozenset[str]
    ativo: bool = True

    def __post_init__(self) -> None:
        obrigatorios = (
            self.usuario_id,
            self.email,
            self.senha_hash,
            self.tenant_id,
            self.unidade_id,
        )
        if any(not valor.strip() for valor in obrigatorios):
            raise ValueError("identidade de usuario incompleta")
        if not self.papeis:
            raise ValueError("usuario deve possuir ao menos um papel")
        if self.unidade_id not in self.unidades_permitidas:
            raise ValueError("unidade ativa deve estar no escopo do usuario")

    @property
    def permissoes(self) -> frozenset[Permissao]:
        acumuladas: set[Permissao] = set()
        for papel in self.papeis:
            acumuladas.update(MATRIZ_PADRAO.get(papel, frozenset()))
        return frozenset(acumuladas)

    def contexto(
        self,
        *,
        origem: str,
        correlation_id: str | None = None,
        solicitado_em: datetime | None = None,
    ) -> ContextoExecucao:
        return ContextoExecucao(
            tenant_id=self.tenant_id,
            unidade_id=self.unidade_id,
            usuario_id=self.usuario_id,
            papeis=self.papeis,
            permissoes=self.permissoes,
            correlation_id=correlation_id or str(uuid4()),
            solicitado_em=solicitado_em or datetime.now(timezone.utc),
            origem=origem,
            unidades_permitidas=self.unidades_permitidas,
        )


class RepositorioIdentidades(Protocol):
    def obter_por_email(self, email_normalizado: str) -> IdentidadeUsuario | None: ...


class ServicoAutenticacao:
    def __init__(self, repositorio: RepositorioIdentidades) -> None:
        self._repositorio = repositorio

    @staticmethod
    def normalizar_email(email: str) -> str:
        return email.strip().casefold()

    def autenticar(self, *, email: str, password: str) -> IdentidadeUsuario:
        normalizado = self.normalizar_email(email)
        identidade = self._repositorio.obter_por_email(normalizado)
        # Mensagem uniforme evita revelar se um e-mail existe.
        if identidade is None or not verify_password(password, identidade.senha_hash):
            raise CredenciaisInvalidas("credenciais invalidas")
        if not identidade.ativo:
            raise UsuarioInativo("usuario indisponivel")
        return identidade
