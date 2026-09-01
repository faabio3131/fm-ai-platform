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


def test_f6a_pix_comercial_nao_usa_confirmacao_automatica_legada() -> None:
    app = Path("app.py").read_text(encoding="utf-8")
    assert "pix_confirmado=not modo_producao_ativo or _canary_pdv" not in app
    assert (
        'else bool(st.session_state.get("pdv_pix_confirmado", False))'
        in app
    )
    assert (
        'forma_pag_pdv.startswith("Pix") and not is_test_mode()'
        in app
    )


def test_f6a_executor_pix_sandbox_e_fail_closed_por_padrao() -> None:
    executor = Path("core/pdv/executor_canonico.py").read_text(encoding="utf-8")
    assert "permitir_pix_sandbox: bool = False" in executor
    assert "pix_sandbox_nao_autorizado" in executor
    assert "from core.pagamentos.adapters import ProvedorPagamentoFake" in executor
