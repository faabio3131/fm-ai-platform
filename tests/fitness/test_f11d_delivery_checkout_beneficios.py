from __future__ import annotations

from ast import Attribute, Call, parse, walk
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_BOUNDARY = _ROOT / "application" / "delivery_checkout_comercial.py"


def _source() -> str:
    return _BOUNDARY.read_text(encoding="utf-8")


def test_f11d_boundary_converge_para_checkout_canonico() -> None:
    source = _source()
    assert "executar_checkout_em_transacao" in source
    assert "ComandoCheckoutV1" in source
    assert "ContextoDeliveryComercialV1" in source
    assert "CarrinhoDelivery" in source


def test_f11d_boundary_nao_depende_de_runtime_demo_ou_fake_pagamento() -> None:
    source = _source()
    for token in (
        "runtime_teste",
        "RuntimeDeliveryTeste",
        "tenant-demo",
        "unidade-demo",
        "cliente-demo",
        "FM_AI_TEST_MODE",
        "pagamento_aprovado_fake",
    ):
        assert token not in source


def test_f11d_boundary_nao_controla_commit_rollback() -> None:
    tree = parse(_source())
    chamadas = {
        node.func.attr
        for node in walk(tree)
        if isinstance(node, Call) and isinstance(node.func, Attribute)
    }
    assert "commit" not in chamadas
    assert "rollback" not in chamadas


def test_f11d_mantem_evidencia_de_decisao_comercial() -> None:
    source = _source()
    for needle in (
        "delivery.beneficio.checkout.avaliado.v1",
        "beneficio_aplicado",
        "origem_nao_elegivel",
        "metodo_pagamento_nao_elegivel",
        "beneficios_indisponiveis",
        "beneficios_inativos",
        "registrar_efeitos",
    ):
        assert needle in source
