"""Verify the vendored Fiscal V1 snapshot against its frozen Git blob manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "web-parity" / "WP031_FISCAL_V1_VENDOR_BASELINE.json"
EXPECTED_COMMIT = "b336def47ad4f5188307102203f4e04b98406014"


def git_blob_sha(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content).hexdigest()  # noqa: S324 - Git object identity


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest["source_commit"] != EXPECTED_COMMIT:
        raise SystemExit("Fiscal V1 source commit changed")
    files = manifest["files"]
    if len(files) != 45:
        raise SystemExit(f"unexpected Fiscal V1 file count: {len(files)}")
    for relative, expected_sha in files.items():
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"vendored fiscal file missing: {relative}")
        actual_sha = git_blob_sha(path.read_bytes())
        if actual_sha != expected_sha:
            raise SystemExit(
                f"vendored fiscal drift: {relative}: "
                f"expected={expected_sha} actual={actual_sha}"
            )
    print(f"Fiscal V1 vendored baseline: PASS ({len(files)} files)")
    print(f"Source commit: {EXPECTED_COMMIT}")


if __name__ == "__main__":
    main()
