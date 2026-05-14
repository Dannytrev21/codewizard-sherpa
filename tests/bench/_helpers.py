"""Shared bench helpers (S5-01).

The atomic merge writer is the single source of truth for ``bench-results.json``.
Each bench test calls :func:`merge_bench_result` with its own top-level key so
concurrent or sequential runs never truncate each other's keys. The path is
resolved from ``$GITHUB_WORKSPACE`` when set (CI) and falls back to a
test-supplied directory locally.

The merge sequence is load-bearing for the "bench harness not silently
no-op" invariant: load existing JSON (best-effort), overlay the new key,
serialize, write to a unique per-writer ``.tmp`` slot, ``fsync``,
``os.replace``. Test-only — NOT under ``src/``.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any

__all__ = ["bench_results_path", "merge_bench_result"]


def bench_results_path(fallback_dir: Path) -> Path:
    """Resolve the ``bench-results.json`` path.

    In CI, ``$GITHUB_WORKSPACE`` is the workflow root that
    ``actions/upload-artifact`` picks up. Locally, the test passes
    ``tmp_path`` so the artifact never escapes the test sandbox.
    """
    ws = os.environ.get("GITHUB_WORKSPACE")
    base = Path(ws) if ws else fallback_dir
    return base / "bench-results.json"


def merge_bench_result(path: Path, key: str, payload: dict[str, Any]) -> None:
    """Atomically merge ``{key: payload}`` into the JSON at ``path``.

    Steps: load-or-init existing dict → overlay ``key`` → write to a
    per-writer ``.tmp`` slot (pid + random suffix) → ``fsync`` → ``replace``.
    Per-writer tmp filenames avoid a same-name race when two bench tests
    happen to publish in parallel under ``pytest-xdist`` or future
    concurrent harnesses.
    """
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            raw = path.read_text(encoding="utf-8")
            parsed = json.loads(raw) if raw else {}
            if isinstance(parsed, dict):
                existing = parsed
        except (OSError, ValueError):
            existing = {}

    existing[key] = payload
    body = json.dumps(existing, sort_keys=True, indent=2).encode("utf-8")

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.{secrets.token_hex(4)}.tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, body)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp), str(path))
