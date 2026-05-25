"""Phase-4 S4-01 — ``codegenie embeddings bootstrap`` subcommand.

This module is the **only** place in the codebase authorized to trigger a
fastembed weights download (ADR-0007 §Decision). The runtime path
(:class:`codegenie.rag.embedder.FastembedEmbedder`) refuses to start on
drift; this CLI is the operator-initiated workflow that lays down the
``.codegenie/rag/embeddings_model.lock`` file plus the on-disk weights
cache.

Three exit paths the body distinguishes (AC-6):

1. **First write / upgrade** — lock absent OR ``--model-name`` differs
   from the on-disk lock's ``model_name``. Download (idempotent — fastembed
   no-ops on already-cached weights), compute the directory digest,
   write/overwrite the lock, exit 0. An upgrade additionally logs a
   ``embeddings.bootstrap.model_upgraded`` warning that ``codegenie rag
   rebuild`` must follow (so the corpus gets re-embedded into the new
   vector space).

2. **Idempotent re-run, same digest** — lock present, ``--model-name``
   matches, recomputed digest matches the lock's ``sha256``. Lock file
   is **NOT** rewritten (mtime-stable, byte-stable). Log
   ``embeddings.bootstrap.lock_current``. Exit 0.

3. **Same-model digest drift** — lock present, ``--model-name`` matches,
   digest differs. This is corruption / tampering, NOT an upgrade.
   Exit 1 with a diagnostic naming both digests; the lock stays
   untouched so an operator can investigate.

The Click registration lives in :mod:`codegenie.cli`. That module
defer-imports this one via :func:`importlib.import_module` so the
top-level ``cli.py`` stays free of ``fastembed`` (the path-scoped fence
+ cold-start contract).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Final

import fastembed
import yaml

from codegenie.rag.embedder import (
    _DEFAULT_LOCK_PATH,
    _DEFAULT_MODEL_NAME,
    FastembedEmbedder,
    _compute_dir_digest,
    _read_lock,
    _weights_present,
)
from codegenie.types.identifiers import ModelId

_EXIT_OK: Final[int] = 0
_EXIT_DRIFT: Final[int] = 1


def _seam_write_lock(lock_path: Path, *, model_name: ModelId, sha256: str) -> None:
    """Write the lock file. Module-scope seam so the idempotence test can
    patch it and assert it is **not** called on the no-op path.

    YAML keys are sorted so the on-disk form is canonical; a trailing
    newline keeps text-editor diffs clean.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        yaml.safe_dump(
            {"model_name": str(model_name), "sha256": sha256},
            sort_keys=True,
        )
    )


def bootstrap(
    *,
    model_name: ModelId = _DEFAULT_MODEL_NAME,
    lock_path: Path | None = None,
    cache_dir: Path | None = None,
) -> int:
    """Bootstrap workflow body. Returns the exit code (the Click adapter
    in ``codegenie.cli`` maps it via ``sys.exit``).
    """
    structlog_mod = importlib.import_module("structlog")
    log = structlog_mod.get_logger(__name__)

    resolved_lock = lock_path if lock_path is not None else _DEFAULT_LOCK_PATH
    resolved_cache = FastembedEmbedder._resolve_cache_dir(cache_dir)
    resolved_cache.mkdir(parents=True, exist_ok=True)

    existing_lock = _read_lock(resolved_lock)
    is_upgrade = existing_lock is not None and existing_lock.model_name != model_name

    # Trigger fastembed download (no-op on already-cached weights).
    # This is the ONE authorized weight-download site in the codebase
    # (ADR-0007 §Decision). Direct import + direct call — admitted
    # under src/codegenie/rag/ by ADR-0003's path-scoped fence.
    fastembed.TextEmbedding(model_name, cache_dir=str(resolved_cache))

    if not _weights_present(resolved_cache):
        # fastembed silently returned without downloading and the cache
        # is still empty — surface this loudly rather than writing a
        # zero-file digest into the lock.
        log.error(
            "embeddings.bootstrap.weights_missing",
            cache_dir=str(resolved_cache),
            model_name=str(model_name),
        )
        return _EXIT_DRIFT

    computed = _compute_dir_digest(resolved_cache)

    if existing_lock is None:
        _seam_write_lock(resolved_lock, model_name=model_name, sha256=computed)
        log.info(
            "embeddings.bootstrap.lock_written",
            lock_path=str(resolved_lock),
            sha256=computed,
            model_name=str(model_name),
        )
        return _EXIT_OK

    if is_upgrade:
        _seam_write_lock(resolved_lock, model_name=model_name, sha256=computed)
        log.warning(
            "embeddings.bootstrap.model_upgraded",
            from_model=str(existing_lock.model_name),
            to_model=str(model_name),
            new_sha256=computed,
            followup="run `codegenie rag rebuild` to re-embed the corpus",
        )
        return _EXIT_OK

    # Same-model re-run: lock_current OR drift.
    if computed == existing_lock.sha256:
        log.info(
            "embeddings.bootstrap.lock_current",
            lock_path=str(resolved_lock),
            sha256=computed,
        )
        return _EXIT_OK

    # Same model, different digest: drift / tampering / corruption.
    log.error(
        "embeddings.bootstrap.same_model_drift",
        lock_path=str(resolved_lock),
        expected_sha256=existing_lock.sha256,
        found_sha256=computed,
        remediation=(
            "investigate cache tampering before overwriting the lock; "
            "the bootstrap CLI did NOT rewrite the lock"
        ),
    )
    return _EXIT_DRIFT


def _cli_entrypoint(*, model_name: str, cache_dir: str | None, lock_path: str | None) -> None:
    """Click-side adapter. Maps the string-typed CLI args to typed
    domain values and calls :func:`bootstrap`, then ``sys.exit``s on the
    returned code."""
    code = bootstrap(
        model_name=ModelId(model_name),
        lock_path=Path(lock_path) if lock_path else None,
        cache_dir=Path(cache_dir) if cache_dir else None,
    )
    sys.exit(code)


__all__ = ("_cli_entrypoint", "_seam_write_lock", "bootstrap")
