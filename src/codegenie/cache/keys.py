"""Cache key derivation — per-probe vs envelope schema versioning (ADR-0003).

The cache key is ``identity_hash(probe.name, probe.version,
per_probe_schema_version(probe), content_hash_of_inputs(declared_inputs_for(...)))``.

The load-bearing distinction this module encodes:

- :func:`envelope_schema_version` returns the envelope's ``$id`` version. The
  envelope is metadata (ADR-0013) — bumping it must NOT invalidate any
  probe's cache. The envelope version is **deliberately not** in the key.
- :func:`per_probe_schema_version` returns the probe's own sub-schema ``$id``
  if present, falling back to :func:`envelope_schema_version` for probes that
  haven't shipped a sub-schema yet. Bumping one probe's sub-schema
  invalidates only that probe's cache entries — surgical invalidation,
  Phase 14 continuous-gather compatible (ADR-0003 §Decision).

The schema-directory resolver lives in module-level :data:`_SCHEMA_DIR` so
tests can monkeypatch it to a tmp_path containing synthetic sub-schemas
without touching the installed package.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from codegenie.hashing import content_hash_of_inputs, identity_hash

if TYPE_CHECKING:
    from codegenie.probes.base import RepoSnapshot, Task

__all__ = [
    "declared_inputs_for",
    "envelope_schema_version",
    "key_for",
    "per_probe_schema_version",
]


class _ProbeLike(Protocol):
    """Structural shape ``cache/keys`` reads from a probe class.

    ``codegenie.probes.base.Probe`` is frozen (ADR-0007 + S2-02 snapshot) and
    does not declare ``version`` as a class attribute — registry.py's
    docstring calls ``version`` a *convention*, not part of the ABC. This
    Protocol bridges that convention to ``--strict`` typing without amending
    the ABC.
    """

    name: str
    version: str
    declared_inputs: list[str]


# Resolves to ``src/codegenie/schema``. Tests monkeypatch this attribute to
# point at a temp directory whose layout mirrors the installed shape
# (``repo_context.schema.json`` + ``probes/<name>.schema.json``).
_SCHEMA_DIR: Path = Path(__file__).resolve().parents[1] / "schema"


def _envelope_schema_path() -> Path:
    return _SCHEMA_DIR / "repo_context.schema.json"


def _probe_schema_path(probe_name: str) -> Path:
    return _SCHEMA_DIR / "probes" / f"{probe_name}.schema.json"


def envelope_schema_version() -> str:
    """Return the envelope schema's ``$id`` (used only as the fallback for
    probes with no sub-schema; **never** part of the cache key tuple)."""
    data = json.loads(_envelope_schema_path().read_text())
    return str(data["$id"])


def per_probe_schema_version(probe: _ProbeLike) -> str:
    """Return the probe's sub-schema ``$id``, falling back to envelope on miss.

    ADR-0003 §Decision: only this string lands in the cache key. A bump to
    ``language_detection.schema.json`` invalidates only ``LanguageDetectionProbe``;
    it does not touch any other probe.
    """
    try:
        data = json.loads(_probe_schema_path(probe.name).read_text())
    except FileNotFoundError:
        return envelope_schema_version()
    return str(data["$id"])


_OUTPUT_NAMESPACE = ".codegenie"


def declared_inputs_for(probe: _ProbeLike, snapshot: RepoSnapshot) -> list[Path]:
    """Resolve a probe's ``declared_inputs`` globs against ``snapshot.root``.

    Each glob is expanded via :meth:`pathlib.Path.rglob`. Results are
    deduplicated, sorted by string form (stable, deterministic), and paths
    that no longer exist on disk are silently dropped — the cache-miss layer
    is the right place to surface that, not this resolver (story implementer
    note in ``S3-01``).

    Paths inside the codegenie output namespace (``<root>/.codegenie/``) are
    filtered out: the cli writes raw artifacts under
    ``.codegenie/context/raw/`` using basename-derived filenames (e.g. a
    persisted ``pnpm-lock.yaml``). Without this filter, every subsequent
    ``rglob("pnpm-lock.yaml")`` from a probe's declared inputs would match
    the cli's own output, spuriously invalidating warm caches on re-runs
    (S3-06 L-35, L-36; B-1 unblocker). Output dirs are never legitimate
    probe inputs.
    """
    seen: set[Path] = set()
    for pattern in probe.declared_inputs:
        for match in snapshot.root.rglob(pattern):
            if not match.exists():
                continue
            try:
                rel = match.relative_to(snapshot.root)
            except ValueError:
                # rglob can in principle produce paths outside root only
                # when the root itself is symlinked; defensively skip.
                continue
            if rel.parts and rel.parts[0] == _OUTPUT_NAMESPACE:
                continue
            seen.add(match)
    return sorted(seen, key=lambda p: str(p))


def key_for(probe: _ProbeLike, snapshot: RepoSnapshot, task: Task) -> str:
    """Compute the cache key for a probe execution.

    The key is ``identity_hash(probe.name, probe.version,
    per_probe_schema_version(probe),
    content_hash_of_inputs(declared_inputs_for(probe, snapshot)))`` — returned
    as ``sha256:<64-hex>``. Note that ``task`` is intentionally NOT in the
    tuple: Phase 0 has one task class and probe outputs depend on inputs +
    schema only, not on the task envelope. Future task-discriminating probes
    extend the tuple via a sub-schema bump (Rule 5 of CLAUDE.md: keep the
    chokepoint small).
    """
    del task  # accepted for signature stability with the arch-pinned shape
    return identity_hash(
        probe.name,
        probe.version,
        per_probe_schema_version(probe),
        content_hash_of_inputs(declared_inputs_for(probe, snapshot)),
    )
