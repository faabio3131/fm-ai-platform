from dataclasses import replace
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from core.impressao import ErroImpressao, JobImpressao, RepositorioSpoolSQLAlchemy
from core.impressao.modelos import StatusImpressao
from migrations.impressao_v1 import downgrade, upgrade

AGORA = datetime(2026, 8, 11, 17, 0, tzinfo=timezone.utc)


def _job(*, job_id: str = "job-1", dedup_key: str = "dedup-1") -> JobImpressao:
    return JobImpressao(
        job_id=job_id,
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        setor_id="setor-1",
        producao_id="producao-1",
        pedido_id="pedido-1",
        pedido_item_id="item-1",
        impressora_id="printer-1",
        dedup_key=dedup_key,
        documento_hash="a" * 64,
        conteudo="ticket operacional",
        status=StatusImpressao.PENDENTE,
        tentativa=0,
        max_tentativas=3,
        versao=1,
        criado_em=AGORA,
        atualizado_em=AGORA,
    )


def test_round_trip_dedup_escopo_e_cas() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    upgrade(engine)

    with Session(engine) as session:
        repositorio = RepositorioSpoolSQLAlchemy(session)
        original = _job()
        repositorio.adicionar(original)
        session.commit()

        assert repositorio.buscar("tenant-1", "unidade-1", "job-1") == original
        assert repositorio.buscar("outro", "unidade-1", "job-1") is None
        assert repositorio.buscar_por_dedup(
            "tenant-1", "unidade-1", "dedup-1"
        ) == original

        atualizado = replace(
            original,
            status=StatusImpressao.IMPRESSO,
            tentativa=1,
            versao=2,
            atualizado_em=AGORA,
        )
        repositorio.atualizar(atualizado, versao_esperada=1)
        session.commit()
        assert repositorio.buscar("tenant-1", "unidade-1", "job-1") == atualizado

        concorrente = replace(atualizado, versao=3)
        with pytest.raises(ErroImpressao) as exc:
            repositorio.atualizar(concorrente, versao_esperada=1)
        assert exc.value.codigo == "job_impressao_concorrente"
        session.rollback()

    downgrade(engine)
    assert "impressao_jobs_v1" not in inspect(engine).get_table_names()


def test_unique_dedup_persistente() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    upgrade(engine)

    with Session(engine) as session:
        repositorio = RepositorioSpoolSQLAlchemy(session)
        repositorio.adicionar(_job())
        session.commit()

        with pytest.raises(ErroImpressao) as exc:
            repositorio.adicionar(_job(job_id="job-2"))
        assert exc.value.codigo == "conflito_idempotencia_impressao"
        session.rollback()


def test_migration_recusa_banco_real() -> None:
    engine = create_engine("sqlite+pysqlite:///banco_erp_local.db")
    with pytest.raises(RuntimeError, match="explicitamente efêmero/teste"):
        upgrade(engine)
