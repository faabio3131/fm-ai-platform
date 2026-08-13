"""Gera backup verificável do banco configurado no runtime V1."""

from __future__ import annotations

import argparse
from pathlib import Path

from core.runtime.backup import backup_database
from core.runtime.config import load_runtime_settings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    settings = load_runtime_settings()
    manifest = backup_database(settings.database_url, args.destination)
    print(
        f"Backup OK: {manifest.file_name} | {manifest.size_bytes} bytes | "
        f"sha256={manifest.sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
