from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from application import salao_transacoes
from application.salao_transacoes import AplicacaoSalaoV1
from core.pagamentos.modelos_orm import PaymentsBase
from core.salao import (
    RepositorioSalaoSQLAlchemy,
    SalaoBase,
    ServicoSalao,
)
from core.salao.modelos_orm import ComandaORM, MesaORM
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel

TENANT = "tenant-sd1e-salao"
UNIDADE = "unidade-sd1e-salao"
AGORA = datetime(2026, 8, 27, 19, 0, tzinfo=UTC)


def _contexto() -> ContextoExecucao:
    papel = Papel.GERENTE

    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id="gerente-sd1e-salao",
        papeis=frozenset({papel}),
        permissoes=MATRIZ_PADRAO[papel],
        correlation_id="corr-sd1e-salao",
        solicitado_em=AGORA,
        origem="tests.sd1e.salao",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _infra():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    PaymentsBase.metadata.create_all(engine)
    SalaoBase.metadata.create_all(engine)

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    with factory() as session:
        servico = ServicoSalao(
            RepositorioSalaoSQLAlchemy(session),
            agora=lambda: AGORA,
        )

        servico.cadastrar_mesa(
            _contexto(),
            mesa_id="mesa-1",
            codigo="01",
            capacidade=4,
            idempotency_key="seed-mesa-1",
        )

        session.commit()

    return engine, factory


def _app(factory) -> AplicacaoSalaoV1:
    return AplicacaoSalaoV1(
        factory,
        agora=lambda: AGORA,
    )


def test_application_salao_abrir_comanda_commita_integralmente() -> None:
    engine, factory = _infra()

    resultado = _app(factory).abrir_comanda(
        _contexto(),
        comanda_id="comanda-commit",
        numero="C-001",
        mesa_id="mesa-1",
        expected_mesa_version=1,
        idempotency_key="abrir-comanda-commit",
    )

    assert resultado.comanda_id == "comanda-commit"

    with Session(engine) as session:
        comanda = session.scalar(
            select(ComandaORM).where(
                ComandaORM.id == "comanda-commit",
                ComandaORM.tenant_id == TENANT,
                ComandaORM.unidade_id == UNIDADE,
            )
        )

        mesa = session.scalar(
            select(MesaORM).where(
                MesaORM.id == "mesa-1",
                MesaORM.tenant_id == TENANT,
                MesaORM.unidade_id == UNIDADE,
            )
        )

        assert comanda is not None
        assert comanda.status == "aberta"

        assert mesa is not None
        assert mesa.status == "ocupada"


def test_application_salao_rollback_remove_write_parcial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, factory = _infra()

    real = salao_transacoes.ServicoSalao.abrir_comanda

    def falhar_depois_do_write(
        self,
        *args,
        **kwargs,
    ):
        real(
            self,
            *args,
            **kwargs,
        )

        raise RuntimeError("falha_depois_do_write_salao")

    monkeypatch.setattr(
        salao_transacoes.ServicoSalao,
        "abrir_comanda",
        falhar_depois_do_write,
    )

    with pytest.raises(
        RuntimeError,
        match="falha_depois_do_write_salao",
    ):
        _app(factory).abrir_comanda(
            _contexto(),
            comanda_id="comanda-rollback",
            numero="C-ROLLBACK",
            mesa_id="mesa-1",
            expected_mesa_version=1,
            idempotency_key="abrir-comanda-rollback",
        )

    with Session(engine) as session:
        comanda = session.scalar(
            select(ComandaORM).where(
                ComandaORM.id == "comanda-rollback",
                ComandaORM.tenant_id == TENANT,
                ComandaORM.unidade_id == UNIDADE,
            )
        )

        mesa = session.scalar(
            select(MesaORM).where(
                MesaORM.id == "mesa-1",
                MesaORM.tenant_id == TENANT,
                MesaORM.unidade_id == UNIDADE,
            )
        )

        assert comanda is None

        assert mesa is not None
        assert mesa.status == "livre"
        assert mesa.versao == 1


def test_application_salao_cancelamento_commita_e_libera_mesa() -> None:
    engine, factory = _infra()
    app = _app(factory)

    aberta = app.abrir_comanda(
        _contexto(),
        comanda_id="comanda-cancelar",
        numero="C-CANCELAR",
        mesa_id="mesa-1",
        expected_mesa_version=1,
        idempotency_key="abrir-comanda-cancelar",
    )

    cancelada = app.cancelar_comanda(
        _contexto(),
        comanda_id=aberta.comanda_id,
        expected_version=aberta.versao,
        idempotency_key="cancelar-comanda",
        pedidos_resolvidos=True,
    )

    assert cancelada.status.value == "cancelada"

    with Session(engine) as session:
        mesa = session.scalar(
            select(MesaORM).where(
                MesaORM.id == "mesa-1",
                MesaORM.tenant_id == TENANT,
                MesaORM.unidade_id == UNIDADE,
            )
        )

        comanda = session.scalar(
            select(ComandaORM).where(
                ComandaORM.id == "comanda-cancelar",
                ComandaORM.tenant_id == TENANT,
                ComandaORM.unidade_id == UNIDADE,
            )
        )

        assert mesa is not None
        assert mesa.status == "livre"

        assert comanda is not None
        assert comanda.status == "cancelada"
