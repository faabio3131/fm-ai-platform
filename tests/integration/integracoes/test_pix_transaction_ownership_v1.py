from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from application import pix_durabilidade as pix_app
from core.dominio.enums import PagamentoStatus
from core.pagamentos.adaptador_sqlalchemy import (
    RepositorioPagamentosSQLAlchemy,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from infra.integracoes.pix_runtime import CobrancaPixRuntime
from migrations.runner import run_migrations

AGORA = datetime(
    2026,
    8,
    27,
    15,
    55,
    tzinfo=timezone.utc,
)


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="tenant-a",
        unidade_id="loja-1",
        usuario_id="admin-1",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id="corr-sd1e-pix",
        solicitado_em=AGORA,
        origem="tests.sd1e.pix-ownership",
        unidades_permitidas=frozenset({"loja-1"}),
    )


def _factory():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    return engine, sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )


def _registrar(factory, pagamento_id: str):
    return pix_app.registrar_vinculo_cobranca_pix(
        session_factory=factory,
        contexto=_contexto(),
        pagamento_id=pagamento_id,
        pedido_id=pagamento_id.removeprefix("pdv-"),
        valor=Decimal("49.90"),
        provedor="pagbank",
        id_externo=f"ext-{pagamento_id}",
        idempotency_key=f"{pagamento_id}:charge",
        timestamp=AGORA,
        terminal_id="caixa-sd1e",
        assinatura_checkout=f"assinatura-{pagamento_id}",
    )


def test_application_commita_vinculo_pix() -> None:
    engine, factory = _factory()

    salva = _registrar(
        factory,
        "pdv-sd1e-commit",
    )

    assert salva.id_externo == "ext-pdv-sd1e-commit"

    with Session(engine) as session:
        repo = RepositorioPagamentosSQLAlchemy(session)

        pagamento = repo.buscar_pagamento(
            "tenant-a",
            "loja-1",
            "pdv-sd1e-commit",
        )

        assert pagamento is not None

        transacoes = repo.listar_transacoes(
            "tenant-a",
            "loja-1",
            "pdv-sd1e-commit",
        )

        assert any(
            transacao.id_externo
            == "ext-pdv-sd1e-commit"
            for transacao in transacoes
        )


def test_application_faz_rollback_integral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, factory = _factory()

    real = pix_app._registrar_vinculo_cobranca_pix

    def falhar(**kwargs):
        real(**kwargs)
        raise RuntimeError(
            "falha depois da persistencia"
        )

    monkeypatch.setattr(
        pix_app,
        "_registrar_vinculo_cobranca_pix",
        falhar,
    )

    with pytest.raises(
        RuntimeError,
        match="falha depois da persistencia",
    ):
        _registrar(
            factory,
            "pdv-sd1e-rollback",
        )

    with Session(engine) as session:
        repo = RepositorioPagamentosSQLAlchemy(session)

        pagamento = repo.buscar_pagamento(
            "tenant-a",
            "loja-1",
            "pdv-sd1e-rollback",
        )

        assert pagamento is None


def test_application_confirma_pix_e_preserva_replay() -> None:
    engine, factory = _factory()

    pagamento_id = "pdv-sd1e-confirm"

    _registrar(
        factory,
        pagamento_id,
    )

    cobranca = CobrancaPixRuntime(
        provedor="pagbank",
        id_externo=f"ext-{pagamento_id}",
        status="paid",
        valor=Decimal("49.90"),
        pix_copia_cola=None,
    )

    primeira = pix_app.confirmar_cobranca_pix_consultada(
        session_factory=factory,
        contexto=_contexto(),
        pagamento_id=pagamento_id,
        cobranca=cobranca,
        timestamp=AGORA,
    )

    assert primeira is not None
    assert primeira.pagamento.status is PagamentoStatus.PAGO

    replay = pix_app.confirmar_cobranca_pix_consultada(
        session_factory=factory,
        contexto=_contexto(),
        pagamento_id=pagamento_id,
        cobranca=cobranca,
        timestamp=AGORA,
    )

    assert replay is not None
    assert replay.idempotente is True

    with Session(engine) as session:
        repo = RepositorioPagamentosSQLAlchemy(session)

        pagamento = repo.buscar_pagamento(
            "tenant-a",
            "loja-1",
            pagamento_id,
        )

        assert pagamento is not None
        assert pagamento.status is PagamentoStatus.PAGO
        assert (
            pagamento.valor_pago.valor
            == Decimal("49.90")
        )
