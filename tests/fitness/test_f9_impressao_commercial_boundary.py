"""Fitness F9-B: boundary comercial da impressão sem Fake/test-runtime."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_application_impressao_owns_uow_and_commit() -> None:
    text = _text("application/impressao_transacoes.py")
    assert "UnitOfWorkV1" in text
    assert "with UnitOfWorkV1" in text
    assert "uow.commit()" in text
    assert "ServicoSpoolImpressao" in text


def test_commercial_boundary_has_no_fake_or_test_runtime() -> None:
    for path in (
        "application/impressao_transacoes.py",
        "app.py",
    ):
        text = _text(path)
        assert "ImpressoraFake" not in text
        assert "RuntimeImpressaoTeste" not in text
        assert "runtime_teste" not in text
        assert "migrations.impressao_v1" not in text


def test_spool_repository_does_not_own_commit() -> None:
    text = _text("core/impressao/adaptador_sqlalchemy.py")
    assert ".commit(" not in text


def test_official_commercial_migration_owns_print_schema() -> None:
    text = _text("migrations/runner.py")
    assert '"0012_restaurant_operations_runtime_v1"' in text
    assert "ImpressaoBase.metadata.create_all" in text
