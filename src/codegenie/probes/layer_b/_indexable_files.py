"""Shared indexable-file walker (extracted in S4-06 per AC-M4).

Originally lived inside :mod:`codegenie.probes.layer_b.scip_index` (S4-03).
Lifted to its own module so :class:`SemanticIndexMetaProbe` (S4-06) can
share the *exact same* walker + exclude policy without copy-paste — a
divergence between the two would cause B2's ``Stale(CoverageGap)`` to
fire on counts that mean different things on each probe.

The exclude set is the canonical SCIP indexable-file exclude set:
``frozenset({"node_modules", "dist", "build", ".git"})``. ``"out"`` is
*not* in the exclude set — it lives in ``GeneratedCodeProbe``'s separate
``_BUILD_OUTPUT_DIRS`` constant, which addresses a different question
(distroless-image build-stage detection, not SCIP indexable-file
counting). The two sets overlap on ``{"dist", "build"}`` and that is
the intended seam.

Suffix set is restricted to ``{".ts", ".tsx"}`` — SCIP's program scope
per ``localv2.md §5.2 B1``. ``.js``/``.jsx`` belong to
S4-04's ``TreeSitterImportGraphProbe``.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S4-06-layer-b-marker-probes.md``
  AC-M4 (extraction discipline).
- ``docs/phases/02-context-gather-layers-b-g/stories/S4-03-scip-index-probe.md``
  AC-9 (original consistency invariant).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Final

from codegenie.hashing import content_hash, identity_hash

__all__ = [
    "_EXCLUDE_DIRS",
    "_INDEXABLE_SUFFIXES",
    "_compute_indexable_merkle",
    "_count_indexable_files",
    "_read_exclude_file",
    "_walk_indexable_files",
]


_INDEXABLE_SUFFIXES: Final[frozenset[str]] = frozenset({".ts", ".tsx"})
_EXCLUDE_DIRS: Final[frozenset[str]] = frozenset({"node_modules", "dist", "build", ".git"})


def _read_exclude_file(root: Path) -> frozenset[str]:
    """Read ``.codegenie/exclude.txt`` if present; return relative-path
    prefixes to exclude. Tolerant: returns an empty frozenset if the file
    is missing or unreadable."""
    exclude_path = root / ".codegenie" / "exclude.txt"
    if not exclude_path.is_file():
        return frozenset()
    try:
        lines = exclude_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return frozenset()
    return frozenset(line.strip() for line in lines if line.strip() and not line.startswith("#"))


def _walk_indexable_files(root: Path) -> Iterator[Path]:
    """Yield every ``.ts``/``.tsx`` file under *root*, excluding the canonical
    exclude dirs and any path listed in ``.codegenie/exclude.txt``.

    Yields paths in sorted order so Merkle and golden-file consumers see a
    deterministic walk.
    """
    user_excludes = _read_exclude_file(root)
    matches: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in _INDEXABLE_SUFFIXES:
            continue
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if any(part in _EXCLUDE_DIRS for part in rel.parts):
            continue
        rel_str = rel.as_posix()
        if any(rel_str == ex or rel_str.startswith(f"{ex}/") for ex in user_excludes):
            continue
        matches.append(path)
    matches.sort(key=lambda p: p.as_posix())
    yield from matches


def _count_indexable_files(root: Path) -> int:
    """Count ``.ts``/``.tsx`` files under *root* via the shared walker."""
    return sum(1 for _ in _walk_indexable_files(root))


def _compute_indexable_merkle(root: Path) -> str:
    """BLAKE3 over the sorted ``(rel-path, content-hash)`` pairs of every
    indexable file under *root*. Structural invariant + future-proofing.
    """
    payload: list[str] = []
    for path in _walk_indexable_files(root):
        rel = path.relative_to(root).as_posix()
        payload.append(f"{rel}\x1f{content_hash(path)}")
    return identity_hash(*payload)
