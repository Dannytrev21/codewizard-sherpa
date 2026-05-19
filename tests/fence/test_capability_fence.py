"""S4-05 AC-15 / AC-16 / AC-17 — capability-construction fence test.

Invokes :func:`codegenie._capability_fence.find_violations` against the
live ``src/codegenie/`` surface AND against synthesised fixtures under
``tmp_path``. Live + planted-positive walks call the **same** function so
a mutation that silently neuters the walker is killed by the planted
fixture.

Mirrors :mod:`tests.fence.test_no_any_in_plugin_surface`'s shape (S1-05
precedent).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenie._capability_fence import (
    _CAPABILITY_CLASS_NAMES,
    _CAPABILITY_FENCE_ROOTS,
    _MARKER_PATTERN,
    Violation,
    find_violations,
)

# ───────────────────────────────────────────────────────────────────────────
# AC-16 — live scan: zero violations across src/codegenie/.
# ───────────────────────────────────────────────────────────────────────────


def test_live_scan_finds_no_violations() -> None:
    """AC-16 — every ``*Capability(...)`` construction in
    ``src/codegenie/`` lives inside the single chokepoint
    :mod:`codegenie.plugins.capabilities`. A non-empty result fails with
    a message naming ``(file, line, class_name)`` per violation."""
    violations = find_violations()
    assert violations == [], "capability constructors found outside the chokepoint: " + "\n".join(
        f"  {v.file}:{v.line} — {v.class_name}" for v in violations
    )


# ───────────────────────────────────────────────────────────────────────────
# AC-16 — floor guard: every root exists and contains non-init modules.
# ───────────────────────────────────────────────────────────────────────────


def test_floor_guard_every_root_exists_and_non_empty() -> None:
    """AC-16 — a deletion of ``src/codegenie/`` would silently green
    the fence; this guard refuses to proceed if any root is missing or
    contains only ``__init__.py`` modules."""
    for root in _CAPABILITY_FENCE_ROOTS:
        assert root.is_dir(), (
            f"capability fence root {root} does not exist; if intentional, "
            f"amend _CAPABILITY_FENCE_ROOTS via ADR amendment"
        )
        non_init = [p for p in root.rglob("*.py") if p.name != "__init__.py"]
        assert non_init, (
            f"capability fence root {root} has only __init__.py modules; silent green refused"
        )


# ───────────────────────────────────────────────────────────────────────────
# AC-16 — planted positive: walker IS alive.
# ───────────────────────────────────────────────────────────────────────────


def test_planted_positive_detects_npm_capability(tmp_path: Path) -> None:
    """AC-16 — synthesised bad file is detected; structural fields match."""
    bad = tmp_path / "bad.py"
    bad.write_text(
        "from codegenie.plugins.capabilities import NpmInstallCapability\n"
        "x = NpmInstallCapability(registry='https://x', _minted_by='p')\n"
    )

    violations = find_violations(roots=[tmp_path])

    assert len(violations) == 1
    v = violations[0]
    assert v.class_name == "NpmInstallCapability"
    assert v.line == 2
    assert v.file == bad


@pytest.mark.parametrize("class_name", sorted(_CAPABILITY_CLASS_NAMES))
def test_per_class_planted_positive(class_name: str, tmp_path: Path) -> None:
    """AC-16 — every capability class is independently detectable. A
    mutant walker that catches ``NpmInstallCapability`` but silently
    drops ``GitLocalOpsCapability`` is killed by this parametrize."""
    bad = tmp_path / f"bad_{class_name}.py"
    bad.write_text(f"y = {class_name}()\n")

    violations = find_violations(roots=[tmp_path])

    class_violations = [v for v in violations if v.class_name == class_name]
    assert len(class_violations) == 1, (
        f"expected exactly one violation for {class_name}; got {violations!r}"
    )


def test_capability_bundle_is_not_in_fence_set() -> None:
    """AC-16 — :class:`CapabilityBundle` is the aggregator and is
    intentionally NOT fenced (it flows through arbitrary call sites)."""
    assert "CapabilityBundle" not in _CAPABILITY_CLASS_NAMES


# ───────────────────────────────────────────────────────────────────────────
# AC-16 — exclusions: chokepoint, tests/, marker.
# ───────────────────────────────────────────────────────────────────────────


def test_chokepoint_file_is_excluded(tmp_path: Path) -> None:
    """AC-16 — a synthesised file at the chokepoint path produces
    zero violations even if it contains a constructor call."""
    chokepoint = tmp_path / "src" / "codegenie" / "plugins" / "capabilities.py"
    chokepoint.parent.mkdir(parents=True)
    chokepoint.write_text("z = NpmInstallCapability()\n")

    violations = find_violations(roots=[tmp_path])

    assert violations == [], f"chokepoint file must be excluded; got: {violations!r}"


def test_tests_ancestor_segment_is_excluded(tmp_path: Path) -> None:
    """AC-16 — a synthesised file under a ``tests/`` ancestor segment
    produces zero violations (tests construct adversarial fixtures)."""
    fixture = tmp_path / "tests" / "fixtures" / "adversarial.py"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("z = NpmInstallCapability()\n")

    violations = find_violations(roots=[tmp_path])

    assert violations == [], f"tests/ ancestor must exclude; got: {violations!r}"


def test_inline_marker_excludes_file(tmp_path: Path) -> None:
    """AC-16 — the inline ``# fence: capability-allowed [P3-ADR-0011]``
    marker in the first 5 lines blanket-excludes the file."""
    bad = tmp_path / "marker.py"
    bad.write_text(
        f"{_MARKER_PATTERN}\n"
        "from codegenie.plugins.capabilities import NpmInstallCapability\n"
        "z = NpmInstallCapability(registry='https://x', _minted_by='p')\n"
    )

    violations = find_violations(roots=[tmp_path])

    assert violations == [], (
        f"file with marker in first 5 lines must be excluded; got: {violations!r}"
    )


# ───────────────────────────────────────────────────────────────────────────
# AC-17 — fence is collected by the default pytest run (this very test).
# ───────────────────────────────────────────────────────────────────────────


def test_violation_dataclass_is_frozen() -> None:
    """AC-15 — :class:`Violation` is frozen so callers can hash it and
    dedupe across walks (Phase-7 multi-root union semantics)."""
    v = Violation(file=Path("x.py"), line=1, class_name="X", snippet="X()")
    with pytest.raises(AttributeError):  # frozen dataclass attribute set
        v.line = 2  # type: ignore[misc]
    # Frozen dataclass instances are hashable; Phase-7 dedupe relies on it.
    assert hash(v) == hash(v)
