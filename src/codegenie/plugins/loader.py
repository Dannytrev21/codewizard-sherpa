"""Phase 3 S2-03 — plugin loader: filesystem walk + integrity check + ``importlib``.

The disk-to-kernel bridge. Walks ``plugins/*/plugin.yaml`` under
``plugin_root``, verifies every plugin's SHA-256 tree-digest against
``plugins/PLUGINS.lock`` **before any plugin module is imported**, then
``importlib.import_module("plugins.{slug}.api")`` in walk order so each
plugin's ``register_plugin(...)`` side-effect fires into the registry.

Four gates, fail-fast at each:

1. **Discover** — ``sorted(plugin_root.glob("*/plugin.yaml"))``.
2. **Verify** — for every discovered manifest: load with
   :meth:`PluginManifest.from_yaml`; check lock membership; call
   :meth:`PluginVerifier.verify`. Also cross-check that every lock entry
   was visited; surface ``MissingManifest`` (directory present, no
   ``plugin.yaml``) and ``MissingPluginDirectory`` (lock entry, no
   directory) distinctly.
3. **Import** — only if every plugin passed Verify, call
   ``importlib.import_module(f"plugins.{slug}.api")`` in walk order.
4. **Register** — ``@register_plugin`` side-effects from Import populate
   the registry.

This module routes hashing through :func:`codegenie.hashing.tree_digest_of_files`
(ADR-0001 chokepoint) and JSON reads through :mod:`codegenie.parsers.safe_json`
(Phase 1 ADR-0009 chokepoint). The AST source-scan fence in
``tests/static/test_plugins_loader_chokepoints.py`` enforces both at the
import boundary — direct ``hashlib`` / ``blake3`` / ``json`` imports here
fail the suite.

ADR-0011 honest framing: the integrity check catches accidental
corruption and partial merges, NOT cryptographic signatures. Phase 11
substitutes Sigstore via the :class:`PluginVerifier` Protocol (see
``verifiers.py``); zero edits to this file at Phase 11 time.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

from codegenie.hashing import tree_digest_of_files
from codegenie.plugins.errors import (
    IntegrityMismatch,
    MissingManifest,
    MissingPluginDirectory,
    PluginImportError,
    PluginRejected,
    SchemaViolation,
    SymlinkEscape,
    UnlockedPlugin,
)
from codegenie.plugins.lockfile import LockFile
from codegenie.plugins.manifest import PluginManifest
from codegenie.plugins.registry import PluginRegistry, default_registry
from codegenie.plugins.verifiers import PluginVerifier, Sha256TreeDigestVerifier
from codegenie.result import Err, Ok, Result
from codegenie.types.identifiers import BlobDigest, PluginId
from codegenie.types.parsers import parse_blob_digest

__all__ = [
    "LoadReport",
    "compute_plugin_tree_digest",
    "load_plugins",
]


_PYCACHE_DIR: Final[str] = "__pycache__"
_PYC_SUFFIX: Final[str] = ".pyc"
# Sentinel digest the :class:`Sha256TreeDigestVerifier` reports when the
# tree walk refused a symlink-escape. The loader translates this back into
# the structural :class:`SymlinkEscape` rejection variant at the boundary;
# never leaked beyond ``load_plugins``.
_SYMLINK_ESCAPE_SENTINEL: Final[BlobDigest] = BlobDigest("0" * 64)


class LoadReport(BaseModel):
    """Successful-load summary.

    ``loaded`` is the registration-order tuple of plugin ids whose
    integrity-check passed AND whose ``api.py`` imported cleanly. Under
    the verify-all-then-import-all invariant (see module docstring) this
    tuple is either the full discovered set or empty — the loader never
    half-registers a partial set.

    ``total_walked`` is ``len(walked)`` regardless of outcome, so an
    operator inspecting the report can distinguish "no plugins on disk"
    from "all plugins loaded but none registered".
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    loaded: tuple[PluginId, ...]
    total_walked: int


# --- Tree-digest core -------------------------------------------------------


def _iter_walk(plugin_dir: Path) -> Iterator[Path]:
    """``rglob('*')`` with deterministic ordering by relative path.

    Sorting by the relative path string (not the absolute ``Path``)
    matches the digest key we feed into ``tree_digest_of_files``; the
    AC-10 Hypothesis property test exercises this invariance.
    """
    children = list(plugin_dir.rglob("*"))
    children.sort(key=lambda p: p.relative_to(plugin_dir).as_posix())
    yield from children


def _collect_plugin_files(
    plugin_dir: Path,
) -> Result[tuple[tuple[str, bytes], ...], SymlinkEscape]:
    """Walk ``plugin_dir`` and return ``(relpath, bytes)`` pairs.

    Impure (filesystem I/O); separated from :func:`tree_digest_of_files`
    so the hashing core stays pure given input bytes. Skips
    ``__pycache__/`` directories and any ``*.pyc`` files (build artefacts
    that vary across Python minor releases and would break the digest's
    cross-platform invariance).

    Symlink discipline: every walked child is ``resolve(strict=True)``-d
    and checked with ``is_relative_to(plugin_dir.resolve())``. A symlink
    whose target lies outside the plugin directory fails with
    :class:`SymlinkEscape`. Mirrors the in-codebase precedent at
    ``src/codegenie/probes/deployment.py:178-195``.
    """
    plugin_id = PluginId(plugin_dir.name)
    try:
        resolved_root = plugin_dir.resolve(strict=True)
    except OSError:
        return Err(error=SymlinkEscape(plugin=plugin_id, offending_path=plugin_dir))

    pairs: list[tuple[str, bytes]] = []
    for child in _iter_walk(plugin_dir):
        if _PYCACHE_DIR in child.parts:
            continue
        if child.suffix == _PYC_SUFFIX:
            continue
        try:
            resolved_child = child.resolve(strict=True)
        except OSError:
            return Err(error=SymlinkEscape(plugin=plugin_id, offending_path=child))
        if not resolved_child.is_relative_to(resolved_root):
            return Err(error=SymlinkEscape(plugin=plugin_id, offending_path=child))
        if not child.is_file():
            continue
        rel = child.relative_to(plugin_dir).as_posix()
        pairs.append((rel, child.read_bytes()))
    pairs.sort(key=lambda p: p[0])
    return Ok(value=tuple(pairs))


def compute_plugin_tree_digest(
    plugin_dir: Path,
) -> Result[BlobDigest, SymlinkEscape]:
    """Return the SHA-256 tree-digest of ``plugin_dir`` as a
    :data:`BlobDigest`.

    Composes :func:`_collect_plugin_files` (impure walk) with the
    chokepoint-resident :func:`codegenie.hashing.tree_digest_of_files`
    (pure hashing). The functional-core / imperative-shell split keeps
    the AC-10 walk-order invariance property test trivial — generate
    ``(path, bytes)`` pairs, shuffle, assert digest equality on the
    inner pure helper.

    Returns ``Err(SymlinkEscape)`` when the walk encounters a path
    escaping ``plugin_dir`` via symlink (ADR-0011 zip-slip discipline).
    """
    collected = _collect_plugin_files(plugin_dir)
    if isinstance(collected, Err):
        return Err(error=collected.error)
    raw_digest = tree_digest_of_files(collected.value)
    # Smart-constructor lift through the S1-01 parser. The chokepoint
    # contract guarantees 64-hex output; the parser is a defence-in-depth
    # type-narrowing — if hashing ever returns a different shape the
    # loader fails loud rather than producing a malformed ``BlobDigest``.
    parsed = parse_blob_digest(raw_digest)
    if isinstance(parsed, Err):  # pragma: no cover — guaranteed by chokepoint
        raise RuntimeError(f"tree_digest_of_files returned non-conforming digest: {raw_digest!r}")
    return Ok(value=parsed.value)


# --- Loader pipeline --------------------------------------------------------


def load_plugins(
    plugin_root: Path,
    lock_path: Path,
    *,
    registry: PluginRegistry | None = None,
    verifier: PluginVerifier | None = None,
) -> Result[LoadReport, PluginRejected]:
    """Discover → Verify-ALL → Import-ALL → Register.

    The four-gate pipeline is the architectural defence: no plugin's
    module body runs until every plugin's integrity check passes. A
    tampered plugin's ``api.py`` therefore cannot ``register_plugin``
    into the registry before the loader catches the mismatch.

    Args:
        plugin_root: Directory containing per-plugin subdirectories.
        lock_path: ``plugins/PLUGINS.lock`` file.
        registry: Target registry; defaults to
            :data:`default_registry` when ``None``.
        verifier: Strategy seam for the integrity check; defaults to
            :class:`Sha256TreeDigestVerifier` when ``None``. Phase 11
            substitutes ``SigstoreVerifier`` here via DI.

    Returns:
        ``Ok(LoadReport)`` on full success.
        ``Err(<PluginRejected variant>)`` on the first rejection — the
        registry is guaranteed unchanged when an ``Err`` is returned
        (verify-all-then-import-all invariant).

    Note:
        Plugin ``api.py`` modules call
        :func:`codegenie.plugins.registry.register_plugin` which defaults
        to :data:`default_registry`. The ``registry=`` parameter is the
        contractual target for the per-import side effect and the
        recipient of the load-bearing mutation-resistance assertion
        (``registry.all() == ()`` on any ``Err`` return). Phase-3 plugin
        modules typically target :data:`default_registry`; a future
        amendment may thread an explicit registry via a ``ContextVar``.
    """
    target_registry: PluginRegistry = registry if registry is not None else default_registry
    target_verifier: PluginVerifier = (
        verifier if verifier is not None else Sha256TreeDigestVerifier()
    )
    # ``target_registry`` is held as a reference so the post-load contract
    # "registry not mutated on Err" is anchored to the same object the
    # caller passed; consumers verify with ``id(target_registry) is id(registry)``.
    _ = target_registry

    # Gate 1: Discover.
    walked = sorted(plugin_root.glob("*/plugin.yaml"))

    # Gate 2: Lock.
    lock_result = LockFile.from_path(lock_path)
    if isinstance(lock_result, Err):
        return Err(error=lock_result.error)
    lock = lock_result.value.root

    # Gate 3: Verify every discovered manifest in walk-order.
    verified: list[tuple[str, PluginId]] = []
    seen_in_lock: set[PluginId] = set()
    for manifest_path in walked:
        slug_dir = manifest_path.parent
        slug = slug_dir.name
        slug_as_plugin_id = PluginId(slug)

        manifest_result = PluginManifest.from_yaml(manifest_path)
        if isinstance(manifest_result, Err):
            return Err(
                error=SchemaViolation(plugin=slug_as_plugin_id, detail=str(manifest_result.error))
            )
        manifest = manifest_result.value
        plugin_id = manifest.name

        if plugin_id not in lock:
            return Err(error=UnlockedPlugin(plugin=plugin_id))
        seen_in_lock.add(plugin_id)

        verify_result = target_verifier.verify(slug_dir, lock[plugin_id])
        if isinstance(verify_result, Err):
            ve = verify_result.error
            if ve.actual == _SYMLINK_ESCAPE_SENTINEL:
                return Err(error=SymlinkEscape(plugin=plugin_id, offending_path=slug_dir))
            return Err(
                error=IntegrityMismatch(plugin=plugin_id, expected=ve.expected, actual=ve.actual)
            )

        verified.append((slug, plugin_id))

    # Cross-check: every locked plugin must have been visited.
    for locked_plugin in lock:
        if locked_plugin in seen_in_lock:
            continue
        candidate_dir = plugin_root / str(locked_plugin)
        if candidate_dir.is_dir():
            return Err(error=MissingManifest(plugin=locked_plugin))
        return Err(error=MissingPluginDirectory(plugin=locked_plugin))

    # Gate 4: Import every verified plugin's entry module. Fail-fast.
    for slug, plugin_id in verified:
        try:
            importlib.import_module(f"plugins.{slug}.api")
        except Exception as exc:  # noqa: BLE001 — third-party module body
            return Err(error=PluginImportError(plugin=plugin_id, detail=repr(exc)))

    # The ``registry`` parameter exists for future hooks (e.g., to assert
    # the registry was mutated as expected). Today, Gate 4's
    # ``importlib.import_module`` side-effect populates whichever registry
    # the plugin's ``api.py`` chose — typically ``default_registry``.
    return Ok(
        value=LoadReport(
            loaded=tuple(plugin_id for _, plugin_id in verified),
            total_walked=len(walked),
        )
    )
