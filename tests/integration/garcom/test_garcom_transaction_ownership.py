from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from application import garcom_transacoes
from application.garcom_transacoes import AplicacaoGarcomV1
from core.garcom import ErroGarcom
from core.kds.modelos_orm import KDSBase
from core.salao.modelos_orm import ComandaORM, MesaORM, SalaoBase
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel

TENANT = "tenant-sd1e-garcom"
UNIDADE = "unidade-sd1e-garcom"
AGORA = datetime(2026, 8, 27, 21, 0, tzinfo=UTC)


def _contexto(
    *,
    usuario_id: str = "garcom-1",
) -> ContextoExecucao:
    papel = Papel.GARCOM

    return ContextoExecucao(
        TENANT,
        UNIDADE,
        usuario_id,
        frozenset({papel}),
        MATRIZ_PADRAO[papel],
        f"corr-sd1e-{usuario_id}",
        AGORA,
        "tests.sd1e.garcom",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _infra():
    engine = create_engine(
        "sqlite://",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    SalaoBase.metadata.create_all(engine)
    KDSBase.metadata.create_all(engine)

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    with factory() as session:
        session.add_all(
            [
                MesaORM(
                    id="mesa-livre",
                    tenant_id=TENANT,
                    unidade_id=UNIDADE,
                    codigo="01",
                    nome="Livre",
                    capacidade=4,
                    status="livre",
                    ativo=True,
                    versao=1,
                    criado_em=AGORA,
                    atualizado_em=AGORA,
                ),
                MesaORM(
                    id="mesa-garcom",
                    tenant_id=TENANT,
                    unidade_id=UNIDADE,
                    codigo="02",
                    nome="Garcom",
                    capacidade=4,
                    status="ocupada",
                    ativo=True,
                    versao=2,
                    criado_em=AGORA,
                    atualizado_em=AGORA,
                ),
                MesaORM(
                    id="mesa-outro",
                    tenant_id=TENANT,
                    unidade_id=UNIDADE,
                    codigo="03",
                    nome="Outro",
                    capacidade=4,
                    status="ocupada",
                    ativo=True,
                    versao=2,
                    criado_em=AGORA,
                    atualizado_em=AGORA,
                ),
                ComandaORM(
                    id="comanda-garcom",
                    tenant_id=TENANT,
                    unidade_id=UNIDADE,
                    mesa_id="mesa-garcom",
                    numero="C-001",
                    status="em_consumo",
                    responsavel_id="garcom-1",
                    aberta_em=AGORA,
                    fechada_em=None,
                    total=Decimal("20.00"),
                    saldo=Decimal("20.00"),
                    recebimento_posterior_autorizado=False,
                    versao=2,
                ),
                ComandaORM(
                    id="comanda-outro",
                    tenant_id=TENANT,
                    unidade_id=UNIDADE,
                    mesa_id="mesa-outro",
                    numero="C-002",
                    status="em_consumo",
                    responsavel_id="garcom-2",
                    aberta_em=AGORA,
                    fechada_em=None,
                    total=Decimal("15.00"),
                    saldo=Decimal("15.00"),
                    recebimento_posterior_autorizado=False,
                    versao=2,
                ),
            ]
        )

        session.commit()

    return engine, factory


def _app(factory) -> AplicacaoGarcomV1:
    return AplicacaoGarcomV1(
        factory,
        agora=lambda: AGORA,
    )


def test_application_garcom_solicitar_conta_commita() -> None:
    engine, factory = _infra()

    resultado = _app(factory).solicitar_conta(
        _contexto(),
        comanda_id="comanda-garcom",
        expected_version=2,
        idempotency_key="garcom-conta-commit",
    )

    assert resultado.status.value == "conta_solicitada"
    assert resultado.versao == 3

    with Session(engine) as session:
        row = session.scalar(
            select(ComandaORM).where(
                ComandaORM.id == "comanda-garcom",
                ComandaORM.tenant_id == TENANT,
                ComandaORM.unidade_id == UNIDADE,
            )
        )

        assert row is not None
        assert row.status == "conta_solicitada"
        assert row.versao == 3


def test_application_garcom_rollback_remove_write_parcial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, factory = _infra()

    real = garcom_transacoes.ServicoGarcom.solicitar_conta

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

        raise RuntimeError(
            "falha_depois_do_write_garcom"
        )

    monkeypatch.setattr(
        garcom_transacoes.ServicoGarcom,
        "solicitar_conta",
        falhar_depois_do_write,
    )

    with pytest.raises(
        RuntimeError,
        match="falha_depois_do_write_garcom",
    ):
        _app(factory).solicitar_conta(
            _contexto(),
            comanda_id="comanda-garcom",
            expected_version=2,
            idempotency_key="garcom-conta-rollback",
        )

    with Session(engine) as session:
        row = session.scalar(
            select(ComandaORM).where(
                ComandaORM.id == "comanda-garcom",
                ComandaORM.tenant_id == TENANT,
                ComandaORM.unidade_id == UNIDADE,
            )
        )

        assert row is not None
        assert row.status == "em_consumo"
        assert row.versao == 2


def test_application_garcom_preserva_alcada_sem_commit() -> None:
    engine, factory = _infra()

    with pytest.raises(ErroGarcom) as erro:
        _app(factory).solicitar_conta(
            _contexto(usuario_id="garcom-1"),
            comanda_id="comanda-outro",
            expected_version=2,
            idempotency_key="garcom-fora-alcada",
        )

    assert erro.value.codigo == "comanda_fora_alcada"

    with Session(engine) as session:
        row = session.scalar(
            select(ComandaORM).where(
                ComandaORM.id == "comanda-outro",
                ComandaORM.tenant_id == TENANT,
                ComandaORM.unidade_id == UNIDADE,
            )
        )

        assert row is not None
        assert row.status == "em_consumo"
        assert row.versao == 2
