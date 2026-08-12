"""Backup/restore verificável para DB-002.

SQLite usa a API de backup consistente do próprio driver. PostgreSQL usa
pg_dump/pg_restore e envia senha somente pelo ambiente do subprocesso, evitando
exposição em argumentos/logs. Todo backup recebe manifesto com checksum SHA-256.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.engine import URL, make_url


@dataclass(frozen=True)
class BackupManifest:
    created_at: str
    backend: str
    database: str
    file_name: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class BackupRetentionPolicy:
    """Retenção local. RPO/RTO são metas de operação, não garantias do código."""

    keep_last: int = 30
    max_age_days: int = 90
    target_rpo_minutes: int = 60
    target_rto_minutes: int = 120

    def __post_init__(self) -> None:
        if self.keep_last < 1:
            raise ValueError("keep_last deve ser >= 1")
        if self.max_age_days < 1:
            raise ValueError("max_age_days deve ser >= 1")
        if self.target_rpo_minutes < 1 or self.target_rto_minutes < 1:
            raise ValueError("RPO/RTO devem ser positivos")

    @classmethod
    def from_env(cls) -> BackupRetentionPolicy:
        return cls(
            keep_last=int(os.getenv("FM_AI_BACKUP_KEEP_LAST", "30")),
            max_age_days=int(os.getenv("FM_AI_BACKUP_MAX_AGE_DAYS", "90")),
            target_rpo_minutes=int(os.getenv("FM_AI_TARGET_RPO_MINUTES", "60")),
            target_rto_minutes=int(os.getenv("FM_AI_TARGET_RTO_MINUTES", "120")),
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_manifest(path: Path, *, url: URL, backend: str) -> Path:
    manifest = BackupManifest(
        created_at=datetime.now(timezone.utc).isoformat(),
        backend=backend,
        database=str(url.database or ""),
        file_name=path.name,
        sha256=_sha256(path),
        size_bytes=path.stat().st_size,
    )
    target = path.with_suffix(path.suffix + ".manifest.json")
    target.write_text(json.dumps(asdict(manifest), indent=2), encoding="utf-8")
    return target


def _postgres_env(url: URL) -> dict[str, str]:
    env = dict(os.environ)
    if url.password:
        env["PGPASSWORD"] = url.password
    return env


def _postgres_common_args(url: URL) -> list[str]:
    args: list[str] = []
    if url.host:
        args.extend(["--host", url.host])
    if url.port:
        args.extend(["--port", str(url.port)])
    if url.username:
        args.extend(["--username", url.username])
    return args


def backup_database(database_url: str, destination: str | Path) -> BackupManifest:
    url = make_url(database_url)
    backend = url.get_backend_name()
    target = Path(destination).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    if backend == "sqlite":
        if not url.database or url.database == ":memory:":
            raise RuntimeError("backup SQLite exige arquivo persistente")
        source = Path(url.database).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(source)
        src = sqlite3.connect(str(source))
        dst = sqlite3.connect(str(target))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
    elif backend in {"postgresql", "postgres"}:
        if shutil.which("pg_dump") is None:
            raise RuntimeError("pg_dump nao encontrado no servidor")
        if not url.database:
            raise RuntimeError("DATABASE_URL PostgreSQL sem nome de banco")
        args = [
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--file",
            str(target),
            *_postgres_common_args(url),
            url.database,
        ]
        subprocess.run(args, env=_postgres_env(url), check=True, capture_output=True)
    else:
        raise RuntimeError(f"backend de backup nao suportado: {backend}")

    manifest_path = _write_manifest(target, url=url, backend=backend)
    return BackupManifest(**json.loads(manifest_path.read_text(encoding="utf-8")))


def verify_backup(backup_file: str | Path) -> BackupManifest:
    path = Path(backup_file).expanduser().resolve()
    manifest_path = path.with_suffix(path.suffix + ".manifest.json")
    if not path.exists() or not manifest_path.exists():
        raise FileNotFoundError("backup ou manifesto ausente")
    manifest = BackupManifest(**json.loads(manifest_path.read_text(encoding="utf-8")))
    if path.stat().st_size != manifest.size_bytes or _sha256(path) != manifest.sha256:
        raise RuntimeError("checksum do backup invalido")
    return manifest


def list_verified_backups(directory: str | Path) -> tuple[tuple[Path, BackupManifest], ...]:
    root = Path(directory).expanduser().resolve()
    if not root.exists():
        return ()
    valid: list[tuple[Path, BackupManifest]] = []
    for manifest_path in root.glob("*.manifest.json"):
        suffix = ".manifest.json"
        backup_path = manifest_path.with_name(manifest_path.name[: -len(suffix)])
        try:
            manifest = verify_backup(backup_path)
        except (FileNotFoundError, RuntimeError, ValueError, json.JSONDecodeError):
            continue
        valid.append((backup_path, manifest))
    return tuple(
        sorted(valid, key=lambda item: item[1].created_at, reverse=True)
    )


def prune_backups(
    directory: str | Path,
    policy: BackupRetentionPolicy,
    *,
    now: datetime | None = None,
) -> tuple[Path, ...]:
    """Remove apenas backups verificados fora da retenção; corruptos ficam para análise."""

    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None or reference.utcoffset() is None:
        raise ValueError("now deve conter timezone")
    cutoff = reference.astimezone(timezone.utc) - timedelta(days=policy.max_age_days)
    removed: list[Path] = []

    for index, (backup_path, manifest) in enumerate(list_verified_backups(directory)):
        created = datetime.fromisoformat(manifest.created_at).astimezone(timezone.utc)
        keep_by_count = index < policy.keep_last
        keep_by_age = created >= cutoff
        if keep_by_count or keep_by_age:
            continue
        manifest_path = backup_path.with_suffix(backup_path.suffix + ".manifest.json")
        backup_path.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        removed.append(backup_path)
    return tuple(removed)


def restore_database(
    database_url: str,
    backup_file: str | Path,
    *,
    confirm_database: str,
) -> None:
    url = make_url(database_url)
    backend = url.get_backend_name()
    target_database = str(url.database or "")
    if not target_database or confirm_database != target_database:
        raise RuntimeError("confirmacao do banco-alvo nao confere")

    path = Path(backup_file).expanduser().resolve()
    manifest = verify_backup(path)
    compatible_backend = "postgres" if backend == "postgresql" else backend
    if manifest.backend not in {backend, compatible_backend}:
        raise RuntimeError("backend do backup incompativel com destino")

    if backend == "sqlite":
        if target_database == ":memory:":
            raise RuntimeError("restore SQLite exige arquivo persistente")
        destination = Path(target_database).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = sqlite3.connect(str(path))
        target = sqlite3.connect(str(destination))
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        return

    if backend in {"postgresql", "postgres"}:
        if shutil.which("pg_restore") is None:
            raise RuntimeError("pg_restore nao encontrado no servidor")
        args = [
            "pg_restore",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--dbname",
            target_database,
            *_postgres_common_args(url),
            str(path),
        ]
        subprocess.run(args, env=_postgres_env(url), check=True, capture_output=True)
        return

    raise RuntimeError(f"backend de restore nao suportado: {backend}")
