from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.dominio.dinheiro import Dinheiro
from core.pagamentos.flags import FlagsPagamentosV1
from core.pdv.configuracao import carregar_rollout_ambiente
from core.pdv.modelos import (
    dinheiro_legado,
    id_cliente_legado,
    id_produto_legado,
    mapear_metodo,
)
from core.pdv.roteamento import (
    ConfiguracaoRolloutInvalida,
    ModoPDV,
    PDVFlags,
    PDVRolloutConfig,
    decidir_modo,
)
from core.pedidos.flags import OrdersFeatureFlags
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel, Permissao


def contexto(tenant: str = "t", unidade: str = "u") -> ContextoExecucao:
    return ContextoExecucao(
        tenant,
        unidade,
        "caixa",
        frozenset({Papel.CAIXA}),
        MATRIZ_PADRAO[Papel.CAIXA],
        "corr",
        datetime.now(timezone.utc),
        "teste",
        unidades_permitidas=frozenset({unidade}),
    )


def test_decimal_ids_e_metodos() -> None:
    for valor in (29.90, 0.01, 999999.99):
        assert dinheiro_legado(valor).valor == Decimal(str(valor)).quantize(
            Decimal(".01")
        )
    assert id_produto_legado(7) == "legacy:produto:7"
    assert id_cliente_legado(None) is None
    assert id_cliente_legado(8) == "legacy:cliente:8"
    assert mapear_metodo("Pix").value == "pix"


def test_legacy_shadow_e_canary() -> None:
    ctx = contexto()
    assert (
        decidir_modo(contexto=ctx, terminal_id="cx", config=PDVRolloutConfig("t", "u"))
        is ModoPDV.LEGACY
    )
    shadow = PDVRolloutConfig(
        "t",
        "u",
        modo=ModoPDV.SHADOW,
        flags=PDVFlags(orders=OrdersFeatureFlags(orders_shadow_write=True)),
    )
    assert decidir_modo(contexto=ctx, terminal_id="cx", config=shadow) is ModoPDV.SHADOW
    canary = PDVRolloutConfig(
        "t",
        "u",
        frozenset({"cx"}),
        ModoPDV.AUTHORITATIVE_CANARY,
        PDVFlags(
            OrdersFeatureFlags(orders_authoritative=True),
            FlagsPagamentosV1(True, True, True),
            False,
        ),
        True,
    )
    assert (
        decidir_modo(contexto=ctx, terminal_id="cx", config=canary)
        is ModoPDV.AUTHORITATIVE_CANARY
    )
    with pytest.raises(ConfiguracaoRolloutInvalida):
        decidir_modo(contexto=ctx, terminal_id="negado", config=canary)
    assert (
        decidir_modo(contexto=contexto("outro"), terminal_id="cx", config=canary)
        is ModoPDV.LEGACY
    )


def test_rbac_minimo_caixa_e_gerente_ia() -> None:
    caixa = MATRIZ_PADRAO[Papel.CAIXA]
    assert {
        Permissao.PEDIDO_CRIAR,
        Permissao.PEDIDO_VISUALIZAR,
        Permissao.PEDIDO_ALTERAR,
    } <= caixa
    assert Permissao.PDV_OPERAR not in MATRIZ_PADRAO[Papel.GERENTE_IA]
    assert Permissao.PERMISSAO_GERENCIAR not in caixa


def test_dinheiro_nao_aceita_float_v1() -> None:
    with pytest.raises(Exception):
        Dinheiro(29.9)  # type: ignore[arg-type]


def test_loader_nunca_ativa_canary_fora_de_test_mode(monkeypatch) -> None:
    monkeypatch.delenv("FM_AI_TEST_MODE", raising=False)
    monkeypatch.setenv("FM_AI_PDV_MODE", "authoritative_canary")
    assert carregar_rollout_ambiente().modo is ModoPDV.LEGACY


def test_loader_canary_exige_ambiente_explicito(monkeypatch) -> None:
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    monkeypatch.setenv("FM_AI_PDV_MODE", "authoritative_canary")
    monkeypatch.setenv("FM_AI_TEST_TENANT", "t")
    monkeypatch.setenv("FM_AI_TEST_UNIDADE", "u")
    monkeypatch.setenv("FM_AI_TEST_TERMINAL", "cx")
    config = carregar_rollout_ambiente()
    assert config.modo is ModoPDV.AUTHORITATIVE_CANARY
    assert config.contexto_confiavel
    assert config.terminais_permitidos == frozenset({"cx"})
