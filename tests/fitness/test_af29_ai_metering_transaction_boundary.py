from __future__ import annotations

import ast
from pathlib import Path


def _calls(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            found.append(func.attr)
        elif isinstance(func, ast.Name):
            found.append(func.id)

    return tuple(found)


def test_af29_router_nao_controla_transacao_de_metering() -> None:
    calls = _calls(Path("core/ai_router.py"))

    assert "commit" not in calls
    assert "rollback" not in calls
    assert "begin" not in calls


def test_af29_commit_do_metering_fica_na_borda_de_infraestrutura() -> None:
    texto = Path("infra/ai_metering.py").read_text(encoding="utf-8")

    assert "session.commit()" in texto
    assert "class AIUsageDurableMetering" in texto
