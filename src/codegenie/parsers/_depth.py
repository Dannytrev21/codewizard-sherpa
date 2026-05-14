"""Shared post-parse depth walker for ``codegenie.parsers``.

The stdlib ``json`` C extension and ``yaml.CSafeLoader`` expose no native
depth limit, so a second pass walks the decoded structure to enforce
``max_depth``. This module is the single implementation; every parser
calls into it.

YAML-only requirement: ``CSafeLoader`` resolves ``*alias`` references to
**the same Python object**, so the parsed graph is a DAG rather than a
tree. A naive recursive walker re-enters shared subtrees once per
alias-resolution — a ten-anchor chain has ten physical nodes but
ten-billion logical visits. This walker memoizes visited containers by
``id()`` so each container is descended at most once. The defense is
load-bearing for YAML and harmless for JSON (which never produces shared
references through ``json.loads``).

Sources:

- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Component design" #8 — the post-parse walker rationale.
- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Edge cases" row 1, §"Scenarios" Scenario 3 — billion-laughs and
  alias-amplification flows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import structlog

from codegenie.errors import DepthCapExceeded

__all__ = ["assert_max_depth"]

_EVENT_CAP_EXCEEDED: Final[str] = "probe.parser.cap_exceeded"
_CAP_KIND_DEPTH: Final[str] = "depth"

_logger = structlog.get_logger(__name__)


def assert_max_depth(obj: object, *, max_depth: int, path: Path, parser_kind: str) -> None:
    """Walk ``obj`` and raise :class:`DepthCapExceeded` past ``max_depth``.

    Depth counts container nesting only; scalars (``None``, ``bool``,
    ``int``, ``float``, ``str``) do not contribute. The root container is
    depth ``0``; descending into one nested container makes the inner
    container depth ``1``. ``current == max_depth`` is allowed;
    ``current > max_depth`` raises.

    Containers already visited (by ``id()``) are skipped on re-entry. This
    is the alias-amplification defense: a YAML DAG with ``k`` physical
    nodes is walked in ``O(k)``, regardless of how many ``*alias``
    references resolve to the shared subtree.

    Args:
        obj: Decoded structure (typically a ``dict`` or ``list``).
        max_depth: Maximum container nesting depth.
        path: Source path — surfaces on the cap-exceeded event.
        parser_kind: Caller-supplied discriminator (``"safe_json"``,
            ``"safe_yaml"``, …).

    Raises:
        DepthCapExceeded: container nesting exceeds ``max_depth``.
    """
    seen: set[int] = set()
    _walk(obj, current=0, max_depth=max_depth, path=path, parser_kind=parser_kind, seen=seen)


def _walk(
    obj: object,
    *,
    current: int,
    max_depth: int,
    path: Path,
    parser_kind: str,
    seen: set[int],
) -> None:
    if not isinstance(obj, (dict, list)):
        return
    if current > max_depth:
        _emit_depth_cap_event(path=path, cap=max_depth, parser_kind=parser_kind)
        raise DepthCapExceeded(f"{path}: depth>{max_depth}")
    obj_id = id(obj)
    if obj_id in seen:
        return
    seen.add(obj_id)
    next_depth = current + 1
    if isinstance(obj, dict):
        for value in obj.values():
            _walk(
                value,
                current=next_depth,
                max_depth=max_depth,
                path=path,
                parser_kind=parser_kind,
                seen=seen,
            )
    else:
        for item in obj:
            _walk(
                item,
                current=next_depth,
                max_depth=max_depth,
                path=path,
                parser_kind=parser_kind,
                seen=seen,
            )


def _emit_depth_cap_event(*, path: Path, cap: int, parser_kind: str) -> None:
    """Emit the single ``probe.parser.cap_exceeded`` event on depth violation."""
    _logger.info(
        _EVENT_CAP_EXCEEDED,
        cap_kind=_CAP_KIND_DEPTH,
        cap=cap,
        path=str(path),
        parser=parser_kind,
        parser_kind=parser_kind,
    )
