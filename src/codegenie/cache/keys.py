"""Cache key derivation — per-probe vs envelope schema versioning (ADR-0003).

The cache key is ``identity_hash(probe.name, probe.version,
per_probe_schema_version(probe), content_hash_of_inputs(declared_inputs_for(...)))``,
plus any resolved special-token values from
:func:`_special_token_values_for` (02-ADR-0004; S5-02 lands the
``image-digest:<resolved>`` dispatch arm — the first consumer of the
mechanism S1-09 introduced on :class:`ProbeContext`).

The load-bearing distinction this module encodes:

- :func:`envelope_schema_version` returns the envelope's ``$id`` version. The
  envelope is metadata (ADR-0013) — bumping it must NOT invalidate any
  probe's cache. The envelope version is **deliberately not** in the key.
- :func:`per_probe_schema_version` returns the probe's own sub-schema ``$id``
  if present, falling back to :func:`envelope_schema_version` for probes that
  haven't shipped a sub-schema yet. Bumping one probe's sub-schema
  invalidates only that probe's cache entries — surgical invalidation,
  Phase 14 continuous-gather compatible (ADR-0003 §Decision).
- Special-token dispatch is a ``match`` on the token name with an explicit
  ``raise CacheKeyError(reason="unknown_special_token", token=…)`` on the
  otherwise arm — the Open/Closed seam for future tokens
  (``scip-index-output:``, ``tree-sitter-grammar-set:``). Future arms add
  via ADR amendment to 02-ADR-0004.

The schema-directory resolver lives in module-level :data:`_SCHEMA_DIR` so
tests can monkeypatch it to a tmp_path containing synthetic sub-schemas
without touching the installed package.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from codegenie.errors import CodegenieError
from codegenie.hashing import content_hash_of_inputs, identity_hash

if TYPE_CHECKING:
    from codegenie.probes.base import ProbeContext, RepoSnapshot, Task

__all__ = [
    "CacheKeyError",
    "declared_inputs_for",
    "envelope_schema_version",
    "key_for",
    "per_probe_schema_version",
]


class CacheKeyError(CodegenieError):
    """Raised when cache-key derivation hits an undispatchable special token.

    Carries ``reason`` (a short machine-readable tag, e.g.
    ``"unknown_special_token"``) and ``token`` (the full offending
    ``<name>:<resolved>`` string) so the caller's structured log surfaces
    both. The class stays a marker per Phase 0 ``test_subclasses_are_markers_only``
    discipline: no behavior beyond carrying the two strings in the message.
    """

    def __init__(self, *, reason: str, token: str) -> None:
        super().__init__(f"{reason}: {token}")
        self.reason = reason
        self.token = token


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

# Special-token syntax: ``<name>:<resolved>`` where ``<name>`` is a
# lowercase identifier composed of ``[a-z0-9_-]``. Anything else continues
# down the rglob path. The literal ``<resolved>`` placeholder is the
# contract pin — bare ``image-digest:`` (without the placeholder) is NOT a
# token; it would rglob like any other entry and silently miss the
# resolver path. (02-ADR-0004 §Decision; ``localv2.md §4``.)
_SPECIAL_TOKEN_RE = re.compile(r"^([a-z0-9_-]+):<resolved>$")

# Sentinel folded into the cache key when an ``image-digest:<resolved>``
# token cannot be resolved (resolver unbound, returned ``None``, or raised).
# The three "unresolved" paths share one sentinel so the cache key is
# stable across them — the diagnostic distinction lives in the probe's
# structured log (S5-02), not in the key.
_UNRESOLVED_SENTINEL = ""


def _is_special_token(pattern: str) -> bool:
    """Return ``True`` iff ``pattern`` matches the ``<name>:<resolved>`` shape."""
    return _SPECIAL_TOKEN_RE.fullmatch(pattern) is not None


def _resolve_special_token(
    token: str,
    snapshot: RepoSnapshot,
    ctx: ProbeContext | None,
) -> str:
    """Dispatch one special token to its resolved string value.

    ``token`` must already have passed :func:`_is_special_token`. The
    dispatch is a ``match`` on the token name; the otherwise arm raises
    :class:`CacheKeyError` so adding a new arm is a deliberate ADR-amend
    rather than a silent fallthrough (the Open/Closed seam — 02-ADR-0004
    §Consequences).

    The ``image-digest:`` arm:

    - returns ``_UNRESOLVED_SENTINEL`` if ``ctx`` is ``None``, or if
      ``ctx.image_digest_resolver`` is unbound, or if the resolver returns
      ``None``, or if the resolver raises any exception (translated to the
      sentinel; the probe's call-site catches the exception too — this
      function is defense-in-depth so the cache key stays well-defined
      across every "unresolved" path).
    """
    match = _SPECIAL_TOKEN_RE.fullmatch(token)
    if match is None:  # pragma: no cover — caller guards via _is_special_token
        raise CacheKeyError(reason="malformed_special_token", token=token)
    name = match.group(1)
    match name:
        case "image-digest":
            if ctx is None:
                return _UNRESOLVED_SENTINEL
            resolver = ctx.image_digest_resolver
            if resolver is None:
                return _UNRESOLVED_SENTINEL
            try:
                resolved = resolver(snapshot.root)
            except Exception:  # noqa: BLE001 — defensive: any resolver failure
                return _UNRESOLVED_SENTINEL
            return resolved if resolved is not None else _UNRESOLVED_SENTINEL
        case _:
            raise CacheKeyError(reason="unknown_special_token", token=token)


def declared_inputs_for(probe: _ProbeLike, snapshot: RepoSnapshot) -> list[Path]:
    """Resolve a probe's ``declared_inputs`` globs against ``snapshot.root``.

    Each glob is expanded via :meth:`pathlib.Path.rglob`. Results are
    deduplicated, sorted by string form (stable, deterministic), and paths
    that no longer exist on disk are silently dropped — the cache-miss layer
    is the right place to surface that, not this resolver (story implementer
    note in ``S3-01``).

    Entries matching the ``<name>:<resolved>`` special-token syntax
    (02-ADR-0004; e.g. ``image-digest:<resolved>``) are **not** rglobbed —
    they are skipped here and handled separately by :func:`key_for` via
    :func:`_resolve_special_token`. Folding them into the path list would
    silently rglob a literal filename like ``image-digest:<resolved>`` and
    quietly miss the resolver, defeating cache correctness.

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
        if _is_special_token(pattern):
            continue
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


def _special_token_values_for(
    probe: _ProbeLike,
    snapshot: RepoSnapshot,
    ctx: ProbeContext | None,
) -> list[str]:
    """Return resolved values for every special token in ``probe.declared_inputs``.

    Tokens appear in the cache-key tuple in their stable declaration order
    so two probes that declare the same tokens in different orders would
    still receive distinct keys (consistent with the existing per-pattern
    file-content hashing). Unknown tokens raise :class:`CacheKeyError`
    immediately — silent fallthrough would defeat the dispatch.
    """
    resolved: list[str] = []
    for pattern in probe.declared_inputs:
        if _is_special_token(pattern):
            resolved.append(_resolve_special_token(pattern, snapshot, ctx))
    return resolved


def key_for(
    probe: _ProbeLike,
    snapshot: RepoSnapshot,
    task: Task,
    *,
    ctx: ProbeContext | None = None,
) -> str:
    """Compute the cache key for a probe execution.

    The key is ``identity_hash(probe.name, probe.version,
    per_probe_schema_version(probe),
    content_hash_of_inputs(declared_inputs_for(probe, snapshot)),
    *_special_token_values_for(probe, snapshot, ctx))`` — returned as
    ``sha256:<64-hex>``. Note that ``task`` is intentionally NOT in the
    tuple: Phase 0 has one task class and probe outputs depend on inputs +
    schema only, not on the task envelope. Future task-discriminating probes
    extend the tuple via a sub-schema bump (Rule 5 of CLAUDE.md: keep the
    chokepoint small).

    The optional ``ctx`` kwarg supplies the
    :class:`~codegenie.probes.base.ProbeContext` whose
    ``image_digest_resolver`` callable is consulted when a probe declares
    the ``image-digest:<resolved>`` token (02-ADR-0004 + S5-02). When
    ``ctx`` is ``None``, every special token folds to the unresolved
    sentinel — the cache key still derives deterministically.

    Raises :class:`CacheKeyError` if any declared input matches the
    ``<name>:<resolved>`` shape but the name has no dispatch arm.
    """
    del task  # accepted for signature stability with the arch-pinned shape
    return identity_hash(
        probe.name,
        probe.version,
        per_probe_schema_version(probe),
        content_hash_of_inputs(declared_inputs_for(probe, snapshot)),
        *_special_token_values_for(probe, snapshot, ctx),
    )
