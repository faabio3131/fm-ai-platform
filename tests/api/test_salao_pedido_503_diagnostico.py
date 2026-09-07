from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import http_api.salao as salao_http


def _contrato() -> ModuleType:
    path = Path(__file__).with_name("test_salao_pedido_http_contract.py")
    spec = importlib.util.spec_from_file_location("_salao_pedido_http_contract_diag", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_diagnostico_expoe_excecao_mascarada_pelo_503(monkeypatch) -> None:
    contrato = _contrato()

    def _rerraise(exc: Exception):
        raise exc

    monkeypatch.setattr(salao_http, "_erro_http", _rerraise)
    _, client = contrato._infra()
    comanda_id = contrato._abrir(client)

    client.post(
        f"/v1/salao/comandas/{comanda_id}/pedidos",
        headers=contrato._headers("salao-order-diagnostico-503"),
        json=contrato._payload(),
    )
