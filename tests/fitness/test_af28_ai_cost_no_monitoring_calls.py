from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_IMPORT_PREFIXES = (
    "google.genai",
    "google.generativeai",
    "openai",
    "anthropic",
    "requests",
    "httpx",
    "urllib.request",
)


def _imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )
    encontrados: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            encontrados.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            encontrados.append(node.module)

    return tuple(encontrados)


def test_af28_cost_calculator_nao_faz_chamada_de_ia_ou_rede() -> None:
    path = Path("core/ai_cost.py")

    for modulo in _imports(path):
        assert not modulo.startswith(FORBIDDEN_IMPORT_PREFIXES)

    texto = path.read_text(encoding="utf-8").lower()

    assert "generate_content" not in texto
    assert "chat.completions" not in texto
    assert "responses.create" not in texto
    assert "http://" not in texto
    assert "https://" not in texto
