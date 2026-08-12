"""Integra a sessão ORM protegida no app.py por substituições exatas."""

from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: esperado 1 trecho, encontrado {count}")
    return text.replace(old, new, 1)


def main() -> int:
    original = APP.read_text(encoding="utf-8")
    updated = original
    updated = replace_once(
        updated,
        "from migrations.runner import assert_schema_current\n",
        "from infra.seguranca.session_guard import build_session_factory\n"
        "from migrations.runner import assert_schema_current\n",
        "import-session-guard",
    )
    updated = replace_once(
        updated,
        "SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)\n",
        "SessionLocal = build_session_factory(\n"
        "    engine=engine, commercial=RUNTIME_SETTINGS.commercial\n"
        ")\n",
        "session-factory",
    )
    updated = replace_once(
        updated,
        "    Text,\n    create_engine,\n)\n",
        "    Text,\n)\n",
        "remove-create-engine",
    )
    updated = replace_once(
        updated,
        "from sqlalchemy.orm import declarative_base, relationship, sessionmaker\n",
        "from sqlalchemy.orm import declarative_base, relationship\n",
        "remove-sessionmaker",
    )
    if updated != original:
        APP.write_text(updated, encoding="utf-8")
        print("Sessão comercial protegida integrada ao app.py.")
    else:
        print("Sessão comercial protegida já integrada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
