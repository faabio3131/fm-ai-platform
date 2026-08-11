from datetime import UTC, datetime
from decimal import Decimal

import pytest

from core.salao import Comanda, ErroSalao, Mesa, StatusComanda, StatusMesa
from core.salao.flags import salao_v1_enabled

AGORA = datetime(2026, 8, 11, 13, 0, tzinfo=UTC)


def test_mesa_e_comanda_normalizam_valores() -> None:
    mesa = Mesa(
        mesa_id="mesa-1",
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        codigo="01",
        capacidade=4,
        status=StatusMesa.LIVRE,
        ativo=True,
        criado_em=AGORA,
        atualizado_em=AGORA,
        versao=1,
    )
    comanda = Comanda(
        comanda_id="cmd-1",
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        numero="C-001",
        status=StatusComanda.ABERTA,
        responsavel_id="garcom-1",
        aberta_em=AGORA,
        total=Decimal(10),
        saldo=Decimal("10.0"),
        versao=1,
        mesa_id=mesa.mesa_id,
    )
    assert comanda.total == Decimal("10.00")
    assert comanda.saldo == Decimal("10.00")


def test_comanda_rejeita_saldo_maior_que_total() -> None:
    with pytest.raises(ErroSalao) as erro:
        Comanda(
            comanda_id="cmd-1",
            tenant_id="tenant-1",
            unidade_id="unidade-1",
            numero="C-001",
            status=StatusComanda.ABERTA,
            responsavel_id="garcom-1",
            aberta_em=AGORA,
            total=Decimal("10.00"),
            saldo=Decimal("11.00"),
            versao=1,
        )
    assert erro.value.codigo == "saldo_comanda_invalido"


def test_flag_salao_e_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FM_AI_TEST_MODE", raising=False)
    monkeypatch.setenv("FM_AI_SALAO_V1", "1")
    assert salao_v1_enabled() is False
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    assert salao_v1_enabled() is True
