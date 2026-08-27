from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = Path(__file__).with_name(
    "transaction_ownership_baseline_v1.json"
)

TARGET_METHODS = {"commit", "rollback"}

EXCLUDED_DIRS = {
    ".git",
    ".tmp",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "playwright-report",
    "test-results",
    "node_modules",
    "migrations",
}


def _excluded(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()

    if rel.startswith("tests/"):
        return True

    return any(
        part in EXCLUDED_DIRS
        for part in path.parts
    )


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        left = _dotted_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr

    if isinstance(node, ast.Call):
        return _dotted_name(node.func)

    if isinstance(node, ast.Subscript):
        return _dotted_name(node.value)

    return ""


def _scan_transaction_calls() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for path in sorted(ROOT.rglob("*.py")):
        if _excluded(path):
            continue

        rel = path.relative_to(ROOT).as_posix()

        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=rel)
        except (UnicodeDecodeError, SyntaxError):
            continue

        parents: dict[ast.AST, ast.AST] = {}

        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            func = node.func

            if not isinstance(func, ast.Attribute):
                continue

            if func.attr not in TARGET_METHODS:
                continue

            current: ast.AST = node
            function_name = "<module>"

            while current in parents:
                current = parents[current]

                if isinstance(
                    current,
                    (ast.FunctionDef, ast.AsyncFunctionDef),
                ):
                    function_name = current.name
                    break

            records.append(
                {
                    "path": rel,
                    "function": function_name,
                    "operation": func.attr,
                    "receiver": _dotted_name(func.value),
                }
            )

    return records


def _signature(
    record: dict[str, Any],
) -> tuple[str, str, str, str]:
    return (
        str(record["path"]),
        str(record["function"]),
        str(record["receiver"]),
        str(record["operation"]),
    )


def _counter(
    records: list[dict[str, Any]],
) -> Counter[tuple[str, str, str, str]]:
    return Counter(
        _signature(record)
        for record in records
    )


def _baseline() -> dict[str, Any]:
    return json.loads(
        BASELINE_PATH.read_text(encoding="utf-8")
    )


def _baseline_counter(
    category: str,
) -> Counter[tuple[str, str, str, str]]:
    entries = _baseline()["categories"][category]

    result: Counter[
        tuple[str, str, str, str]
    ] = Counter()

    for entry in entries:
        signature = (
            entry["path"],
            entry["function"],
            entry["receiver"],
            entry["operation"],
        )

        result[signature] = int(entry["count"])

    return result


def _presentation(record: dict[str, Any]) -> bool:
    path = str(record["path"])
    name = Path(path).name

    return (
        path == "app.py"
        or path.startswith(
            ("http_api/", "infra/streamlit_app/")
        )
        or (
            path.startswith("core/")
            and name.startswith("ui_")
        )
    )


def _is_repository_path(path: str) -> bool:
    name = Path(path).name

    return (
        "adaptador_sqlalchemy" in name
        or "repositorio_sqlalchemy" in name
        or "persistencia_sqlalchemy" in name
    )


def _within_budget(
    current: Counter[tuple[str, str, str, str]],
    allowed: Counter[tuple[str, str, str, str]],
) -> bool:
    return all(
        count <= allowed.get(signature, 0)
        for signature, count in current.items()
    )


def _is_canonical_owner(
    record: dict[str, Any],
) -> bool:
    path = str(record["path"])
    receiver = str(record["receiver"]).casefold()

    if path == "infra/transacoes/uow.py":
        return True

    return (
        path.startswith("application/")
        and "uow" in receiver
    )


def _is_operational_exemption(
    record: dict[str, Any],
) -> bool:
    path = str(record["path"])

    return (
        path.startswith("scripts/")
        or path == "test_mode.py"
    )


def _matches_any_transitional_budget(
    record: dict[str, Any],
) -> bool:
    signature = _signature(record)

    for category in (
        "presentation_debt",
        "pdv_compatibility",
        "infra_pix_hidden",
        "integration_boundary_debt",
    ):
        if signature in _baseline_counter(category):
            return True

    return False


def test_af03_a_domain_no_commit_outside_pdv_compatibility() -> None:
    offenders = []

    for record in _scan_transaction_calls():
        path = str(record["path"])

        if not path.startswith("core/"):
            continue

        if Path(path).name.startswith("ui_"):
            continue

        if path.startswith("core/pdv/"):
            continue

        offenders.append(record)

    assert offenders == []


def test_af03_b_repositories_no_commit_outside_pdv_allowlist() -> None:
    current = [
        record
        for record in _scan_transaction_calls()
        if _is_repository_path(
            str(record["path"])
        )
    ]

    pdv = [
        record
        for record in current
        if str(record["path"]).startswith("core/pdv/")
    ]

    unexpected = [
        record
        for record in current
        if record not in pdv
    ]

    assert unexpected == []

    assert _within_budget(
        _counter(pdv),
        _baseline_counter("pdv_compatibility"),
    )


def test_af03_c_pix_hidden_commit_budget_can_only_fall() -> None:
    current = [
        record
        for record in _scan_transaction_calls()
        if record["path"]
        == "infra/integracoes/pix_durabilidade.py"
    ]

    assert _within_budget(
        _counter(current),
        _baseline_counter("infra_pix_hidden"),
    )


def test_af03_d_presentation_owner_budget_can_only_fall() -> None:
    current = [
        record
        for record in _scan_transaction_calls()
        if _presentation(record)
    ]

    assert _within_budget(
        _counter(current),
        _baseline_counter("presentation_debt"),
    )


def test_af03_e_pdv_compatibility_allowlist_cannot_expand() -> None:
    current = [
        record
        for record in _scan_transaction_calls()
        if str(record["path"]).startswith("core/pdv/")
    ]

    assert _within_budget(
        _counter(current),
        _baseline_counter("pdv_compatibility"),
    )


def test_af03_f_canonical_uow_contract_remains_explicit() -> None:
    signatures = _counter(
        _scan_transaction_calls()
    )

    assert signatures[
        (
            "infra/transacoes/uow.py",
            "commit",
            "self.session",
            "commit",
        )
    ] == 1

    assert signatures[
        (
            "infra/transacoes/uow.py",
            "rollback",
            "self.session",
            "rollback",
        )
    ] == 1

    assert signatures[
        (
            "infra/transacoes/uow.py",
            "__exit__",
            "self.session",
            "rollback",
        )
    ] == 1


def test_af03_g_checkout_uses_uow_not_raw_session_commit() -> None:
    checkout = [
        record
        for record in _scan_transaction_calls()
        if record["path"] == "application/checkout.py"
    ]

    assert _counter(checkout)[
        (
            "application/checkout.py",
            "executar_checkout_v1",
            "uow",
            "commit",
        )
    ] == 1

    assert all(
        "session"
        not in str(record["receiver"]).casefold()
        for record in checkout
    )


def test_af03_h_every_transaction_call_is_classified() -> None:
    unclassified = [
        record
        for record in _scan_transaction_calls()
        if not _is_canonical_owner(record)
        and not _is_operational_exemption(record)
        and not _matches_any_transitional_budget(record)
    ]

    assert unclassified == []


def test_af03_i_transitional_budget_is_monotonic() -> None:
    records = _scan_transaction_calls()

    current_debt = [
        record
        for record in records
        if _matches_any_transitional_budget(record)
    ]

    baseline = _baseline()

    baseline_total = sum(
        int(entry["count"])
        for category in baseline["categories"].values()
        for entry in category
    )

    assert len(current_debt) <= baseline_total


def test_af03_detects_artificial_new_transaction_owner() -> None:
    artificial = {
        "path": "core/novo/servicos.py",
        "function": "executar",
        "receiver": "session",
        "operation": "commit",
    }

    assert not _is_canonical_owner(artificial)
    assert not _is_operational_exemption(artificial)
    assert not _matches_any_transitional_budget(artificial)

def test_af03_j_http_core_has_no_raw_session_transaction_owner() -> None:
    current = [
        record
        for record in _scan_transaction_calls()
        if record["path"] == "http_api/app.py"
    ]

    raw_session = [
        record
        for record in current
        if "session"
        in str(record["receiver"]).casefold()
    ]

    assert raw_session == []


def test_af03_k_kds_ui_has_no_transaction_owner() -> None:
    kds_ui_paths = {
        "core/kds/ui_roteamento.py",
        "core/kds/ui_runtime.py",
    }

    offenders = [
        record
        for record in _scan_transaction_calls()
        if record["path"] in kds_ui_paths
    ]

    assert offenders == []


def test_af03_l_salao_ui_has_no_transaction_owner() -> None:
    offenders = [
        record
        for record in _scan_transaction_calls()
        if record["path"] == "core/salao/ui_streamlit.py"
    ]

    assert offenders == []


def test_af03_m_entrega_ui_has_no_transaction_owner() -> None:
    offenders = [
        record
        for record in _scan_transaction_calls()
        if record["path"] == "core/entrega/ui_streamlit.py"
    ]

    assert offenders == []
