"""Capability-construction AST fence — S4-05 / 03-ADR-0011.

AST-walks ``src/codegenie/`` (plus future plugin roots) and reports any
``*Capability(...)`` constructor call outside the single chokepoint at
:mod:`codegenie.plugins.capabilities`. Consumed from
:mod:`tests.fence.test_capability_fence`.

**Honest framing posture** (mirrors :mod:`codegenie._phase3_fence`): this
fence is **audit + lint** enforcement, NOT a runtime guarantee. A PR that
edits both the fence file and the violation defeats the fence — CODEOWNERS
on ``tests/fence/`` is the social anchor.

**Walker-home decision (Rule 7 + Rule 11).** 03-ADR-0011 §Consequences
originally named ``tooling/ruff_rules/no_capability_construction.py``, but
the codebase has no ``tooling/`` directory and no ruff-plugin scaffolding.
The established precedent is :mod:`codegenie._phase3_fence` (S1-05) — a
pure-Python AST walker consumed from ``tests/fence/``. S4-05 picks the
more-recent and more-tested codebase convention; ADR-0011 §Consequences
is amended to point at this module (one-line edit).

**Extension-by-addition.** Adding a fourth capability type is a one-line
edit to :data:`_CAPABILITY_CLASS_NAMES`. The walker introspects the AST
at parse time and never imports the modules it scans, so adding a new
capability class does not require touching the walker until the constant
is updated.

Sources:

- 03-ADR-0011 §Decision §Capability tokens — lint enforcement.
- ``docs/phases/03-vuln-deterministic-recipe/stories/
  S4-05-allowed-binaries-capabilities.md`` — story.
- :mod:`codegenie._phase3_fence` — precedent walker.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

__all__ = [
    "_CAPABILITY_CLASS_NAMES",
    "_CAPABILITY_FENCE_ROOTS",
    "_MARKER_PATTERN",
    "Violation",
    "find_violations",
]


_CAPABILITY_FENCE_ROOTS: Final[tuple[Path, ...]] = (Path("src/codegenie"),)
"""Roots scanned by :func:`find_violations`.

Extension is by **one-line append** at Phase-7 time (when ``plugins/`` ships
real Python under ``vulnerability-remediation--node--npm/recipes/``). The
floor-guard assertion in :mod:`tests.fence.test_capability_fence` catches
the case where a root gets deleted or accidentally emptied.
"""


_CAPABILITY_CLASS_NAMES: Final[frozenset[str]] = frozenset(
    {"NpmInstallCapability", "FsReadWriteCapability", "GitLocalOpsCapability"}
)
"""The three capability constructor names the fence reports.

:class:`CapabilityBundle` is the aggregator and is *intentionally* NOT in
this set — the bundle is meant to flow through arbitrary call sites; only
*individual capability* instantiation is fenced.

Refactor trigger: when the fourth capability type lands (Phase 7 likely
introduces ``ContainerOpsCapability``), evaluate whether to refactor this
set to introspect ``codegenie.plugins.capabilities.__all__`` (data-driven).
Until then the hardcoded literal is the precedent — mirrors
:data:`codegenie.exec.ALLOWED_BINARIES`'s ADR-pinned amendment discipline.
"""


_CHOKEPOINT_RELATIVE_PATH: Final[tuple[str, ...]] = (
    "codegenie",
    "plugins",
    "capabilities.py",
)
"""Trailing path segments identifying the single legal chokepoint. The
walker's exclusion uses tail-match (``parts[-3:] == _CHOKEPOINT_...``) so
the check is repo-layout independent — the fixture under ``tmp_path/src/
codegenie/plugins/capabilities.py`` is recognised even when planted by a
test under a different working directory."""


_MARKER_PATTERN: Final[str] = "# fence: capability-allowed [P3-ADR-0011]"
"""Inline escape-hatch marker. A capability constructor on a line where
this marker appears in the first 5 lines of the enclosing file is NOT
reported. Mirrors the ``_phase3_fence`` marker discipline; new markers
require an ADR amendment per ADR-0011 §Consequences."""


@dataclass(frozen=True)
class Violation:
    """One capability constructor reported outside the chokepoint.

    ``snippet`` is the unparsed AST source for the offending Call node so
    the error message points at the exact construction. Frozen so callers
    can hash and dedupe across walks if a Phase-7 multi-root scan ever
    needs union semantics.
    """

    file: Path
    line: int
    class_name: str
    snippet: str


def _is_chokepoint(path: Path) -> bool:
    """Tail-match against ``codegenie/plugins/capabilities.py``."""
    parts = path.parts
    return len(parts) >= 3 and parts[-3:] == _CHOKEPOINT_RELATIVE_PATH


def _is_in_tests(path: Path) -> bool:
    """Tail-match: any ancestor segment is exactly ``tests``."""
    return "tests" in path.parts


def _has_marker_in_first_lines(source_lines: list[str]) -> bool:
    """True iff any of the first 5 lines carry the escape-hatch marker.

    Mirrors :data:`codegenie._phase3_fence.ALLOWED_MARKER_RE` discipline:
    the marker is whole-file scope (first 5 lines) rather than per-line so
    files explicitly marked as "capability-allowed" by an ADR are blanket-
    excluded. Per-line markers would invite drift — the kill happens at
    the file boundary."""
    return any(_MARKER_PATTERN in line for line in source_lines[:5])


def _violations_for_source(src: str, path: Path) -> list[Violation]:
    """Parse *src* and return every capability-constructor Call outside the
    chokepoint. Pure function — no I/O — so the planted-positive tests can
    feed synthetic strings."""
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        raise AssertionError(
            f"Capability fence walker could not parse {path}: {exc}. "
            f"Fix the syntax error before re-running the fence."
        ) from exc

    out: list[Violation] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _CAPABILITY_CLASS_NAMES
        ):
            try:
                snippet = ast.unparse(node)
            except (ValueError, AttributeError):
                snippet = node.func.id
            out.append(
                Violation(
                    file=path,
                    line=node.lineno,
                    class_name=node.func.id,
                    snippet=snippet,
                )
            )
    return out


def find_violations(
    roots: Iterable[Path] = _CAPABILITY_FENCE_ROOTS,
) -> list[Violation]:
    """Scan *roots* recursively and return every capability constructor
    Call node outside the chokepoint, sorted by ``(file, line, class_name)``.

    Excludes:

    * The chokepoint :mod:`codegenie.plugins.capabilities` itself
      (tail-match on the file path).
    * Any file under a ``tests/`` ancestor segment.
    * Any file whose first 5 lines contain :data:`_MARKER_PATTERN`.

    Pure function — no global state — so multiple concurrent walks are safe.
    Mirrors :func:`codegenie._phase3_fence.scan_phase3_surface` shape.
    """
    out: list[Violation] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if _is_chokepoint(path) or _is_in_tests(path):
                continue
            text = path.read_text(encoding="utf-8")
            if _has_marker_in_first_lines(text.splitlines()):
                continue
            out.extend(_violations_for_source(text, path))
    return sorted(out, key=lambda v: (str(v.file), v.line, v.class_name))
