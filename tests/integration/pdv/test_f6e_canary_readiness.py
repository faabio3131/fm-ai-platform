import pytest
from sqlalchemy import func, select

from core.pdv.adaptadores_sqlalchemy import RepositorioPDVSQLAlchemy
from core.pdv.modelos_orm import ReconciliacaoPDVORM
from core.pdv.reconciliacao import RecomendacaoCoortePDV
from core.pdv.roteamento import ModoPDV
from core.pedidos.modelos_orm import PedidoORM

from .helpers import executar


def test_retry_reutiliza_checkout_e_readiness_sem_duplicar_reconciliacao(
    fabrica, contexto, entrada
) -> None:
    primeira = executar(fabrica, contexto, entrada, ModoPDV.AUTHORITATIVE_CANARY)
    segunda = executar(fabrica, contexto, entrada, ModoPDV.AUTHORITATIVE_CANARY)

    assert primeira.sucesso is True
    assert segunda.sucesso is True
    assert segunda.idempotente is True

    with fabrica() as session:
        assert session.scalar(select(func.count()).select_from(PedidoORM)) == 1
        assert (
            session.scalar(select(func.count()).select_from(ReconciliacaoPDVORM))
            == 1
        )
        resumo = RepositorioPDVSQLAlchemy(session).resumir_readiness(
            contexto.tenant_id,
            contexto.unidade_id,
        )

    assert resumo.total_registros == 1
    assert resumo.recomendacao is RecomendacaoCoortePDV.AMPLIACAO_ELEGIVEL
    assert len(resumo.metricas) == 1
    metrica = resumo.metricas[0]
    assert metrica.modo == "authoritative_canary"
    assert metrica.terminal_id == entrada.terminal_id
    assert metrica.total == 1
    assert metrica.conciliados == 1


def test_readiness_divergente_e_estritamente_read_only(
    fabrica, contexto, entrada
) -> None:
    resultado = executar(fabrica, contexto, entrada, ModoPDV.AUTHORITATIVE_CANARY)
    assert resultado.sucesso is True

    with fabrica() as session:
        row = session.scalar(select(ReconciliacaoPDVORM))
        assert row is not None
        row.status = "divergente"
        row.divergencias = ["valor_divergente"]
        session.commit()

    with fabrica() as session:
        row_antes = session.scalar(select(ReconciliacaoPDVORM))
        assert row_antes is not None
        snapshot_antes = (
            row_antes.status,
            tuple(row_antes.divergencias),
            row_antes.idempotency_key,
        )

        repo = RepositorioPDVSQLAlchemy(session)
        primeiro = repo.resumir_readiness(contexto.tenant_id, contexto.unidade_id)
        segundo = repo.resumir_readiness(contexto.tenant_id, contexto.unidade_id)

        session.expire_all()
        row_depois = session.scalar(select(ReconciliacaoPDVORM))
        assert row_depois is not None
        snapshot_depois = (
            row_depois.status,
            tuple(row_depois.divergencias),
            row_depois.idempotency_key,
        )

        assert primeiro == segundo
        assert primeiro.recomendacao is RecomendacaoCoortePDV.REDUZIR
        assert primeiro.divergentes == 1
        assert snapshot_depois == snapshot_antes
        assert not session.new
        assert not session.dirty
        assert not session.deleted


@pytest.mark.parametrize("limite", [0, -1, 10_001])
def test_readiness_limite_falha_fechado(fabrica, contexto, limite: int) -> None:
    with fabrica() as session:
        repo = RepositorioPDVSQLAlchemy(session)
        with pytest.raises(ValueError, match="limite_readiness_pdv_invalido"):
            repo.resumir_readiness(
                contexto.tenant_id,
                contexto.unidade_id,
                limite=limite,
            )
