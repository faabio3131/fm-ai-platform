import ast
from pathlib import Path


def test_core_eventos_nao_importa_dependencias_proibidas() -> None:
    proibidas = (
        "streamlit",
        "sqlalchemy",
        "app",
        "requests",
        "google.genai",
        "core.database",
    )
    for arquivo in Path("core/eventos").glob("*.py"):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        imports: list[str] = []
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                imports.extend(alias.name for alias in no.names)
            elif isinstance(no, ast.ImportFrom) and no.module:
                imports.append(no.module)
        assert not any(
            nome == item or nome.startswith(f"{item}.")
            for nome in imports
            for item in proibidas
        ), arquivo
