"""Manifest determinístico para detectar deriva em migrations registradas."""

from __future__ import annotations

import hashlib
import inspect
import json
import textwrap
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

MANIFEST_PATH = Path(__file__).with_name("manifest_v1.json")
ALGORITHM = "sha256:migration-callable-source-v1"


class MigrationLike(Protocol):
    @property
    def version(self) -> str: ...

    @property
    def apply(self) -> Callable[..., None]: ...

    @property
    def revert(self) -> Callable[..., None] | None: ...


class MigrationManifestError(RuntimeError):
    """O registry oficial divergiu do baseline histórico aprovado."""


@dataclass(frozen=True)
class MigrationFingerprint:
    version: str
    sha256: str


def _normalized_source(function: Callable[..., None] | None) -> str | None:
    if function is None:
        return None

    source = inspect.getsource(function).replace("\r\n", "\n").replace("\r", "\n")
    dedented = textwrap.dedent(source)
    lines = [line.rstrip() for line in dedented.splitlines()]
    return "\n".join(lines).strip() + "\n"


def migration_fingerprint(migration: MigrationLike) -> MigrationFingerprint:
    payload = {
        "version": migration.version,
        "apply": {
            "module": migration.apply.__module__,
            "qualname": migration.apply.__qualname__,
            "source": _normalized_source(migration.apply),
        },
        "revert": (
            None
            if migration.revert is None
            else {
                "module": migration.revert.__module__,
                "qualname": migration.revert.__qualname__,
                "source": _normalized_source(migration.revert),
            }
        ),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return MigrationFingerprint(
        version=migration.version,
        sha256=hashlib.sha256(encoded).hexdigest(),
    )


def current_fingerprints(
    migrations: Iterable[MigrationLike],
) -> tuple[MigrationFingerprint, ...]:
    return tuple(migration_fingerprint(migration) for migration in migrations)


def load_manifest(path: Path = MANIFEST_PATH) -> tuple[MigrationFingerprint, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))

    if payload.get("algorithm") != ALGORITHM:
        raise MigrationManifestError("algoritmo do manifest de migrations divergente")

    entries = payload.get("migrations")
    if not isinstance(entries, list):
        raise MigrationManifestError("manifest de migrations invalido")

    return tuple(
        MigrationFingerprint(
            version=str(entry["version"]),
            sha256=str(entry["sha256"]),
        )
        for entry in entries
    )


def assert_migration_manifest(
    migrations: Iterable[MigrationLike],
    *,
    path: Path = MANIFEST_PATH,
) -> None:
    expected = load_manifest(path)
    current = current_fingerprints(migrations)

    expected_versions = tuple(item.version for item in expected)
    current_versions = tuple(item.version for item in current)

    if current_versions != expected_versions:
        raise MigrationManifestError(
            "ordem ou conjunto de migrations diverge do manifest aprovado"
        )

    changed = [
        actual.version
        for baseline, actual in zip(expected, current, strict=True)
        if baseline.sha256 != actual.sha256
    ]

    if changed:
        raise MigrationManifestError(
            "migration historica alterada sem atualizar o baseline: "
            + ", ".join(changed)
        )
