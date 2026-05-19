"""Phase-3 S2-04 AC-2 — the literal ``"universal--*--*"`` lives in
exactly one place per directory.

Scans every ``.py`` file under ``src/codegenie/`` and
``tests/fixtures/plugins/`` and asserts the literal substring
``"universal--*--*"`` appears only in:

- ``src/codegenie/plugins/resolver.py`` (the single source of truth)
- ``tests/fixtures/plugins/universal_fallback_fixture.py`` (the test
  fixture that imports and re-binds the constant)

Mutation M14: a future contributor inlines the literal into a
comparison (``if plugin.id == "universal--*--*":``) or a docstring;
the scan reports the file:line.
"""

from __future__ import annotations

from pathlib import Path

_LITERAL = "universal--*--*"

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC_DIR = _REPO_ROOT / "src" / "codegenie"
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures" / "plugins"

_PERMITTED = frozenset(
    {
        _SRC_DIR / "plugins" / "resolver.py",
        _FIXTURES_DIR / "universal_fallback_fixture.py",
    }
)


def _collect_py_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def test_universal_fallback_id_single_source_of_truth() -> None:
    files = _collect_py_files(_SRC_DIR) + _collect_py_files(_FIXTURES_DIR)
    offenders: list[tuple[Path, int]] = []
    for path in files:
        if path in _PERMITTED:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover — defensive
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if _LITERAL in line:
                offenders.append((path, i))
    assert not offenders, (
        "literal 'universal--*--*' appears outside the single-source files "
        "(import UNIVERSAL_FALLBACK_ID instead): " + ", ".join(f"{p}:{ln}" for p, ln in offenders)
    )
