"""Gera e valida o baseline autoritativo do schema comercial V1."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from sqlalchemy import create_engine, event

from migrations.history_guard import (
    SCHEMA_ALGORITHM,
    SCHEMA_BASELINE_PATH,
    schema_digest,
)
from migrations.runner import run_migrations


def _head_aprovado(explicito: str | None) -> str:
    if explicito:
        return explicito.strip()
    github_head = os.getenv("GITHUB_HEAD_SHA", "").strip()
    if github_head:
        return github_head
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _schema_fresco() -> tuple[str, str, int]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    applied = run_migrations(engine)
    if not applied:
        raise RuntimeError("gerador esperava aplicar migrations em schema vazio")

    digest, table_count = schema_digest(engine)
    return engine.dialect.name, digest, table_count


def _payload(*, approved_head: str) -> dict[str, object]:
    dialect, digest, table_count = _schema_fresco()
    return {
        "algorithm": SCHEMA_ALGORITHM,
        "approved_head": approved_head,
        "dialect": dialect,
        "signature_sha256": digest,
        "table_count": table_count,
    }


def _serialized(payload: dict[str, object]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera/valida migrations/schema_baseline_v1.json a partir de schema fresco."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=SCHEMA_BASELINE_PATH,
        help="arquivo de destino do baseline",
    )
    parser.add_argument(
        "--approved-head",
        default=None,
        help="SHA de origem arquitetural aprovado; por padrão usa GITHUB_HEAD_SHA ou git HEAD",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="não grava; falha se o arquivo atual divergir do baseline calculado",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="imprime o baseline calculado sem gravar",
    )
    args = parser.parse_args()

    payload = _payload(approved_head=_head_aprovado(args.approved_head))
    rendered = _serialized(payload)

    if args.stdout:
        print(rendered, end="")
        return 0

    output = args.output.resolve()
    if args.check:
        if not output.exists():
            print(rendered, end="")
            raise SystemExit("schema baseline ausente")
        atual = json.loads(output.read_text(encoding="utf-8"))
        structural_keys = (
            "algorithm",
            "dialect",
            "signature_sha256",
            "table_count",
        )
        divergencias = {
            key: {"esperado": payload[key], "atual": atual.get(key)}
            for key in structural_keys
            if atual.get(key) != payload[key]
        }
        if divergencias:
            print(rendered, end="")
            raise SystemExit(
                "schema baseline desatualizado: "
                + json.dumps(divergencias, ensure_ascii=False, sort_keys=True)
            )
        print(
            "Schema baseline V1 confere: "
            f"sha256={payload['signature_sha256']} "
            f"table_count={payload['table_count']}"
        )
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".tmp")
    temp.write_text(rendered, encoding="utf-8")
    temp.replace(output)
    print(
        f"Baseline escrito em {output}: "
        f"sha256={payload['signature_sha256']} "
        f"table_count={payload['table_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
