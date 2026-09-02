import logging
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.dominio.dinheiro import Dinheiro
from core.pdv.configuracao import carregar_rollout_ambiente
from core.pdv.modelos import EntradaPDV, ResultadoPDV
from core.pdv.reconciliacao import (
    RecomendacaoCoortePDV,
    RegistroReadinessPDV,
    extrair_terminal_id_reconciliacao,
    resumir_readiness,
)
from core.pdv.roteamento import ModoPDV, PDVRolloutConfig
from core.pdv.servicos import finalizar_venda_pdv
from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel


class _UOW:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.rollback()

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _Legacy:
    def executar(self, entrada: EntradaPDV) -> ResultadoPDV:
        return ResultadoPDV("legacy", True, venda_legada_id="legacy-1")


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        "tenant-f6e",
        "unidade-f6e",
        "caixa",
        frozenset({Papel.CAIXA}),
        MATRIZ_PADRAO[Papel.CAIXA],
        "corr-f6e",
        datetime.now(timezone.utc),
        "teste-f6e",
        unidades_permitidas=frozenset({"unidade-f6e"}),
    )


def _entrada(
    *, terminal_id: str = "caixa-01", checkout_id: str = "checkout-01"
) -> EntradaPDV:
    return EntradaPDV(
        produto_id=1,
        produto_nome="Produto",
        quantidade=1,
        preco_unitario=Dinheiro(Decimal("10.00")),
        custo_total=Dinheiro(Decimal("4.00")),
        forma_pagamento="Dinheiro Em Espécie",
        terminal_id=terminal_id,
        checkout_id=checkout_id,
    )


def _registro(
    *,
    modo: str,
    terminal: str,
    checkout: str,
    status: str = "conciliado",
) -> RegistroReadinessPDV:
    return RegistroReadinessPDV(
        tenant_id="tenant-f6e",
        unidade_id="unidade-f6e",
        modo=modo,
        idempotency_key=f"pdv:{terminal}:{checkout}:reconciliacao",
        status=status,
        divergencias=(),
        criado_em=datetime.now(timezone.utc),
    )


def test_readiness_agrega_por_modo_e_terminal_sem_criar_estado_paralelo() -> None:
    resumo = resumir_readiness(
        (
            _registro(
                modo="authoritative_canary",
                terminal="caixa-01",
                checkout="a",
            ),
            _registro(
                modo="authoritative_canary",
                terminal="caixa-01",
                checkout="b",
            ),
            _registro(modo="shadow", terminal="caixa-02", checkout="c"),
        )
    )

    assert resumo.total_registros == 3
    assert resumo.recomendacao is RecomendacaoCoortePDV.AMPLIACAO_ELEGIVEL
    assert [(m.modo, m.terminal_id, m.total) for m in resumo.metricas] == [
        ("authoritative_canary", "caixa-01", 2),
        ("shadow", "caixa-02", 1),
    ]


def test_readiness_reduz_coorte_se_houver_divergencia_ou_chave_invalida() -> None:
    divergente = _registro(
        modo="authoritative_canary",
        terminal="caixa-01",
        checkout="a",
        status="divergente",
    )
    invalido = RegistroReadinessPDV(
        tenant_id="tenant-f6e",
        unidade_id="unidade-f6e",
        modo="authoritative_canary",
        idempotency_key="chave-invalida",
        status="conciliado",
        divergencias=(),
        criado_em=datetime.now(timezone.utc),
    )

    resumo = resumir_readiness((divergente, invalido))

    assert resumo.divergentes == 1
    assert resumo.chaves_invalidas == 1
    assert resumo.recomendacao is RecomendacaoCoortePDV.REDUZIR
    assert not resumo.apto_ampliacao


def test_readiness_mantem_coorte_com_pendente_ou_sem_amostra() -> None:
    pendente = _registro(
        modo="authoritative_canary",
        terminal="caixa-01",
        checkout="a",
        status="pendente_financeiro",
    )
    assert resumir_readiness((pendente,)).recomendacao is RecomendacaoCoortePDV.MANTER
    assert resumir_readiness(()).recomendacao is RecomendacaoCoortePDV.MANTER


def test_terminal_pdv_preserva_chave_parseavel() -> None:
    assert (
        extrair_terminal_id_reconciliacao(
            "pdv:caixa-01:checkout-com:segmento:reconciliacao"
        )
        == "caixa-01"
    )
    with pytest.raises(ValueError, match="terminal_pdv_invalido"):
        _entrada(terminal_id="caixa:01")


def test_telemetria_operacional_registra_legacy_por_terminal_sem_pii(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="fm_ai.pdv.rollout")
    uow = _UOW()

    resultado = finalizar_venda_pdv(
        entrada=_entrada(),
        contexto=_contexto(),
        config=PDVRolloutConfig("tenant-f6e", "unidade-f6e"),
        legado=_Legacy(),
        uow_legado=uow,
    )

    assert resultado.sucesso
    assert uow.commits == 1
    registro = next(
        item for item in caplog.records if item.getMessage() == "pdv_rollout_resultado"
    )
    assert registro.pdv_modo == "legacy"
    assert registro.pdv_terminal_id == "caixa-01"
    assert registro.pdv_tenant_id == "tenant-f6e"
    assert registro.pdv_unidade_id == "unidade-f6e"
    assert registro.pdv_sucesso is True
    assert not hasattr(registro, "produto_nome")


def test_rollback_operacional_retorna_para_legacy_sem_apagar_dados(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = RuntimeSettings(
        RuntimeEnvironment.STAGING,
        "postgresql+psycopg://localhost/f6e",
        "tenant-f6e",
        "unidade-f6e",
    )
    monkeypatch.delenv("FM_AI_TEST_MODE", raising=False)
    monkeypatch.setenv("FM_AI_PDV_MODE", "authoritative_canary")
    monkeypatch.setenv("FM_AI_PDV_COMMERCIAL_CANARY_ENABLED", "1")
    monkeypatch.setenv("FM_AI_PDV_TERMINAL_ID", "caixa-01")
    monkeypatch.setenv("FM_AI_PDV_ALLOWED_TERMINALS", "caixa-01")

    canary = carregar_rollout_ambiente(runtime_settings=settings)
    assert canary.modo is ModoPDV.AUTHORITATIVE_CANARY

    monkeypatch.setenv("FM_AI_PDV_MODE", "legacy")
    monkeypatch.setenv("FM_AI_PDV_COMMERCIAL_CANARY_ENABLED", "0")
    rollback = carregar_rollout_ambiente(runtime_settings=settings)

    assert rollback.modo is ModoPDV.LEGACY
    assert rollback.terminais_permitidos == frozenset()
