from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_wp031l_canonical_channels_remain_explicit_and_stable() -> None:
    enums = _source("core/dominio/enums.py")
    assert "{v: v.lower() for v in valores.split()}" in enums

    origem = enums.split("OrigemPedido = _enum(", 1)[1].split(
        "CanalAtendimento = _enum(", 1
    )[0]
    canal = enums.split("CanalAtendimento = _enum(", 1)[1].split(
        "FormaPagamento = _enum(", 1
    )[0]
    expected = {
        "PDV",
        "SALAO",
        "DELIVERY_PROPRIO",
        "IFOOD",
        "FOOD99",
        "KEETA",
        "WHATSAPP",
        "MICA",
    }
    for name in expected:
        assert name in origem
        assert name in canal


def test_wp031l_channels_reuse_canonical_order_and_payment_boundaries() -> None:
    pdv = _source("http_api/pdv.py")
    delivery = _source("application/delivery_checkout_comercial.py")
    salao = _source("application/salao_transacoes.py")
    marketplace = _source("application/marketplaces_web.py")

    assert "executar_checkout_v1" in pdv
    assert "executar_checkout_em_transacao" in delivery
    assert "criar_obrigacao_pagamento" in salao
    assert "confirmar_pagamento" in salao
    assert "PedidosInternosMarketplaceSQLAlchemy" in marketplace


def test_wp031l_operational_channels_do_not_embed_fiscal_engine() -> None:
    operational = (
        "http_api/pdv.py",
        "application/delivery_checkout_comercial.py",
        "application/salao_transacoes.py",
        "application/garcom_transacoes.py",
        "application/marketplaces_web.py",
    )
    for path in operational:
        source = _source(path)
        assert "kordena_fiscal" not in source
        assert "application.fiscal_" not in source


def test_wp031l_fiscal_outbound_starts_from_canonical_sale_event() -> None:
    payments = _source("core/pagamentos/servicos.py")
    fiscal = _source("application/fiscal_outbound.py")

    assert '"venda.criada"' in payments
    assert "venda.criada" in fiscal
    assert "VendaFinanceira" in payments


def test_wp031l_cognitive_fiscal_remains_read_only() -> None:
    service = _source("core/gerente_ia/servicos.py")
    tools = _source("core/gerente_ia/tools.py")

    assert "CONSULTAR_FISCAL" in service
    assert "Permissao.FISCAL_VISUALIZAR" in service
    assert "ToolGerenteIA.CONSULTAR_FISCAL" in tools
    assert "NaturezaTool.CONSULTA" in tools
