"""Aplica migrations comerciais V1 usando o mesmo contrato de runtime da aplicação."""

from __future__ import annotations

from dotenv import load_dotenv

from core.runtime import build_engine, check_database_health, load_runtime_settings
from migrations.runner import run_migrations


def main() -> int:
    load_dotenv(dotenv_path=".env")
    settings = load_runtime_settings()
    engine = build_engine(settings)
    health = check_database_health(engine)
    if not health.ok:
        raise RuntimeError(health.detail)
    applied = run_migrations(engine)
    if applied:
        print("Migrations aplicadas:", ", ".join(applied))
    else:
        print("Schema comercial V1 ja esta atualizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
