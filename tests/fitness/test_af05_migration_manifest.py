from __future__ import annotations

from dataclasses import replace

import pytest

from migrations.manifest import (
    ALGORITHM,
    MANIFEST_PATH,
    MigrationManifestError,
    assert_migration_manifest,
    load_manifest,
)
from migrations.runner import DEFAULT_MIGRATIONS


def test_af05_manifest_cobre_registry_oficial_na_ordem_exata() -> None:
    manifest = load_manifest()

    assert MANIFEST_PATH.name == "manifest_v1.json"
    assert ALGORITHM == "sha256:migration-callable-source-v1"
    assert tuple(item.version for item in manifest) == tuple(
        migration.version for migration in DEFAULT_MIGRATIONS
    )


def test_af05_fingerprints_do_baseline_atual_sao_validos() -> None:
    assert_migration_manifest(DEFAULT_MIGRATIONS)


def test_af05_alteracao_acidental_de_migration_falha_fechado() -> None:
    def changed_migration(_connection) -> None:
        return None

    changed = (
        replace(DEFAULT_MIGRATIONS[0], apply=changed_migration),
        *DEFAULT_MIGRATIONS[1:],
    )

    with pytest.raises(
        MigrationManifestError,
        match="migration historica alterada",
    ):
        assert_migration_manifest(changed)
