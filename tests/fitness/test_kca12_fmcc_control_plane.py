from __future__ import annotations

import inspect
from typing import get_args

import http_api.fmcc_commercial_control as boundary


def test_kca12_fmcc_boundary_delega_para_autoridade_canonica_do_catalogo() -> None:
    source = inspect.getsource(boundary)

    assert (
        "from application.commercial_catalog import AplicacaoCatalogoComercialV1"
        in source
    )
    assert "catalog = AplicacaoCatalogoComercialV1(session_factory)" in source

    for method in (
        "catalog.criar_versao_plano(",
        "catalog.validar_versao_plano(",
        "catalog.preview_versao_plano(",
        "catalog.publicar_versao_plano(",
        "catalog.criar_preco(",
        "catalog.validar_preco(",
        "catalog.preview_preco(",
        "catalog.publicar_preco(",
        "catalog.criar_promocao(",
        "catalog.criar_versao_promocao(",
        "catalog.validar_versao_promocao(",
        "catalog.preview_promocao(",
        "catalog.publicar_versao_promocao(",
    ):
        assert method in source

    assert "sqlalchemy" not in source
    assert "infra.comercial" not in source
    assert ".execute(" not in source
    assert ".add(" not in source


def test_kca12_nao_expoe_mutacao_de_product_account_no_control_plane() -> None:
    actions = set(get_args(boundary.CatalogAction))

    assert actions
    assert all("product_account" not in action for action in actions)
    assert all("customer" not in action for action in actions)
