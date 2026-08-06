# ruff: noqa: F405
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import ast
from pathlib import Path

import pytest

from core.dominio.comandos import ConfirmarPedido
from core.dominio.decisoes import DecisaoCozinha
from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import CodigoDecisaoCozinha, PedidoStatus, RiscoPedido
from core.dominio.erros import (
    ErroValidacaoDominio,
    IdentificadorInvalido,
    ValorMonetarioInvalido,
)
from core.dominio.eventos import PedidoCriado
from core.dominio.ids import *  # noqa: F403
from core.dominio.snapshots import PedidoSnapshot
from core.dominio.tempo import FixedClock, em_utc

NOW = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)


def test_ids_sao_nominais_hashable_e_validos():
    assert PedidoId("x") != ClienteId("x")
    assert len({PedidoId("x"), PedidoId("x")}) == 1
    assert PedidoId.de(" x ").para_dict() == "x"
    with pytest.raises(IdentificadorInvalido):
        TenantId("")


def test_dinheiro_decimal_operacoes_serializacao_e_float_rejeitado():
    assert (Dinheiro("0.10") + Dinheiro(Decimal("0.20"))).valor == Decimal("0.30")
    assert Dinheiro("1.005").valor == Decimal("1.01")
    assert (Dinheiro(2) * 3).valor == Decimal("6.00")
    assert Dinheiro("-1").valor == Decimal("-1.00")
    assert Dinheiro("1.20").para_dict() == {"valor": "1.20", "moeda": "BRL"}
    with pytest.raises(ValorMonetarioInvalido):
        Dinheiro(0.1)
    with pytest.raises(ValorMonetarioInvalido):
        _ = Dinheiro(1, "BRL") + Dinheiro(1, "USD")


def test_tempo_utc_e_clock():
    with pytest.raises(ErroValidacaoDominio):
        em_utc(datetime(2026, 1, 1))
    local = datetime(2026, 1, 1, 0, tzinfo=timezone(timedelta(hours=-3)))
    assert em_utc(local).hour == 3
    assert FixedClock(local).agora().tzinfo is timezone.utc


def test_enum_persistivel_estavel():
    assert PedidoStatus.CONFIRMADO.value == "confirmado"


def _base():
    return dict(
        command_id=CommandId("cmd"),
        tenant_id=TenantId("t"),
        unidade_id=UnidadeId("u"),
        ator_id=UsuarioId("a"),
        correlation_id=CorrelationId("c"),
        solicitado_em=NOW,
    )


def test_comando_validado_imutavel_e_serializavel():
    cmd = ConfirmarPedido(**_base(), pedido_id=PedidoId("p"))
    assert cmd.para_dict()["solicitado_em"].endswith("Z")
    with pytest.raises(FrozenInstanceError):
        cmd.versao = 2
    with pytest.raises(IdentificadorInvalido):
        ConfirmarPedido(
            **(_base() | {"tenant_id": TenantId("")}), pedido_id=PedidoId("p")
        )


def test_evento_correlation_e_serializacao_deterministica():
    kwargs = dict(
        event_id=EventoId("e"),
        aggregate_id="p",
        aggregate_type="pedido",
        tenant_id=TenantId("t"),
        unidade_id=UnidadeId("u"),
        causation_id=None,
        occurred_at=NOW,
    )
    with pytest.raises((ValueError, TypeError)):
        PedidoCriado(**kwargs, correlation_id=None)
    event = PedidoCriado(
        **kwargs, correlation_id=CorrelationId("c"), payload={"total": Decimal("1.20")}
    )
    assert event.para_dict()["payload"]["total"] == "1.20"
    assert list(event.para_dict()) == sorted(event.para_dict())


def test_snapshot_imutavel():
    snap = PedidoSnapshot(
        tenant_id=TenantId("t"),
        unidade_id=UnidadeId("u"),
        atualizado_em=NOW,
        pedido_id=PedidoId("p"),
        status=PedidoStatus.RASCUNHO,
        origem="balcao",
        total=Dinheiro(0),
    )
    with pytest.raises(FrozenInstanceError):
        snap.status = PedidoStatus.CONFIRMADO


def test_decisao_cozinha_invariante_e_serializacao():
    base = dict(
        justificativa="Política satisfeita",
        confirmacao_exigida=False,
        risco=RiscoPedido.BAIXO,
        politica_aplicada="pagamento",
        versao_politica="1",
        decidido_em=NOW,
    )
    decisao = DecisaoCozinha(
        permitido=True,
        codigo_decisao=CodigoDecisaoCozinha.PERMITIDO_PAGAMENTO_CONFIRMADO,
        **base,
    )
    assert decisao.para_dict()["decidido_em"].endswith("Z")
    with pytest.raises(ErroValidacaoDominio):
        DecisaoCozinha(
            permitido=False,
            codigo_decisao=CodigoDecisaoCozinha.PERMITIDO_PAGAMENTO_CONFIRMADO,
            **base,
        )


def test_dominio_nao_importa_infraestrutura():
    proibidos = {"streamlit", "sqlalchemy", "google.generativeai", "requests", "app"}
    for path in Path("core/dominio").glob("*.py"):
        tree = ast.parse(path.read_text())
        imports = {
            n.names[0].name.split(".")[0]
            for n in ast.walk(tree)
            if isinstance(n, ast.Import)
        } | {
            str(n.module).split(".")[0]
            for n in ast.walk(tree)
            if isinstance(n, ast.ImportFrom)
        }
        assert imports.isdisjoint(proibidos)
