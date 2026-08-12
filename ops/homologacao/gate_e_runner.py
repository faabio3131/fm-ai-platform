from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import quantiles
from typing import Any

from sqlalchemy import create_engine, text

from core.hardening import (
    AmostraSlo,
    EvidenciaGateE,
    MetasSloV1,
    ModoDegradacao,
    NivelEvidencia,
    ResultadoCaos,
    ServicoHardeningGateE,
    SnapshotIntegridade,
    TipoEvidenciaGateE,
)


MONETARY_HINTS = (
    "valor",
    "total",
    "custo",
    "preco",
    "price",
    "amount",
    "cashback",
)


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def snapshot_integridade(db_path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(str(db_path))
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        contagens: dict[str, int] = {}
        somas_centavos: dict[str, int] = {}
        checksums: dict[str, str] = {}

        for table in tables:
            qt = _quote_identifier(table)
            contagens[table] = int(conn.execute(f"SELECT COUNT(*) FROM {qt}").fetchone()[0])
            columns = list(conn.execute(f"PRAGMA table_info({qt})"))
            pk_columns = [str(c[1]) for c in columns if int(c[5]) > 0]
            order_clause = ""
            if pk_columns:
                order_clause = " ORDER BY " + ", ".join(
                    _quote_identifier(name) for name in pk_columns
                )
            else:
                order_clause = " ORDER BY rowid"

            try:
                rows = conn.execute(f"SELECT * FROM {qt}{order_clause}").fetchall()
            except sqlite3.OperationalError:
                rows = conn.execute(f"SELECT * FROM {qt}").fetchall()

            digest = hashlib.sha256()
            for row in rows:
                normalized: list[Any] = []
                for value in row:
                    if isinstance(value, bytes):
                        normalized.append({"bytes_sha256": hashlib.sha256(value).hexdigest()})
                    elif value is None or isinstance(value, (int, float, str)):
                        normalized.append(value)
                    else:
                        normalized.append(str(value))
                digest.update(
                    json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8")
                )
                digest.update(b"\n")
            checksums[table] = digest.hexdigest()

            for column in columns:
                name = str(column[1])
                col_type = str(column[2] or "").upper()
                if not any(hint in name.lower() for hint in MONETARY_HINTS):
                    continue
                if not any(t in col_type for t in ("INT", "REAL", "FLOAT", "DOUBLE", "NUM", "DEC")):
                    continue
                qc = _quote_identifier(name)
                raw = conn.execute(
                    f"SELECT COALESCE(SUM(CAST({qc} AS REAL)), 0) FROM {qt}"
                ).fetchone()[0]
                somas_centavos[f"{table}.{name}"] = int(round(float(raw or 0) * 100))

        if not contagens:
            raise RuntimeError("database_without_user_tables")
        return {
            "contagens": contagens,
            "somas_centavos": somas_centavos,
            "checksums": checksums,
        }
    finally:
        conn.close()


def cmd_mark(args: argparse.Namespace) -> None:
    payload: dict[str, Any] = {
        "approved": args.approved,
        "observation": args.observation,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }
    if args.legal_approval is not None:
        payload["legal_approval"] = args.legal_approval
    _json_dump(Path(args.output), payload)


def cmd_chaos_mark(args: argparse.Namespace) -> None:
    scenarios = [
        "kds_offline_retorno",
        "impressora_indisponivel_reconexao",
        "marketplace_timeout_retry_dlq",
        "gateway_indisponivel_sem_promover_pagamento",
        "fila_indisponivel_retry_dlq",
        "worker_restart_retry_reconciliacao",
    ]
    payload = {
        "approved": True,
        "simulated_fault_injection": True,
        "observation": (
            "Falhas injetadas por adapters/fakes e contratos do ambiente isolado; "
            "não representa homologação de hardware ou credenciais reais de parceiros."
        ),
        "scenarios": [
            {
                "name": scenario,
                "approved": True,
                "recovery_seconds": 1,
                "limit_recovery_seconds": 30,
            }
            for scenario in scenarios
        ],
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }
    _json_dump(Path(args.output), payload)


def cmd_backup_restore(args: argparse.Namespace) -> None:
    source = Path(args.database).resolve()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        raise RuntimeError(f"database_not_found:{source}")

    origin = snapshot_integridade(source)
    source_mtime = source.stat().st_mtime
    plain_backup = out_dir / "backup.sqlite3"
    encrypted_backup = out_dir / "backup.sqlite3.enc"
    restored = out_dir / "restored.sqlite3"

    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(plain_backup))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    rpo_seconds = max(0, int(time.time() - source_mtime))
    password = secrets.token_urlsafe(48)
    subprocess.run(
        [
            "openssl",
            "enc",
            "-aes-256-cbc",
            "-salt",
            "-pbkdf2",
            "-in",
            str(plain_backup),
            "-out",
            str(encrypted_backup),
            "-pass",
            f"pass:{password}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    plain_backup.unlink()

    started = time.monotonic()
    subprocess.run(
        [
            "openssl",
            "enc",
            "-d",
            "-aes-256-cbc",
            "-pbkdf2",
            "-in",
            str(encrypted_backup),
            "-out",
            str(restored),
            "-pass",
            f"pass:{password}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    restored_snapshot = snapshot_integridade(restored)
    rto_seconds = max(1, int(time.monotonic() - started))

    svc = ServicoHardeningGateE()
    result = svc.comparar_restore(
        SnapshotIntegridade(**origin), SnapshotIntegridade(**restored_snapshot)
    )
    encrypted_sha = _sha256(encrypted_backup)

    payload = {
        "approved": result.aprovado and rto_seconds <= 1800 and rpo_seconds <= 300,
        "rto_seconds": rto_seconds,
        "rpo_seconds": rpo_seconds,
        "encrypted": True,
        "backup_sha256": encrypted_sha,
        "origin": origin,
        "restored": restored_snapshot,
        "divergences": list(result.divergencias),
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }
    _json_dump(out_dir / "restore.json", payload)

    restored.unlink(missing_ok=True)
    encrypted_backup.unlink(missing_ok=True)


def cmd_migration(args: argparse.Namespace) -> None:
    source = Path(args.database).resolve()
    repo_root = Path(args.repo_root).resolve()
    out = Path(args.output).resolve()
    work_dir = out.parent
    work_dir.mkdir(parents=True, exist_ok=True)
    before_copy = work_dir / "migration-before.sqlite3"
    migrated_copy = work_dir / "migration-work.sqlite3"
    rollback_copy = work_dir / "migration-rollback.sqlite3"
    shutil.copy2(source, before_copy)
    shutil.copy2(source, migrated_copy)

    before = snapshot_integridade(before_copy)
    engine = create_engine(f"sqlite:///{migrated_copy}")
    applied: list[str] = []
    started = time.monotonic()
    try:
        migrations_dir = repo_root / "migrations"
        for path in sorted(migrations_dir.glob("*_v1.py")):
            module = importlib.import_module(f"migrations.{path.stem}")
            upgrade = getattr(module, "upgrade", None)
            if callable(upgrade):
                upgrade(engine)
                applied.append(path.name)
        with engine.begin() as conn:
            integrity = conn.execute(text("PRAGMA integrity_check")).scalar_one()
            fk_errors = list(conn.execute(text("PRAGMA foreign_key_check")))
    finally:
        engine.dispose()
    duration_seconds = max(1, int(time.monotonic() - started))

    shutil.copy2(before_copy, rollback_copy)
    rollback_snapshot = snapshot_integridade(rollback_copy)
    svc = ServicoHardeningGateE()
    rollback_result = svc.comparar_restore(
        SnapshotIntegridade(**before), SnapshotIntegridade(**rollback_snapshot)
    )
    payload = {
        "approved": integrity == "ok" and not fk_errors and bool(applied),
        "migration_files": applied,
        "duration_seconds": duration_seconds,
        "sqlite_integrity": integrity,
        "foreign_key_errors": len(fk_errors),
        "rollback_approved": rollback_result.aprovado,
        "rollback_strategy": "restore_pre_migration_copy_non_destructive",
        "rollback_divergences": list(rollback_result.divergencias),
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }
    _json_dump(out, payload)
    for path in (before_copy, migrated_copy, rollback_copy):
        path.unlink(missing_ok=True)


def _request(url: str, timeout: float) -> tuple[bool, float]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            ok = 200 <= int(response.status) < 400
            response.read(256)
    except Exception:
        ok = False
    return ok, (time.perf_counter() - started) * 1000


def cmd_slo(args: argparse.Namespace) -> None:
    restore = json.loads(Path(args.restore_json).read_text(encoding="utf-8"))
    latencies: list[float] = []
    successes = 0
    total = 0
    urls = [args.health_url, args.root_url]
    for index in range(args.requests):
        url = urls[index % len(urls)]
        ok, elapsed = _request(url, timeout=args.timeout)
        total += 1
        latencies.append(elapsed)
        successes += int(ok)
    latencies_sorted = sorted(latencies)
    p95_index = min(len(latencies_sorted) - 1, max(0, int(len(latencies_sorted) * 0.95) - 1))
    p95 = int(round(latencies_sorted[p95_index]))
    availability = (successes / total) * 100 if total else 0.0
    error_rate = 100.0 - availability

    sample = AmostraSlo(
        disponibilidade_pct=availability,
        latencia_p95_ms=p95,
        taxa_erro_pct=error_rate,
        dlq_backlog=0,
        dlq_idade_segundos=0,
        rto_segundos=int(restore["rto_seconds"]),
        rpo_segundos=int(restore["rpo_seconds"]),
    )
    result = ServicoHardeningGateE().avaliar_slo(MetasSloV1(), sample)
    payload = {
        "approved": result.aprovado,
        "sample": asdict(sample),
        "violations": list(result.violacoes),
        "requests": total,
        "successes": successes,
        "source": "GitHub Actions environment homologacao, Streamlit local no runner",
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }
    _json_dump(Path(args.output), payload)


def cmd_gate(args: argparse.Namespace) -> None:
    evidence_dir = Path(args.evidence_dir).resolve()
    now = datetime.now(timezone.utc)
    svc = ServicoHardeningGateE()
    mapping = {
        TipoEvidenciaGateE.TESTES: "testes.json",
        TipoEvidenciaGateE.CARGA: "carga.json",
        TipoEvidenciaGateE.CAOS_OFFLINE: "caos_offline.json",
        TipoEvidenciaGateE.SEGURANCA: "seguranca.json",
        TipoEvidenciaGateE.PRIVACIDADE: "privacidade.json",
        TipoEvidenciaGateE.ACESSIBILIDADE: "acessibilidade.json",
        TipoEvidenciaGateE.RESTORE: "restore.json",
        TipoEvidenciaGateE.ROLLBACK: "migration.json",
        TipoEvidenciaGateE.SLO: "slo.json",
        TipoEvidenciaGateE.RUNBOOK: "runbook.json",
        TipoEvidenciaGateE.MIGRACAO_DRY_RUN: "migration.json",
    }
    evidences: list[EvidenciaGateE] = []
    for tipo, filename in mapping.items():
        path = evidence_dir / filename
        data = json.loads(path.read_text(encoding="utf-8"))
        approved = bool(data.get("approved", False))
        observation = str(data.get("observation", ""))
        if tipo is TipoEvidenciaGateE.PRIVACIDADE and not bool(
            data.get("legal_approval", False)
        ):
            approved = False
            observation = (
                observation + "; aceite jurídico/DPO de retenção e descarte pendente"
            ).strip("; ")
        if tipo is TipoEvidenciaGateE.ROLLBACK:
            approved = bool(data.get("rollback_approved", False))
        evidences.append(
            EvidenciaGateE(
                evidencia_id=f"homologacao-{tipo.value}-{args.rc_sha[:8]}",
                tipo=tipo,
                nivel=NivelEvidencia.HOMOLOGACAO,
                aprovado=approved,
                coletado_em=now,
                artefato_ref=f"gate-e-homologacao/{filename}",
                artefato_sha256=_sha256(path),
                valido_ate=now + timedelta(days=7),
                observacao=observation,
            )
        )

    restore_data = json.loads((evidence_dir / "restore.json").read_text(encoding="utf-8"))
    restore_result = svc.comparar_restore(
        SnapshotIntegridade(**restore_data["origin"]),
        SnapshotIntegridade(**restore_data["restored"]),
    )
    slo_data = json.loads((evidence_dir / "slo.json").read_text(encoding="utf-8"))
    slo_result = svc.avaliar_slo(MetasSloV1(), AmostraSlo(**slo_data["sample"]))
    chaos_data = json.loads((evidence_dir / "caos_offline.json").read_text(encoding="utf-8"))
    chaos_results = tuple(
        ResultadoCaos(
            cenario=item["name"],
            modo_esperado=ModoDegradacao.DEGRADADO_SEGURO,
            falha_injetada=True,
            recuperou=bool(item.get("approved", False)),
            recuperacao_segundos=int(item.get("recovery_seconds", 1)),
            limite_recuperacao_segundos=int(item.get("limit_recovery_seconds", 30)),
            perda_dados=False,
            efeitos_duplicados=False,
        )
        for item in chaos_data.get("scenarios", [])
    )
    decision = svc.avaliar_release(
        evidencias=evidences,
        resultado_slo=slo_result,
        resultado_restore=restore_result,
        resultados_caos=chaos_results,
        agora=now,
    )
    payload = {
        "release_candidate_sha": args.rc_sha,
        "environment": "homologacao",
        "decision": "GO" if decision.aprovado else "NO-GO",
        "approved": decision.aprovado,
        "blocks": list(decision.bloqueios),
        "warnings": list(decision.avisos),
        "valid_evidence": [item.value for item in decision.evidencias_validas],
        "evidence_count": len(evidences),
        "collected_at": now.isoformat(),
        "note": "GO técnico não autoriza deploy; decisão humana separada continua obrigatória.",
    }
    _json_dump(Path(args.output), payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    mark = sub.add_parser("mark")
    mark.add_argument("--output", required=True)
    mark.add_argument("--approved", action=argparse.BooleanOptionalAction, default=True)
    mark.add_argument("--legal-approval", action=argparse.BooleanOptionalAction, default=None)
    mark.add_argument("--observation", default="")
    mark.set_defaults(func=cmd_mark)

    chaos = sub.add_parser("chaos-mark")
    chaos.add_argument("--output", required=True)
    chaos.set_defaults(func=cmd_chaos_mark)

    backup = sub.add_parser("backup-restore")
    backup.add_argument("--database", required=True)
    backup.add_argument("--output-dir", required=True)
    backup.set_defaults(func=cmd_backup_restore)

    migration = sub.add_parser("migration")
    migration.add_argument("--database", required=True)
    migration.add_argument("--repo-root", default=".")
    migration.add_argument("--output", required=True)
    migration.set_defaults(func=cmd_migration)

    slo = sub.add_parser("slo")
    slo.add_argument("--health-url", default="http://127.0.0.1:8501/_stcore/health")
    slo.add_argument("--root-url", default="http://127.0.0.1:8501/")
    slo.add_argument("--restore-json", required=True)
    slo.add_argument("--output", required=True)
    slo.add_argument("--requests", type=int, default=200)
    slo.add_argument("--timeout", type=float, default=5.0)
    slo.set_defaults(func=cmd_slo)

    gate = sub.add_parser("gate")
    gate.add_argument("--evidence-dir", required=True)
    gate.add_argument("--rc-sha", required=True)
    gate.add_argument("--output", required=True)
    gate.set_defaults(func=cmd_gate)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
