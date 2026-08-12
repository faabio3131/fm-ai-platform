from __future__ import annotations

import argparse
import importlib
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

from core.hardening import ServicoHardeningGateE, SnapshotIntegridade
from ops.homologacao.gate_e_runner import snapshot_integridade


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    source = Path(args.database).resolve()
    repo_root = Path(args.repo_root).resolve()
    output = Path(args.output).resolve()
    work_dir = output.parent
    work_dir.mkdir(parents=True, exist_ok=True)

    before_copy = work_dir / "migration-test-before.sqlite3"
    migrated_copy = work_dir / "migration-test-work.sqlite3"
    rollback_copy = work_dir / "migration-test-rollback.sqlite3"
    shutil.copy2(source, before_copy)
    shutil.copy2(source, migrated_copy)

    before = snapshot_integridade(before_copy)
    engine = create_engine(f"sqlite:///{migrated_copy}")
    applied: list[str] = []
    started = time.monotonic()
    integrity = "not-run"
    fk_errors: list[object] = []
    try:
        migrations_dir = repo_root / "migrations"
        for path in sorted(migrations_dir.glob("*_v1.py")):
            module = importlib.import_module(f"migrations.{path.stem}")
            upgrade = getattr(module, "upgrade", None)
            if callable(upgrade):
                upgrade(engine)
                applied.append(path.name)
        with engine.begin() as conn:
            integrity = str(conn.execute(text("PRAGMA integrity_check")).scalar_one())
            fk_errors = list(conn.execute(text("PRAGMA foreign_key_check")))
    finally:
        engine.dispose()
    duration_seconds = max(1, int(time.monotonic() - started))

    # Ensaio de rollback não destrutivo: reconstrução a partir da cópia pré-migração.
    shutil.copy2(before_copy, rollback_copy)
    rollback_snapshot = snapshot_integridade(rollback_copy)
    rollback_result = ServicoHardeningGateE().comparar_restore(
        SnapshotIntegridade(**before), SnapshotIntegridade(**rollback_snapshot)
    )

    payload = {
        "approved": integrity == "ok" and not fk_errors and bool(applied),
        "migration_files": applied,
        "duration_seconds": duration_seconds,
        "sqlite_integrity": integrity,
        "foreign_key_errors": len(fk_errors),
        "rollback_approved": rollback_result.aprovado,
        "rollback_strategy": "restore_pre_migration_test_copy_non_destructive",
        "rollback_divergences": list(rollback_result.divergencias),
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    for path in (before_copy, migrated_copy, rollback_copy):
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
