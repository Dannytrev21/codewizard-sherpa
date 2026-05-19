"""Phase 7 ``Any`` annotation fence — audit + lint, NOT runtime (ADR-0011).

Pins ``src/codegenie/primitives/vuln_provenance/`` to be free of ``Any`` /
``dict[str, Any]`` / ``typing.Any`` annotations in declaration positions.
The deliberate ``extra='allow'`` on ``SyftSbom`` (S1-05) admits unknown
keys via Pydantic's generated ``__pydantic_extra__`` attribute — that
attribute is NOT declared in the source AST, so the fence does not see
it. Every other typed boundary in the primitive stays ``extra='forbid'``
(see Phase 7 ADR-0004 + arch-design §Anti-patterns avoided).

Live + planted-positive tests call the SAME ``walk_any_annotations()``
function from ``codegenie._phase3_fence`` — the walker is the canonical
home, Phase 7 reuses it (mutation-resistance property inherited from the
Phase-0 / Phase-3 precedent; Rule 7 — don't fork).

Documented limitation: a PR that edits this fence file AND introduces a
violation in the same commit defeats the fence — CODEOWNERS on
``tests/fence/`` is the social anchor (ADR-0011).
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Final

import pytest

from codegenie._phase3_fence import (
    Violation,
    walk_any_annotations,
)

PHASE7_ROOTS: Final[tuple[Path, ...]] = (Path("src/codegenie/primitives/vuln_provenance"),)
"""The Phase 7 contract-surface roots scanned by the AST walker.

A single root today (``vuln_provenance``). Extension to additional
Phase-7 primitive surfaces is by one-line append; new surfaces require
an ADR amendment so the fence's blast radius is reviewed.
"""


def _iter_python_files(root: Path) -> list[Path]:
    """Return ALL ``*.py`` files under ``root`` (including ``__init__.py``),
    sorted. Including ``__init__.py`` here is the intended discipline:
    re-exports in the package init are part of the public surface and an
    ``Any`` annotation there is just as harmful as one in a submodule."""
    return sorted(root.rglob("*.py"))


def _scan_phase7_surface() -> list[Violation]:
    """Live scan over ``PHASE7_ROOTS``; raises if a root is missing or empty.

    Floor guard (AC-4 floor): catches the case where the primitive package
    gets deleted or accidentally emptied — silent green is the worst
    failure mode (Rule 12). The error message names the missing-or-empty
    root."""
    out: list[Violation] = []
    for root in PHASE7_ROOTS:
        if not root.is_dir():
            raise AssertionError(
                f"Phase-7 fence root {root} does not exist. The fence requires "
                f"every entry in PHASE7_ROOTS to be a directory; if the package "
                f"was intentionally removed, edit PHASE7_ROOTS via ADR amendment."
            )
        files = [p for p in _iter_python_files(root) if p.name != "__init__.py"]
        if not files:
            raise AssertionError(
                f"Phase-7 fence root {root} contains no non-__init__.py modules. "
                f"This would silently green the fence; refusing to proceed."
            )
        for file in _iter_python_files(root):
            text = file.read_text(encoding="utf-8")
            out.extend(walk_any_annotations(text, file))
    return out


# ---------------------------------------------------------------------------
# AC-4 floor guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("root", PHASE7_ROOTS, ids=lambda p: str(p))
def test_each_phase7_root_exists_and_is_non_empty(root: Path) -> None:
    """Floor guard: a future deletion of ``vuln_provenance/`` is NOT silent green."""
    assert root.is_dir(), f"Phase 7 root {root} missing — fence cannot run"
    non_init_modules = [p for p in root.rglob("*.py") if p.name != "__init__.py"]
    assert non_init_modules, (
        f"Phase 7 root {root} has only __init__.py — fence would silently green"
    )


# ---------------------------------------------------------------------------
# AC-4 live scan
# ---------------------------------------------------------------------------


def test_phase7_surface_has_no_any_annotations() -> None:
    """AC-4: zero ``Any`` annotations under ``src/codegenie/primitives/vuln_provenance``."""
    violations = _scan_phase7_surface()
    assert violations == [], (
        f"Phase-7 primitive surface introduced Any annotations: "
        f"{[(str(v.file), v.line, v.kind, v.snippet) for v in violations]}. "
        f"Remove them; the SyftSbom `extra='allow'` admits unknown keys via "
        f"Pydantic's generated `__pydantic_extra__` (not in the AST), so an "
        f"explicit `Any` annotation is not the right tool here."
    )


# ---------------------------------------------------------------------------
# AC-5 syft_reader.py exempt-but-clean check
# ---------------------------------------------------------------------------


def test_syft_reader_has_no_declared_any_annotations() -> None:
    """AC-5: the deliberate ``extra='allow'`` on ``SyftSbom`` does NOT manifest
    as a declared ``Any`` annotation. Pydantic generates
    ``__pydantic_extra__`` at runtime; it is not in the source AST.

    If S1-05 was implemented correctly (no declared `Any`), this test is
    green today; a future PR adding ``metadata: dict[str, Any]`` to a Pydantic
    model under syft_reader.py fires this — exactly the intended discipline.
    """
    path = PHASE7_ROOTS[0] / "syft_reader.py"
    assert path.is_file(), f"syft_reader.py missing at {path}"
    violations = walk_any_annotations(path.read_text(encoding="utf-8"), path)
    assert violations == [], (
        f"syft_reader.py introduced declared `Any` annotations: {violations}. "
        f"The `extra='allow'` carve-out applies to Pydantic's generated "
        f"`__pydantic_extra__` only — declared annotations must stay typed."
    )


# ---------------------------------------------------------------------------
# AC-4 per-shape planted-violation matrix (reuses Phase 3 visitor under the
# Phase 7 surface — each row is one mutation guard against a regression that
# drops a shape from the visitor's coverage)
# ---------------------------------------------------------------------------

_SHAPE_MATRIX: Final[tuple[tuple[str, bool], ...]] = (
    ("x: Any = 1", True),
    ("def f(x: Any) -> None: ...", True),
    ("def f() -> Any: ...", True),
    ("x: dict[str, Any] = {}", True),
    ("x: Dict[str, Any] = {}", True),
    ("x: list[Any] = []", True),
    ("x: tuple[Any, ...] = ()", True),
    ("x: typing.Any = 1", True),
    ("x: Callable[..., Any] = None", True),
    ("x: dict[str, list[Any]] = {}", True),
    ('x: "Any" = 1', True),
    ('x: "dict[str, Any]" = {}', True),
    ("x: int = 1", False),
    ("x: dict[str, int] = {}", False),
    ("isinstance(obj, Any)", False),
    ("if TYPE_CHECKING:\n    from typing import Any", False),
    ("from typing import Any", False),
)


@pytest.mark.parametrize(
    "snippet,expected_hit",
    _SHAPE_MATRIX,
    ids=[s.replace("\n", "\\n")[:50] for s, _ in _SHAPE_MATRIX],
)
def test_walker_catches_each_shape(snippet: str, expected_hit: bool) -> None:
    """AC-4 mutation guard: each row independently checks a shape. The walker
    used is the SAME one Phase 3 uses (``walk_any_annotations``); a
    regression in the visitor fails both Phase 3 and Phase 7 — the canonical
    mutation-resistance property."""
    violations = walk_any_annotations(textwrap.dedent(snippet), path=Path("_test.py"))
    actual_hit = len(violations) > 0
    assert actual_hit is expected_hit, (
        f"Shape `{snippet!r}` expected hit={expected_hit}, got {violations}"
    )
