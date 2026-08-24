"""Autenticação e derivação de contexto para o runtime comercial.

Senhas e PINs administrativos nunca são armazenados em texto puro. O formato
versionado usa PBKDF2-HMAC-SHA256 com salt aleatório e permite aumentar o custo
no futuro sem quebrar hashes já persistidos.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from .contexto import ContextoExecucao
from .erros import CredenciaisInvalidas, UsuarioInativo
from .permissoes import MATRIZ_PADRAO, Papel, Permissao

_ALGORITMO = "pbkdf2_sha256"
_ITERACOES_PADRAO = 390_000
_SALT_BYTES = 16
_ADMIN_PIN_PREFIX = "admin-pin-v1:"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _hash_secret(secret: str, *, iterations: int = _ITERACOES_PADRAO) -> str:
    if iterations < 100_000:
        raise ValueError("custo PBKDF2 inseguro")
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, iterations)
    return f"{_ALGORITMO}${iterations}${_b64(salt)}${_b64(digest)}"


def _verify_secret(secret: str, encoded: str) -> bool:
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
            "sha256", secret.encode("utf-8"), salt, iterations
        )
        return hmac.compare_digest(calculated, expected)
    except (AttributeError, TypeError, ValueError):
        return False


def hash_password(password: str, *, iterations: int = _ITERACOES_PADRAO) -> str:
    if not isinstance(password, str) or len(password) < 10:
        raise ValueError("senha deve ter no minimo 10 caracteres")
    return _hash_secret(password, iterations=iterations)


def verify_password(password: str, encoded: str) -> bool:
    return _verify_secret(password, encoded)


def validate_admin_pin(pin: str) -> str:
    """Valida o PIN administrativo individual sem aceitar formatos fracos/ambíguos."""

    if not isinstance(pin, str):
        raise ValueError("PIN administrativo invalido")
    normalized = pin.strip()
    if not normalized.isdigit() or not 6 <= len(normalized) <= 8:
        raise ValueError("PIN administrativo deve ter de 6 a 8 digitos")
    if len(set(normalized)) == 1:
        raise ValueError("PIN administrativo muito fraco")
    return normalized


def hash_admin_pin(pin: str, *, iterations: int = _ITERACOES_PADRAO) -> str:
    normalized = validate_admin_pin(pin)
    return _hash_secret(_ADMIN_PIN_PREFIX + normalized, iterations=iterations)


def verify_admin_pin(pin: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        normalized = validate_admin_pin(pin)
    except ValueError:
        return False
    return _verify_secret(_ADMIN_PIN_PREFIX + normalized, encoded)


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
    acesso_admin_sensivel: bool = False

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
        if self.acesso_admin_sensivel:
            acumuladas.add(Permissao.ADMIN_ACESSAR)
        return frozenset(acumuladas)

    def no_escopo_ativo(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
    ) -> IdentidadeUsuario:
        """Vincula a identidade ao único escopo ativo já autorizado.

        ``unidade_id`` persistida na identidade representa inicialmente a unidade
        padrão do usuário. O runtime pode estar configurado para outra unidade
        permitida; nesse caso a identidade usada por UI, contexto e adapters deve
        carregar explicitamente essa mesma unidade, sem ampliar o membership.
        """

        tenant_ativo = tenant_id.strip() if isinstance(tenant_id, str) else ""
        unidade_ativa = unidade_id.strip() if isinstance(unidade_id, str) else ""
        if (
            not tenant_ativo
            or not unidade_ativa
            or tenant_ativo != self.tenant_id
            or unidade_ativa not in self.unidades_permitidas
        ):
            raise CredenciaisInvalidas("credenciais invalidas")
        if unidade_ativa == self.unidade_id:
            return self
        return replace(self, unidade_id=unidade_ativa)

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
