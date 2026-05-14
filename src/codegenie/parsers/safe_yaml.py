"""``safe_yaml.load`` / ``safe_yaml.load_all`` — chokepoint YAML reader.

Every Phase 1 probe that reads YAML (``pnpm-lock.yaml``, GitHub Actions
workflows, ``Chart.yaml`` / ``values-*.yaml``, ``kustomization.yaml``,
raw K8s manifests, the catalog YAMLs) routes through this module. The
four structural defenses are:

1. ``os.open(path, os.O_RDONLY | os.O_NOFOLLOW)`` refuses a symlink at
   the final path component (``ELOOP``); translated to
   :class:`codegenie.errors.SymlinkRefusedError`. All other ``OSError``
   subclasses propagate unchanged.
2. Pre-parse ``os.fstat`` size cap — bytes are never allocated past
   ``max_bytes``. Raises :class:`codegenie.errors.SizeCapExceeded`.
3. ``yaml.CSafeLoader`` only — required at module import time
   (``ImportError`` on absence). No ``yaml.SafeLoader`` fallback under
   any circumstance (ADR-0009 forbids new C-extension parsers and pins
   ``CSafeLoader`` as the only allowed loader).
4. ``id()``-memoized post-parse depth walker (alias-amplification
   mitigation). ``CSafeLoader`` resolves ``*alias`` references to the
   same Python object — a ten-anchor chain has ten physical nodes but
   ten-billion logical visits under a naive walker. The walker
   memoizes by ``id()`` so each container is descended at most once.
   Raises :class:`codegenie.errors.DepthCapExceeded`.

``yaml.YAMLError`` (covering ``ConstructorError`` for ``!!python/...``
tags, ``ParserError``, ``ScannerError``) is uniformly translated to
:class:`codegenie.errors.MalformedYAMLError`. Top-level non-mapping
non-``None`` documents also raise ``MalformedYAMLError`` — the signature
promises a mapping.

``load_all`` is a lazy generator: it yields each document as it is
parsed, runs the depth walker per document (not on the iterator
wrapper), and yields ``None`` verbatim for empty documents (``---\\n---``
is legal YAML). Callers decide whether to filter (``DeploymentProbe``
filters by ``kind`` per arch §"Component design" #6).

Sources:

- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Component design" #8 — interface and exception map.
- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Edge cases" rows 1, 15 and §"Scenarios" Scenario 3 — billion-laughs
  and alias-amplification flows.
- ``docs/phases/01-context-gather-layer-a-node/ADRs/`` —
  ``0008-in-process-parse-caps-not-per-probe-sandbox.md`` (ADR-0008)
  ratifies in-process caps; ``0009-no-new-c-extension-parser-dependencies.md``
  (ADR-0009) pins ``CSafeLoader`` as the only allowed loader.

Every typed exception this module raises is a **marker** — a single
positional formatted-message string with no instance state — preserving
the Phase 0 ``test_subclasses_are_markers_only`` invariant. The catch
site (a probe) reconstructs the structured ``WarningId`` per ADR-0007
from probe context.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Final

import yaml

from codegenie.errors import MalformedYAMLError
from codegenie.parsers import JSONValue
from codegenie.parsers._depth import assert_max_depth
from codegenie.parsers._io import open_capped

__all__ = ["load", "load_all"]

_PARSER_KIND: Final[str] = "safe_yaml"

if getattr(yaml, "CSafeLoader", None) is None:  # pragma: no cover - import-time guard
    raise ImportError(
        "yaml.CSafeLoader is required (ADR-0008, ADR-0009). "
        "Install pyyaml with libyaml support; SafeLoader fallback is banned."
    )


def load(path: Path, *, max_bytes: int, max_depth: int = 64) -> Mapping[str, JSONValue]:
    """Parse ``path`` as a single top-level YAML mapping with size + depth caps.

    Args:
        path: File to read. Must be a regular file (or fail loudly).
        max_bytes: Hard upper bound on file size; exceeding raises
            :class:`SizeCapExceeded` *before* any bytes are read.
        max_depth: Maximum container nesting depth. Defaults to 64.

    Returns:
        The decoded YAML mapping as ``dict[str, JSONValue]``.

    Raises:
        SymlinkRefusedError: ``path``'s final component is a symlink
            (``OSError(errno=ELOOP)``).
        SizeCapExceeded: ``os.fstat(fd).st_size > max_bytes``.
        MalformedYAMLError: empty file, ``yaml.YAMLError`` (any subclass),
            or top-level non-mapping (list / scalar / ``None``).
        DepthCapExceeded: container nesting exceeds ``max_depth``.
        FileNotFoundError: ``path`` does not exist — passes through.
        OSError: any other open-time error — passes through unchanged.
    """
    data = open_capped(path, max_bytes=max_bytes, parser_kind=_PARSER_KIND)
    obj = _parse_one(data, path=path)
    if obj is None or not isinstance(obj, dict):
        kind = "None" if obj is None else type(obj).__name__
        raise MalformedYAMLError(f"{path}: top-level must be a mapping (got {kind})")
    assert_max_depth(obj, max_depth=max_depth, path=path, parser_kind=_PARSER_KIND)
    return obj


def load_all(
    path: Path, *, max_bytes: int, max_depth: int = 64
) -> Iterator[Mapping[str, JSONValue] | None]:
    """Lazily parse ``path`` as a multi-document YAML stream.

    Yields each document in source order. Empty documents (``---\\n---``)
    yield ``None`` — callers decide whether to filter. Non-mapping
    non-``None`` documents raise :class:`MalformedYAMLError` from the
    ``next()`` call that surfaces them. The depth walker runs **per
    document**, so a valid first document surfaces before a later
    document raises.

    Args:
        path: File to read.
        max_bytes: Pre-parse size cap (whole file).
        max_depth: Per-document container nesting cap.

    Yields:
        Each document as ``dict[str, JSONValue]`` or ``None``.

    Raises:
        Same set as :func:`load`, but :class:`MalformedYAMLError` /
        :class:`DepthCapExceeded` raise from inside the generator on the
        offending ``next()`` rather than at construction time.
    """
    data = open_capped(path, max_bytes=max_bytes, parser_kind=_PARSER_KIND)
    return _generate(data, path=path, max_depth=max_depth)


def _parse_one(data: bytes, *, path: Path) -> object:
    """Run ``yaml.load`` with ``CSafeLoader``; translate ``YAMLError``."""
    try:
        return yaml.load(data, Loader=yaml.CSafeLoader)
    except yaml.YAMLError as exc:
        raise MalformedYAMLError(f"{path}: {type(exc).__name__}: {exc}") from exc


def _generate(
    data: bytes, *, path: Path, max_depth: int
) -> Iterator[Mapping[str, JSONValue] | None]:
    """Lazy multi-doc generator — depth-walks and yields one doc at a time."""
    try:
        for doc in yaml.load_all(data, Loader=yaml.CSafeLoader):
            if doc is not None and not isinstance(doc, dict):
                raise MalformedYAMLError(
                    f"{path}: document must be a mapping or empty (got {type(doc).__name__})"
                )
            if doc is not None:
                assert_max_depth(doc, max_depth=max_depth, path=path, parser_kind=_PARSER_KIND)
            yield doc
    except yaml.YAMLError as exc:
        raise MalformedYAMLError(f"{path}: {type(exc).__name__}: {exc}") from exc
