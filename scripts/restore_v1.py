"""Restaura backup V1 com confirmação explícita do nome do banco-alvo."""

from __future__ import annotations

import argparse
from pathlib import Path

from core.runtime.backup import restore_database
from core.runtime.config import load_runtime_settings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("backup_file", type=Path)
    parser.add_argument("--confirm-database", required=True)
    args = parser.parse_args()
    settings = load_runtime_settings()
    restore_database(
        settings.database_url,
        args.backup_file,
        confirm_database=args.confirm_database,
    )
    print("Restore concluido e checksum validado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
