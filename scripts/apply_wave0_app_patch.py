"""Patch determinístico da integração Wave0 no app legado.

Este script existe para uma alteração mecânica controlada no app.py grande. Ele
exige exatamente os trechos conhecidos e falha sem escrever se o arquivo divergir.
"""

from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"patch {label}: esperado 1 trecho, encontrado {count}")
    return text.replace(old, new, 1)


def main() -> int:
    original = APP.read_text(encoding="utf-8")
    updated = original

    updated = _replace_once(
        updated,
        'from premium_ui import apply_premium_visual_system\n',
        'from premium_ui import apply_premium_visual_system\n'
        'from core.runtime import (\n'
        '    build_engine as build_runtime_engine,\n'
        '    load_runtime_settings,\n'
        ')\n'
        'from infra.streamlit_app.auth_ui import (\n'
        '    render_identity_sidebar,\n'
        '    require_authentication,\n'
        ')\n',
        label="imports-runtime-auth",
    )

    updated = _replace_once(
        updated,
        'TEST_RUNTIME = build_runtime()\n'
        'os.makedirs(TEST_RUNTIME.files_dir, exist_ok=True)\n\n'
        'DATABASE_URL = TEST_RUNTIME.database_url\n'
        'engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})\n',
        'TEST_RUNTIME = build_runtime()\n'
        'os.makedirs(TEST_RUNTIME.files_dir, exist_ok=True)\n\n'
        'RUNTIME_SETTINGS = load_runtime_settings(\n'
        '    test_database_url=TEST_RUNTIME.database_url if is_test_mode() else None\n'
        ')\n'
        'DATABASE_URL = RUNTIME_SETTINGS.database_url\n'
        'engine = build_runtime_engine(RUNTIME_SETTINGS)\n',
        label="database-runtime",
    )

    updated = _replace_once(
        updated,
        '    upgrade_pdv_v1(engine)\n\n\ndef get_db():\n',
        '    upgrade_pdv_v1(engine)\n\n\n'
        'CURRENT_IDENTITY = require_authentication(\n'
        '    session_factory=SessionLocal,\n'
        '    settings=RUNTIME_SETTINGS,\n'
        ')\n\n\n'
        'def get_db():\n',
        label="authentication-gate",
    )

    updated = _replace_once(
        updated,
        '    st.success("Conectado como:\\n**admin@micaburger.com**")\n'
        '    st.info("🏪 **Loja Ativa:**\\nMica Burguer & Restaurante")\n',
        '    render_identity_sidebar(CURRENT_IDENTITY, RUNTIME_SETTINGS)\n',
        label="identity-sidebar",
    )

    if updated == original:
        print("app.py já contém a integração Wave0; nenhuma alteração necessária.")
        return 0

    APP.write_text(updated, encoding="utf-8")
    print("app.py atualizado com runtime comercial e autenticação V1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
