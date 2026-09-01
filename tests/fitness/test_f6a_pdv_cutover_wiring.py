"""Fitness gate F6-A: o runtime comercial deve apontar para o PDV canônico."""

from pathlib import Path

from core.pdv.executor_canonico import ExecutorAutoritativoCanonicoSQLAlchemy
from core.pdv.executores import ExecutorAutoritativoSQLAlchemy


def test_f6a_executor_publico_e_o_executor_canonico() -> None:
    assert ExecutorAutoritativoSQLAlchemy is ExecutorAutoritativoCanonicoSQLAlchemy


def test_f6a_app_injeta_runtime_comercial_no_rollout() -> None:
    app = Path("app.py").read_text(encoding="utf-8")
    assert (
        "_pdv_rollout = carregar_rollout_ambiente("
        "runtime_settings=RUNTIME_SETTINGS)"
    ) in app
    assert "_pdv_terminal_id = carregar_terminal_pdv_ambiente()" in app
    assert 'os.getenv("FM_AI_TEST_TERMINAL", "pdv-default")' not in app
