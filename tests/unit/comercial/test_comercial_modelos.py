from __future__ import annotations

import pytest

from core.comercial.erros import DadoComercialInvalido, TransicaoComercialInvalida
from core.comercial.modelos import (
    StatusContaProduto,
    normalizar_email,
    normalizar_product_code,
    validar_transicao_conta_produto,
)


def test_normalizacoes_comerciais_sao_deterministicas() -> None:
    assert normalizar_email("  Dono@Empresa.COM  ") == "dono@empresa.com"
    assert normalizar_product_code(" kordena ") == "KORDENA"


@pytest.mark.parametrize("email", ["", "sem-arroba", "x@y"])
def test_email_invalido_falha_fechado(email: str) -> None:
    with pytest.raises(DadoComercialInvalido):
        normalizar_email(email)


def test_ativacao_exige_tenant_e_binding_e_imutavel() -> None:
    with pytest.raises(
        TransicaoComercialInvalida,
        match="tenant_obrigatorio_para_ativacao",
    ):
        validar_transicao_conta_produto(
            atual=StatusContaProduto.REQUESTED,
            destino=StatusContaProduto.ACTIVE,
            tenant_atual=None,
            tenant_solicitado=None,
        )

    assert (
        validar_transicao_conta_produto(
            atual=StatusContaProduto.REQUESTED,
            destino=StatusContaProduto.ACTIVE,
            tenant_atual=None,
            tenant_solicitado="tenant-a",
        )
        == "tenant-a"
    )

    with pytest.raises(
        TransicaoComercialInvalida,
        match="product_tenant_id_imutavel",
    ):
        validar_transicao_conta_produto(
            atual=StatusContaProduto.SUSPENDED,
            destino=StatusContaProduto.ACTIVE,
            tenant_atual="tenant-a",
            tenant_solicitado="tenant-b",
        )
