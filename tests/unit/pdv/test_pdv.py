from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.dominio.dinheiro import Dinheiro
from core.pagamentos.flags import FlagsPagamentosV1
from core.pdv.configuracao import carregar_rollout_ambiente
from core.pdv.contexto import contexto_caixa_pdv_autenticado
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
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import CredenciaisInvalidas
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


def identidade_ativa(
    *,
    tenant: str = "tenant-ativo",
    unidade_padrao: str = "unidade-a",
    unidade_ativa: str = "unidade-b",
    ativo: bool = True,
) -> IdentidadeUsuario:
    return IdentidadeUsuario(
        usuario_id="operador",
        email="operador@example.com",
        senha_hash="hash-de-teste",
        tenant_id=tenant,
        unidade_id=unidade_padrao,
        papeis=frozenset({Papel.CAIXA}),
        unidades_permitidas=frozenset({unidade_padrao, unidade_ativa}),
        ativo=ativo,
    ).no_escopo_ativo(tenant_id=tenant, unidade_id=unidade_ativa)


def test_contexto_caixa_usa_active_execution_scope_e_ignora_escopo_do_rollout(
    monkeypatch,
) -> None:
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    monkeypatch.setenv("FM_AI_TEST_TENANT", "tenant-divergente")
    monkeypatch.setenv("FM_AI_TEST_UNIDADE", "unidade-divergente")
    rollout = carregar_rollout_ambiente()
    identidade = identidade_ativa()

    contexto_ativo = contexto_caixa_pdv_autenticado(
        identidade=identidade,
        usuario_id="caixa",
        correlation_id="corr-active-scope",
        instante=datetime.now(timezone.utc),
        origem="teste-active-scope",
    )

    assert (rollout.tenant_id, rollout.unidade_id) == (
        "tenant-divergente",
        "unidade-divergente",
    )
    assert (contexto_ativo.tenant_id, contexto_ativo.unidade_id) == (
        "tenant-ativo",
        "unidade-b",
    )
    assert contexto_ativo.unidades_permitidas == frozenset({"unidade-b"})


def test_contexto_caixa_falha_fechado_para_identidade_inativa() -> None:
    identidade = identidade_ativa(ativo=False)

    with pytest.raises(CredenciaisInvalidas, match="credenciais invalidas"):
        contexto_caixa_pdv_autenticado(
            identidade=identidade,
            usuario_id="caixa",
            correlation_id="corr-inativa",
            instante=datetime.now(timezone.utc),
            origem="teste-inativa",
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
            True,
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


def test_canary_falha_fechado_sem_estoque_canonico_autoritativo() -> None:
    config = PDVRolloutConfig(
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
    with pytest.raises(ConfiguracaoRolloutInvalida, match="canary_incompleto"):
        decidir_modo(contexto=contexto(), terminal_id="cx", config=config)


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
    assert config.flags.orders.orders_authoritative
    assert config.flags.payments.payments_v1_enabled
    assert config.flags.stock_ledger_authoritative
