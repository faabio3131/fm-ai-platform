from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    encontrados: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            encontrados.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            encontrados.add(node.module)
    return encontrados


def test_hardening_e_puro_sem_orm_http_ou_app_monolitico() -> None:
    proibidos = {"app", "requests", "sqlalchemy", "httpx"}
    for path in (ROOT / "core" / "hardening").glob("*.py"):
        imports = _imports(path)
        assert not any(
            nome == proibido or nome.startswith(f"{proibido}.")
            for nome in imports
            for proibido in proibidos
        ), f"{path} acoplou hardening a dependencia proibida: {sorted(imports)}"


def test_runbook_gate_e_cobre_restore_rollback_slo_privacidade_e_go_no_go() -> None:
    runbook = (ROOT / "docs" / "runbooks" / "gate-e-release-v1.md").read_text(
        encoding="utf-8"
    ).lower()
    for termo in (
        "restore",
        "rollback",
        "rto",
        "rpo",
        "slo",
        "lgpd",
        "acessibilidade",
        "go/no-go",
        "backup",
        "checksum",
        "dlq",
    ):
        assert termo in runbook


def test_documentacao_declara_que_ci_sintetico_nao_autoriza_producao() -> None:
    doc = (ROOT / "docs" / "hardening-transversal-v1.md").read_text(
        encoding="utf-8"
    ).lower()
    assert "evidência sintética não autoriza release" in doc
    assert "nenhum teste desta pr toca banco ou credencial real" in doc
    assert "no-go" in doc
