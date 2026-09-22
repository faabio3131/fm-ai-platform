"""Entidades e invariantes do Commercial Registry KCA-01."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .erros import DadoComercialInvalido, TransicaoComercialInvalida


def _texto(valor: str, campo: str, *, max_length: int) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise DadoComercialInvalido(f"{campo}_obrigatorio")
    normalizado = valor.strip()
    if len(normalizado) > max_length:
        raise DadoComercialInvalido(f"{campo}_excede_limite")
    return normalizado


def normalizar_email(valor: str) -> str:
    email = _texto(valor, "email", max_length=320).casefold()
    local, separador, dominio = email.partition("@")
    if not separador or not local or "." not in dominio:
        raise DadoComercialInvalido("email_invalido")
    return email


def normalizar_telefone(valor: str | None) -> str | None:
    if valor is None:
        return None
    telefone = valor.strip()
    if not telefone:
        return None
    if len(telefone) > 64:
        raise DadoComercialInvalido("telefone_excede_limite")
    return telefone


def normalizar_product_code(valor: str) -> str:
    product_code = _texto(valor, "product_code", max_length=64).upper()
    if not all(
        caractere.isalnum() or caractere in {"_", "-"} for caractere in product_code
    ):
        raise DadoComercialInvalido("product_code_invalido")
    return product_code


class ClasseContaComercial(StrEnum):
    INTERNAL_TEST = "internal_test"
    TRIAL = "trial"
    PAID = "paid"
    PARTNER = "partner"


class StatusClienteComercial(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class StatusContaProduto(StrEnum):
    REQUESTED = "requested"
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


_TRANSICOES_CONTA_PRODUTO: dict[StatusContaProduto, frozenset[StatusContaProduto]] = {
    StatusContaProduto.REQUESTED: frozenset(
        {
            StatusContaProduto.PROVISIONING,
            StatusContaProduto.ACTIVE,
            StatusContaProduto.CLOSED,
        }
    ),
    StatusContaProduto.PROVISIONING: frozenset(
        {
            StatusContaProduto.ACTIVE,
            StatusContaProduto.SUSPENDED,
            StatusContaProduto.CLOSED,
        }
    ),
    StatusContaProduto.ACTIVE: frozenset(
        {StatusContaProduto.SUSPENDED, StatusContaProduto.CLOSED}
    ),
    StatusContaProduto.SUSPENDED: frozenset(
        {StatusContaProduto.ACTIVE, StatusContaProduto.CLOSED}
    ),
    StatusContaProduto.CLOSED: frozenset(),
}


@dataclass(frozen=True, kw_only=True)
class ClienteComercial:
    fm_customer_id: str
    customer_code: str
    display_name: str
    legal_name: str | None
    status: StatusClienteComercial
    account_class: ClasseContaComercial
    primary_contact_email: str
    primary_contact_phone: str | None
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, kw_only=True)
class ContaProdutoComercial:
    product_account_id: str
    fm_customer_id: str
    product_code: str
    product_tenant_id: str | None
    status: StatusContaProduto
    version: int
    created_at: datetime
    updated_at: datetime
    activated_at: datetime | None
    suspended_at: datetime | None
    closed_at: datetime | None


def validar_transicao_conta_produto(
    *,
    atual: StatusContaProduto,
    destino: StatusContaProduto,
    tenant_atual: str | None,
    tenant_solicitado: str | None,
) -> str | None:
    if destino == atual:
        raise TransicaoComercialInvalida("transicao_sem_mudanca")
    if destino not in _TRANSICOES_CONTA_PRODUTO[atual]:
        raise TransicaoComercialInvalida(
            f"transicao_invalida:{atual.value}->{destino.value}"
        )

    atual_normalizado = tenant_atual.strip() if tenant_atual else None
    solicitado_normalizado = tenant_solicitado.strip() if tenant_solicitado else None
    if (
        atual_normalizado
        and solicitado_normalizado
        and atual_normalizado != solicitado_normalizado
    ):
        raise TransicaoComercialInvalida("product_tenant_id_imutavel")

    tenant_resultante = atual_normalizado or solicitado_normalizado
    if destino == StatusContaProduto.ACTIVE and not tenant_resultante:
        raise TransicaoComercialInvalida("tenant_obrigatorio_para_ativacao")
    return tenant_resultante
