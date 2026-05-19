"""Phase-3 ``Any`` annotation fence — audit + lint, NOT runtime (ADR-0011).

Pins ``src/codegenie/{plugins,transforms}/`` to be free of ``Any`` /
``dict[str, Any]`` / ``typing.Any`` annotations in declaration positions.
Live + planted-positive tests call the SAME ``walk_any_annotations()``
function from ``codegenie._phase3_fence`` (mutation-resistance property
inherited from the Phase-0 ``codegenie._fence`` precedent).

Documented limitation: a PR that edits this fence file AND introduces a
violation in the same commit defeats the fence — CODEOWNERS on
``tests/fence/`` is the social anchor (ADR-0011).
"""

from __future__ import annotations

import importlib
import textwrap
from pathlib import Path
from typing import Final

import pytest

from codegenie._phase3_fence import (
    ALLOWED_MARKER_RE,
    KNOWN_BYPASSES,
    PHASE3_ROOTS,
    Violation,
    scan_phase3_surface,
    walk_any_annotations,
)

# ---------------------------------------------------------------------------
# AC-5 live scan + AC-5.a floor guard
# ---------------------------------------------------------------------------


def test_phase3_surface_has_no_any_annotations() -> None:
    """AC-5: zero ``Any`` annotations under ``src/codegenie/{plugins,transforms}``."""
    violations = scan_phase3_surface()
    assert violations == [], (
        f"Phase-3 contract surface introduced Any annotations: "
        f"{[(str(v.file), v.line, v.kind, v.snippet) for v in violations]}. "
        f"Either remove them or add an ADR amendment + inline marker "
        f"`# fence: any-allowed [P3-ADR-NNNN]`."
    )


@pytest.mark.parametrize("root", PHASE3_ROOTS, ids=lambda p: str(p))
def test_each_phase3_root_exists_and_is_non_empty(root: Path) -> None:
    """AC-5.a floor guard: a future deletion of ``plugins/`` is NOT silent green."""
    assert root.is_dir(), f"Phase 3 root {root} missing — fence cannot run"
    non_init_modules = [p for p in root.rglob("*.py") if p.name != "__init__.py"]
    assert non_init_modules, (
        f"Phase 3 root {root} has only __init__.py — fence would silently green"
    )


# ---------------------------------------------------------------------------
# AC-5.b per-shape planted-violation matrix
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
    """AC-5.b mutation guard — each row is one independent guard against
    a regression that drops a shape from the visitor's coverage."""
    violations = walk_any_annotations(textwrap.dedent(snippet), path=Path("_test.py"))
    actual_hit = len(violations) > 0
    assert actual_hit is expected_hit, (
        f"Shape `{snippet!r}` expected hit={expected_hit}, got {violations}"
    )


# ---------------------------------------------------------------------------
# AC-5.c marker grammar
# ---------------------------------------------------------------------------

_MARKER_GRAMMAR_CASES: Final[tuple[tuple[str, bool], ...]] = (
    # (full source line containing an Any annotation + marker, expected_clean)
    ("x: Any = 1  # fence: any-allowed [P3-ADR-0010]\n", True),
    ("x: Any = 1  # fence:any-allowed[P3-ADR-0010]\n", True),  # whitespace-tolerant
    ("x: Any = 1  # fence: any-allowed\n", False),  # bare — violation
    ("x: Any = 1  # fence: any-allowed []\n", False),  # empty
    ("x: Any = 1  # fence: any-allowed [garbage]\n", False),  # malformed
    ("x: Any = 1  # fence: any-allowed [P3-ADR-12]\n", False),  # too few digits
    ("x: Any = 1  # fence: any-allowed [PROD-ADR-0010]\n", False),  # wrong prefix
)


@pytest.mark.parametrize(
    "src,expected_clean",
    _MARKER_GRAMMAR_CASES,
    ids=[s.strip()[:60] for s, _ in _MARKER_GRAMMAR_CASES],
)
def test_marker_grammar(src: str, expected_clean: bool) -> None:
    """AC-5.c: only ``# fence: any-allowed [P3-ADR-NNNN]`` exempts; any other
    shape that *looks like* a marker is itself a violation."""
    violations = walk_any_annotations(src, path=Path("_marker_test.py"))
    if expected_clean:
        assert violations == [], (
            f"Valid marker should suppress hit. Source: {src!r}, got {violations}"
        )
    else:
        assert violations, f"Bare or malformed marker MUST be a violation. Source: {src!r}"


def test_allowed_marker_regex_shape() -> None:
    """The regex itself is a stable contract — pinning its pattern catches a
    later 'cleanup' that accidentally widens the grammar."""
    assert ALLOWED_MARKER_RE.pattern == (
        r"#\s*fence:\s*any-allowed\s*\[(?P<adr>P3-ADR-\d{4})\]\s*$"
    )


# ---------------------------------------------------------------------------
# AC-5.d zero markers at S1-05 landing
# ---------------------------------------------------------------------------


def test_zero_allowlist_markers_at_step1_landing() -> None:
    """AC-5.d: ``# fence: any-allowed`` markers MUST NOT appear under
    ``src/codegenie/{plugins,transforms}/`` at S1-05 GREEN time. New markers
    require an ADR amendment + same-PR review."""
    hits: list[tuple[Path, int, str]] = []
    for root in PHASE3_ROOTS:
        for file in root.rglob("*.py"):
            for idx, line in enumerate(file.read_text().splitlines(), start=1):
                if "fence: any-allowed" in line or "fence:any-allowed" in line:
                    hits.append((file, idx, line.strip()))
    assert hits == [], (
        f"Found inline allowlist markers at Step-1 landing time: {hits}. "
        f"Each marker requires a Phase-3 ADR amendment."
    )


# ---------------------------------------------------------------------------
# AC-5.e known-bypass catalogue
# ---------------------------------------------------------------------------


def test_known_bypasses_constant_is_non_empty_and_documented() -> None:
    """The walker advertises its limitations. An empty ``KNOWN_BYPASSES``
    would mean either zero limitations (false) or undocumented ones (worse)."""
    assert KNOWN_BYPASSES, "KNOWN_BYPASSES must enumerate documented walker gaps"
    expected_keys = {
        "type-comment-annotation",
        "from-typing-import-any-as-alias",
        "from-typing-extensions-import-any",
    }
    assert KNOWN_BYPASSES == frozenset(expected_keys), (
        f"KNOWN_BYPASSES drift: {KNOWN_BYPASSES} != {expected_keys}. "
        f"Update both the constant and ``tests/fence/_fixtures/_known_bypasses.py``."
    )


def test_known_bypass_fixture_imports_cleanly() -> None:
    """Prove the bypass fixture is a real file (otherwise the catalogue
    documents nothing)."""
    mod = importlib.import_module("tests.fence._fixtures._known_bypasses")
    # The fixture defines ``type_comment_bypass`` (dict) + ``aliased_bypass``
    # (typed via aliased ``Any``). Both attributes must exist.
    assert hasattr(mod, "type_comment_bypass")
    assert hasattr(mod, "aliased_bypass")


def test_walker_misses_bypass_shapes() -> None:
    """The walker is documented as NOT catching these shapes; if a future
    walker upgrade fixes one, this test fires so the bypass entry can be
    removed in the same PR (fail-loud invariant)."""
    fixture_path = Path(__file__).parent / "_fixtures" / "_known_bypasses.py"
    text = fixture_path.read_text(encoding="utf-8")
    violations = walk_any_annotations(text, path=fixture_path)
    # ``aliased_bypass: _Any`` — visitor's ``ast.Name(id="Any")`` check looks
    # for ``Any`` exactly, not ``_Any``, so this MUST slip through.
    aliased_hits = [v for v in violations if v.snippet == "Any" and v.line >= 18]
    assert aliased_hits == [], (
        "Walker now catches aliased Any — remove ``from-typing-import-any-as-alias`` "
        "from KNOWN_BYPASSES and update _known_bypasses.py."
    )


# ---------------------------------------------------------------------------
# AC-5.f lineno + snippet accuracy
# ---------------------------------------------------------------------------


def test_walker_returns_accurate_lineno_and_snippet() -> None:
    """AC-5.f: a planted ``y: Any = 2`` on line 2 returns ``Violation(line=2,
    kind="any-name", snippet="Any")``."""
    src = "x: int = 1\ny: Any = 2\n"
    violations = walk_any_annotations(src, path=Path("_lineno_test.py"))
    assert violations == [
        Violation(file=Path("_lineno_test.py"), line=2, kind="any-name", snippet="Any")
    ]


def test_walker_lineno_for_forward_ref() -> None:
    src = 'a: int = 1\nb: "dict[str, Any]" = {}\n'
    violations = walk_any_annotations(src, path=Path("_fr.py"))
    assert any(v.kind == "any-forward-ref" and v.line == 2 for v in violations)


# ---------------------------------------------------------------------------
# AC-5.e + AC-5.f extra: Violation dataclass is frozen, kind is closed Literal
# ---------------------------------------------------------------------------


def test_violation_is_frozen_dataclass() -> None:
    """Newtype-style typed primitive — kills primitive obsession on
    ``tuple[Path, int, str]`` (ADR-0010)."""
    import dataclasses

    v = Violation(file=Path("x"), line=1, kind="any-name", snippet="Any")
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.line = 2  # type: ignore[misc]
