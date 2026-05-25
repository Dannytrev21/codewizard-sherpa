"""Phase-4 S4-01 — ``codegenie embeddings bootstrap`` subcommand
**plus** S4-07 — ``codegenie rag rebuild [--reembed]`` operational-recovery
subcommand.

This module is the **only** place in the codebase authorized to trigger a
fastembed weights download (ADR-0007 §Decision). The runtime path
(:class:`codegenie.rag.embedder.FastembedEmbedder`) refuses to start on
drift; this CLI is the operator-initiated workflow that lays down the
``.codegenie/rag/embeddings_model.lock`` file plus the on-disk weights
cache.

S4-07 grafts the ``rag rebuild`` subcommand alongside ``embeddings
bootstrap`` — both ride the same path-scoped fence + cold-start contract.
The rebuild CLI is the **second sanctioned mint call-site** for
``_phase4_local_capability_mint`` (ADR-0016 §"operational-recovery"); the
``ignore_imports`` row in ``pyproject.toml`` plus the allowlist in
``tests/fence/test_phase4_capability_mint_scope.py`` keep the boundary
honest.

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

import asyncio
import importlib
import shutil
import sys
from pathlib import Path
from typing import Final

import fastembed
import yaml

from codegenie.rag._capability_mint import _phase4_local_capability_mint
from codegenie.rag.embedder import (
    _DEFAULT_LOCK_PATH,
    _DEFAULT_MODEL_NAME,
    FastembedEmbedder,
    _compute_dir_digest,
    _read_lock,
    _weights_present,
)
from codegenie.rag.embedding_cache import CachedEmbedder
from codegenie.rag.errors import StoreCorrupted
from codegenie.rag.models import SolvedExample
from codegenie.rag.store import (
    ChromaPersistentStore,
    _atomic_write_text,
    _canonical_yaml_dump,
    _parse_manifest_or_raise,
    _reset_process_wide_client_cache,
)
from codegenie.types.identifiers import ModelId

_EXIT_OK: Final[int] = 0
_EXIT_DRIFT: Final[int] = 1

# ---------------------------------------------------------------------------
# S4-07 — rag rebuild exit codes (story AC-1)
# ---------------------------------------------------------------------------

_REBUILD_EXIT_OK: Final[int] = 0
_REBUILD_EXIT_ERROR: Final[int] = 1
_REBUILD_EXIT_NO_MANIFEST: Final[int] = 2

_DEFAULT_RAG_ROOT: Final[Path] = Path(".codegenie/rag")
_CHROMA_SUBDIR: Final[str] = "chroma"
_RECORDS_SUBDIR: Final[str] = "records"
_MANIFEST_FILENAME: Final[str] = "manifest.yaml"


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


# ---------------------------------------------------------------------------
# S4-07 — codegenie rag rebuild [--reembed]
# ---------------------------------------------------------------------------


def _query_text_for(example: SolvedExample) -> str:
    """Deterministic query-text projection used by the ``--reembed`` path.

    :class:`SolvedExample` does **not** persist the original harvester
    ``query_text`` — by ADR-0016 design (workflow context is intentionally
    excluded from the identity set; see ``codegenie.rag.ingest.``
    ``_canonical_identity_bytes``). The rebuild's job is operational
    recovery, not perfect parity with the harvester. The projection is
    over stable record fields so:

    1. Same record → same text → same embedding (idempotent — AC-6 pins
       the "second ``--reembed`` is a no-op" property).
    2. Cross-machine YAML moves reproduce the same vectors (Out-of-scope
       §"Cross-machine rebuild migration": works by construction).
    """
    return (
        f"cve_id={example.cve_id}\n"
        f"language={example.language}\n"
        f"build_system={example.build_system}\n"
        f"plan_kind={example.plan_kind}\n"
    )


def _resolve_chroma_dir_or_raise(root: Path) -> Path:
    """AC-12 destructive-op guard for ``shutil.rmtree``.

    Refuses to return a chroma path that:

    1. Is a symlink (could point outside ``root``).
    2. Resolves outside ``root.resolve()``.

    Both conditions raise :class:`ValueError` with the literal substring
    ``"refusing to remove"`` so the CLI body can surface it on stderr and
    exit 1. The function does **not** itself call ``rmtree`` — separation
    of concerns keeps the unit test cheap.
    """
    chroma = root / _CHROMA_SUBDIR
    if chroma.is_symlink():
        raise ValueError(
            f"refusing to remove symlinked chroma directory: {chroma} "
            f"(symlink target may be outside --root)"
        )
    if chroma.exists():
        resolved_chroma = chroma.resolve()
        resolved_root = root.resolve()
        if not resolved_chroma.is_relative_to(resolved_root):
            raise ValueError(
                f"refusing to remove chroma path outside --root: "
                f"resolved={resolved_chroma} root={resolved_root}"
            )
    return chroma


def _dry_run_parse(root: Path) -> tuple[list[SolvedExample], list[str]]:
    """AC-8 transactional dry-run pass.

    Reads ``manifest.yaml``, iterates ``manifest.records`` in order, and
    parses every ``<root>/records/<id>.yaml`` into a :class:`SolvedExample`.
    Returns the parsed records alongside the ordered id list (the latter
    matches ``manifest.records`` verbatim — fed downstream so the rebuild
    preserves insertion order even if the iteration order of ``parsed``
    diverges from a future ``OrderedDict`` change).

    Raises :class:`StoreCorrupted` when ``manifest.yaml`` is malformed.
    Raises :class:`FileNotFoundError` when a record yaml is absent — the
    caller translates to exit 1 with the path verbatim.
    Raises :class:`Exception` from Pydantic on parse failure — the
    caller catches and translates.
    """
    manifest = _parse_manifest_or_raise(root / _MANIFEST_FILENAME)
    parsed: list[SolvedExample] = []
    record_ids = [str(rid) for rid in manifest.records]
    for rid in manifest.records:
        yaml_path = root / _RECORDS_SUBDIR / f"{rid}.yaml"
        parsed.append(SolvedExample.from_yaml(yaml_path))
    return parsed, record_ids


def _seam_build_reembed_embedder(root: Path) -> object:
    """Module-level seam for the ``--reembed`` embedder construction.

    Tests patch ``codegenie.rag.cli._seam_build_reembed_embedder`` to
    inject a deterministic fake (typically: an :class:`Embedder` that
    returns a fixed vector and a controlled ``model_digest`` so AC-6's
    "chain head changed; embedding_model updated" assertions are
    crisp). Mirrors :func:`_seam_write_lock`'s seam pattern.

    Return type is ``object`` to keep the boundary loose: any
    :class:`~codegenie.rag.embedder.Embedder`-shaped object works (the
    Protocol is :func:`typing.runtime_checkable`).
    """
    return CachedEmbedder(
        inner=FastembedEmbedder(),
        db_path=root / "embeddings.cache.sqlite",
    )


async def _rebuild_async(
    *,
    root: Path,
    reembed: bool,
    parsed: list[SolvedExample],
) -> None:
    """Inner async body — separate from :func:`rebuild` so the sync entry
    point owns the ``asyncio.run`` boundary (Notes §2).

    Steps:

    1. If ``--reembed``: build embedder (cached); re-embed each record's
       ``query_text`` projection; ``model_copy`` with the new
       ``embedding_model`` + ``embedding_vector``; rewrite the canonical
       YAML *before* chromadb re-insertion (so ``store.add`` rolls the
       NEW canonical bytes into ``manifest.chain_head``).
    2. Construct a fresh :class:`ChromaPersistentStore` (the previous
       ``chroma/`` was deleted by the caller).
    3. For each record (in manifest order): mint a capability;
       ``await store.add(example, capability)``. ``add`` writes the
       canonical YAML, adds to chromadb, and re-rolls the manifest —
       which converges to the post-rebuild chain head naturally (AC-2).
    4. ``store.close()`` so the chromadb client releases its handle
       before the test re-opens.
    """
    log = importlib.import_module("structlog").get_logger(__name__)

    if reembed:
        embedder: object = _seam_build_reembed_embedder(root)
        new_model_digest = ModelId(str(embedder.model_digest()))  # type: ignore[attr-defined]
        for idx, example in enumerate(parsed):
            new_vector = embedder.embed(_query_text_for(example))  # type: ignore[attr-defined]
            updated = example.model_copy(
                update={
                    "embedding_model": new_model_digest,
                    "embedding_vector": new_vector,
                }
            )
            parsed[idx] = updated
            # Pre-emptively rewrite the canonical YAML so a mid-loop
            # failure leaves the YAML idempotently re-runnable (Notes §3).
            (root / _RECORDS_SUBDIR).mkdir(parents=True, exist_ok=True)
            _atomic_write_text(
                root / _RECORDS_SUBDIR / f"{updated.id}.yaml",
                _canonical_yaml_dump(updated),
            )

    store = ChromaPersistentStore(root_dir=root)
    try:
        for example in parsed:
            capability = _phase4_local_capability_mint(
                workflow_id=example.provenance.workflow_id,
                chain_head=example.provenance.event_chain_head,
            )
            await store.add(example, capability)
        log.info(
            "rebuild.completed",
            root=str(root),
            count=len(parsed),
            digest=str(store.digest()),
            reembed=reembed,
        )
    finally:
        store.close()


def rebuild(
    *,
    root: Path = _DEFAULT_RAG_ROOT,
    reembed: bool = False,
) -> int:
    """``codegenie rag rebuild`` body — returns the exit code.

    See module docstring + S4-07 acceptance criteria. Exit codes:

    - ``0`` — rebuild completed; ``store.digest() == manifest.chain_head``.
    - ``1`` — YAML parse error, chromadb write failure, or ``rmtree``
      refused (path escape / symlink).
    - ``2`` — ``manifest.yaml`` missing under ``--root``; nothing to
      rebuild from.
    """
    log = importlib.import_module("structlog").get_logger(__name__)

    manifest_path = root / _MANIFEST_FILENAME
    if not manifest_path.is_file():
        sys.stderr.write(f"no manifest.yaml found at {root}; see docs/operations/rag.md\n")
        return _REBUILD_EXIT_NO_MANIFEST

    # Phase 1 — dry-run parse. Any failure aborts BEFORE chromadb is touched
    # (AC-8 transactional contract; Notes §3 default-mode atomicity).
    try:
        parsed, _record_ids = _dry_run_parse(root)
    except FileNotFoundError as exc:
        sys.stderr.write(f"yaml parse error: missing record file: {exc.filename}\n")
        return _REBUILD_EXIT_ERROR
    except StoreCorrupted as exc:
        sys.stderr.write(f"manifest.yaml is corrupt: {exc}\n")
        return _REBUILD_EXIT_ERROR
    except Exception as exc:  # noqa: BLE001 — Pydantic / yaml errors translate here
        offender = _find_offending_record(root, exc)
        sys.stderr.write(f"yaml parse error in {offender}: {exc}\n")
        return _REBUILD_EXIT_ERROR

    # Phase 2 — rmtree guard + wipe ``chroma/``. Even a corrupted sqlite is
    # replaced wholesale (AC-4 corruption-recovery contract).
    try:
        chroma_dir = _resolve_chroma_dir_or_raise(root)
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        return _REBUILD_EXIT_ERROR
    if chroma_dir.exists():
        shutil.rmtree(chroma_dir, ignore_errors=False)
        # chromadb's ``PersistentClient`` caches a process-wide
        # ``System`` keyed by path; after ``rmtree`` the stale system
        # still holds handles to the now-deleted sqlite. Without this
        # reset a subsequent ``ChromaPersistentStore(root_dir=root)`` re-
        # opens the dead handle and the first ``collection.add`` raises
        # ``OperationalError: no such table: collections``.
        _reset_process_wide_client_cache()
        log.info("rebuild.chroma_removed", path=str(chroma_dir))

    # The records YAML files stay (canonical source of truth) but the
    # manifest must be deleted: ``ChromaPersistentStore.__init__`` calls
    # ``_load_existing_record_ids`` which reads the manifest into
    # ``_record_ids`` — without wiping, each subsequent ``store.add``
    # would APPEND to the existing list and the rebuilt manifest would
    # carry every record twice (records section + chain head both bloat).
    manifest_file = root / _MANIFEST_FILENAME
    if manifest_file.exists():
        manifest_file.unlink()

    # Phase 3+4 — re-insert in order; assert digest reproduction.
    try:
        asyncio.run(_rebuild_async(root=root, reembed=reembed, parsed=parsed))
    except Exception as exc:  # noqa: BLE001 — chromadb-side failures map to exit 1
        log.error("rebuild.digest_mismatch", error_class=type(exc).__name__, error=str(exc))
        sys.stderr.write(f"rebuild failed: {type(exc).__name__}: {exc}\n")
        return _REBUILD_EXIT_ERROR

    return _REBUILD_EXIT_OK


def _find_offending_record(root: Path, exc: BaseException) -> str:
    """Best-effort: probe each record in turn to surface the bad path.

    The Pydantic/yaml exception type carries no path context, so on a
    parse failure the caller re-walks the records dir to pin which file
    is unparseable. Returns the first failing path (string form) or the
    repr of ``exc`` if every record now parses (transient I/O race).
    """
    try:
        manifest = _parse_manifest_or_raise(root / _MANIFEST_FILENAME)
    except Exception:  # noqa: BLE001
        return repr(exc)
    for rid in manifest.records:
        yaml_path = root / _RECORDS_SUBDIR / f"{rid}.yaml"
        try:
            SolvedExample.from_yaml(yaml_path)
        except Exception:  # noqa: BLE001
            return str(yaml_path)
    return repr(exc)


def _rebuild_cli_entrypoint(*, root: str, reembed: bool) -> None:
    """Click adapter — maps CLI string args to typed values and ``sys.exit``s
    on the returned code."""
    code = rebuild(root=Path(root), reembed=reembed)
    sys.exit(code)


__all__ = (
    "_cli_entrypoint",
    "_query_text_for",
    "_rebuild_cli_entrypoint",
    "_resolve_chroma_dir_or_raise",
    "_seam_build_reembed_embedder",
    "_seam_write_lock",
    "bootstrap",
    "rebuild",
)
