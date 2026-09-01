from __future__ import annotations

from decimal import Decimal

import pytest

from core.administracao import (
    ConfiguracaoEstabelecimento,
    EmpresaAdministrativa,
    UnidadeAdministrativa,
)


def test_modelos_administrativos_validam_campos_e_nao_exigem_segredos() -> None:
    empresa = EmpresaAdministrativa(
        tenant_id="tenant-1",
        nome_exibicao="Empresa Teste",
        moeda="brl",
    )
    unidade = UnidadeAdministrativa(
        tenant_id="tenant-1",
        unidade_id="loja-centro",
        codigo="CENTRO",
        nome_fantasia="Loja Centro",
        tipo="filial",
        endereco={"descricao": "Rua de Teste, 10"},
        horarios={"descricao": "08:00-18:00"},
    )
    config = ConfiguracaoEstabelecimento(
        tenant_id="tenant-1",
        unidade_id="loja-centro",
        formas_pagamento=("PIX", "dinheiro", "pix"),
        taxa_servico_percentual=Decimal("10"),
        parametros_operacionais={"aceita_pagamento_na_entrega": True},
        politica_financeira={"taxa_embalagem": "2.50"},
    )

    assert empresa.moeda == "BRL"
    assert unidade.tipo == "filial"
    assert config.formas_pagamento == ("pix", "dinheiro")
    assert config.taxa_servico_percentual == Decimal("10")


@pytest.mark.parametrize("taxa", [Decimal("-0.01"), Decimal("100.01")])
def test_configuracao_rejeita_taxa_de_servico_fora_do_limite(taxa: Decimal) -> None:
    with pytest.raises(ValueError, match="taxa_servico_invalida"):
        ConfiguracaoEstabelecimento(
            tenant_id="tenant-1",
            unidade_id="loja-1",
            taxa_servico_percentual=taxa,
        )


def test_unidade_rejeita_tipo_nao_governado() -> None:
    with pytest.raises(ValueError, match="tipo_unidade_invalido"):
        UnidadeAdministrativa(
            tenant_id="tenant-1",
            unidade_id="loja-1",
            codigo="L1",
            nome_fantasia="Loja 1",
            tipo="franquia-inventada",
        )
