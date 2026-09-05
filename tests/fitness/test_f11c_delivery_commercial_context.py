from __future__ import annotations

from ast import Attribute, Call, parse, walk
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_COMMERCIAL_FILES = (
    _ROOT / "application" / "delivery_contexto_comercial.py",
    _ROOT / "infra" / "delivery" / "catalogo_sqlalchemy.py",
    _ROOT / "infra" / "crm" / "clientes_sqlalchemy.py",
)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_f11c_contexto_comercial_nao_depende_de_runtime_demo() -> None:
    proibidos = (
        "runtime_teste",
        "RuntimeDeliveryTeste",
        "tenant-demo",
        "unidade-demo",
        "cliente-demo",
        "FM_AI_TEST_MODE",
    )
    for path in _COMMERCIAL_FILES:
        source = _source(path)
        for token in proibidos:
            assert token not in source, f"{path}: referência comercial proibida {token}"


def test_f11c_adapters_nao_controlam_transacao() -> None:
    for path in _COMMERCIAL_FILES:
        tree = parse(_source(path))
        chamadas = {
            node.func.attr
            for node in walk(tree)
            if isinstance(node, Call) and isinstance(node.func, Attribute)
        }
        assert "commit" not in chamadas, f"{path}: commit escondido no boundary"
        assert "rollback" not in chamadas, f"{path}: rollback escondido no boundary"


def test_f11c_usa_fontes_canonicas_de_escopo_cliente_endereco_e_politica() -> None:
    contexto = _source(_ROOT / "application" / "delivery_contexto_comercial.py")
    catalogo = _source(_ROOT / "infra" / "delivery" / "catalogo_sqlalchemy.py")

    for needle in (
        "identidade.contexto",
        "LeitorClientesCRMSQLAlchemy",
        "EncryptedSQLAlchemyAddressStore",
        "RepositorioPoliticaEntregaSQLAlchemy",
        "CatalogoDeliverySQLAlchemy",
    ):
        assert needle in contexto

    for needle in (
        "listar_produtos_legados",
        "listar_fichas_produto_legadas",
        "obter_insumo_por_id_legado",
        'produto_id=f"legacy:produto:{produto_id}"',
    ):
        assert needle in catalogo
