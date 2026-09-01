"""Gate CI append-only para o histórico de migrations."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from migrations.history_guard import assert_frozen_history, load_history_baseline


def _git_show_json(ref: str, path: str) -> dict[str, Any] | None:
    completed = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    return json.loads(completed.stdout)


def _assert_base_is_prefix(
    previous: dict[str, Any],
    current: dict[str, Any],
) -> None:
    old_entries = tuple(
        (str(item["version"]), str(item["sha256"]))
        for item in previous.get("manifest_entries", [])
    )
    new_entries = tuple(
        (str(item["version"]), str(item["sha256"]))
        for item in current.get("manifest_entries", [])
    )
    if new_entries[: len(old_entries)] != old_entries:
        raise RuntimeError(
            "baseline historico existente foi alterado/removido/reordenado"
        )

    old_modules = {
        str(item["version"]): (str(item["path"]), str(item["git_blob_sha"]))
        for item in previous.get("module_blobs", [])
    }
    new_modules = {
        str(item["version"]): (str(item["path"]), str(item["git_blob_sha"]))
        for item in current.get("module_blobs", [])
    }
    for version, expected in old_modules.items():
        if new_modules.get(version) != expected:
            raise RuntimeError(
                f"baseline de source historico alterado para {version}"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", default="")
    args = parser.parse_args()

    assert_frozen_history()
    base_ref = args.base_ref.strip()
    if base_ref and set(base_ref) != {"0"}:
        previous = _git_show_json(
            base_ref,
            "migrations/history_baseline_v1.json",
        )
        if previous is not None:
            _assert_base_is_prefix(previous, load_history_baseline())

    print("SD-1D migration history gate: PASS")


if __name__ == "__main__":
    main()
