from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import Column, Integer, String, create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from application import legacy_bootstrap_transacoes
from application.legacy_bootstrap_transacoes import (
    AplicacaoLegacyBootstrapV1,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao

Base = declarative_base()

TENANT = "tenant-bootstrap-sd1e"
UNIDADE = "unidade-bootstrap-sd1e"

AGORA = datetime(
    2026,
    8,
    28,
    12,
    0,
    tzinfo=UTC,
)


class ConfiguracaoMetaTeste(Base):
    __tablename__ = "configuracoes_meta"

    id = Column(
        Integer,
        primary_key=True,
    )
    gateway_provider = Column(
        String,
        nullable=True,
    )


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id="bootstrap-system",
        papeis=frozenset(
            {
                Papel.ADMINISTRADOR,
            }
        ),
        permissoes=frozenset(
            Permissao
        ),
        correlation_id=(
            "corr-bootstrap-sd1e"
        ),
        solicitado_em=datetime(
            2026,
            8,
            28,
            12,
            0,
            tzinfo=UTC,
        ),
        origem=(
            "tests.sd1e.legacy_bootstrap"
        ),
        unidades_permitidas=frozenset(
            {
                UNIDADE,
            }
        ),
    )


def _infra():
    engine = create_engine(
        "sqlite://",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    Base.metadata.create_all(
        engine
    )

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE
                fm_unidade_loja_legacy_v1 (
                    tenant_id VARCHAR(64) NOT NULL,
                    unidade_id VARCHAR(64) NOT NULL,
                    loja_id INTEGER NOT NULL,
                    ativo BOOLEAN NOT NULL
                )
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE insumos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    loja_id INTEGER NOT NULL,
                    nome VARCHAR(255) NOT NULL,
                    unidade_medida VARCHAR(32),
                    saldo_atual FLOAT,
                    estoque_minimo FLOAT,
                    custo_unitario FLOAT,
                    data_fabricacao DATETIME,
                    data_validade DATETIME,
                    dias_alerta_vencimento INTEGER
                )
                """
            )
        )

        conn.execute(
            text(
                """
                INSERT INTO
                    fm_unidade_loja_legacy_v1
                    (
                        tenant_id,
                        unidade_id,
                        loja_id,
                        ativo
                    )
                VALUES
                    (
                        :tenant,
                        :unidade,
                        7,
                        TRUE
                    )
                """
            ),
            {
                "tenant": TENANT,
                "unidade": UNIDADE,
            },
        )

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    application = (
        AplicacaoLegacyBootstrapV1(
            factory,
            ConfiguracaoMetaTeste,
        )
    )

    return (
        engine,
        application,
    )


def _total(
    engine,
    tabela: str,
) -> int:
    with Session(engine) as session:
        return int(
            session.execute(
                text(
                    f"SELECT COUNT(*) FROM {tabela}"
                )
            ).scalar_one()
        )


def test_bootstrap_teste_cria_gateway_e_insumos_em_uow() -> None:
    engine, application = _infra()

    alterado = application.executar(
        _contexto(),
        habilitar_gateway_teste=True,
        agora=AGORA,
    )

    assert alterado is True
    assert _total(
        engine,
        "configuracoes_meta",
    ) == 1
    assert _total(
        engine,
        "insumos",
    ) == 3

    with Session(engine) as session:
        provider = session.execute(
            text(
                """
                SELECT gateway_provider
                FROM configuracoes_meta
                """
            )
        ).scalar_one()

        nomes = session.execute(
            text(
                """
                SELECT nome
                FROM insumos
                ORDER BY id
                """
            )
        ).scalars().all()

    assert provider == "Mercado Pago"
    assert nomes == [
        "Hambúrguer 180g Angus",
        "Queijo Provolone / Cheddar",
        "Pão Brioche Artesanal",
    ]


def test_bootstrap_e_idempotente_quando_dados_ja_existem() -> None:
    engine, application = _infra()

    assert application.executar(
        _contexto(),
        habilitar_gateway_teste=True,
        agora=AGORA,
    )

    alterado = application.executar(
        _contexto(),
        habilitar_gateway_teste=True,
        agora=AGORA,
    )

    assert alterado is False
    assert _total(
        engine,
        "configuracoes_meta",
    ) == 1
    assert _total(
        engine,
        "insumos",
    ) == 3


def test_bootstrap_comercial_nao_cria_gateway_legado() -> None:
    engine, application = _infra()

    alterado = application.executar(
        _contexto(),
        habilitar_gateway_teste=False,
        agora=AGORA,
    )

    assert alterado is True
    assert _total(
        engine,
        "configuracoes_meta",
    ) == 0
    assert _total(
        engine,
        "insumos",
    ) == 3


def test_falha_no_bootstrap_faz_rollback_de_gateway_e_insumo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, application = _infra()

    real = (
        legacy_bootstrap_transacoes
        .inserir_insumo_legado
    )

    def falhar_depois_de_inserir(
        *args,
        **kwargs,
    ):
        real(
            *args,
            **kwargs,
        )

        raise RuntimeError(
            "falha_bootstrap"
        )

    monkeypatch.setattr(
        legacy_bootstrap_transacoes,
        "inserir_insumo_legado",
        falhar_depois_de_inserir,
    )

    with pytest.raises(
        RuntimeError,
        match="falha_bootstrap",
    ):
        application.executar(
            _contexto(),
            habilitar_gateway_teste=True,
            agora=AGORA,
        )

    assert _total(
        engine,
        "configuracoes_meta",
    ) == 0
    assert _total(
        engine,
        "insumos",
    ) == 0
