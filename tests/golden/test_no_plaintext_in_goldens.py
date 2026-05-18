"""S7-03 AC-32 — defense-in-depth plaintext-leak guard.

Patterns are imported from ``codegenie.output.sanitizer._PATTERNS`` (the
production source of truth per ADR-0005). A new pattern added to that
table is automatically picked up here, so drift between the redactor and
this audit is a compile-time ``ImportError``, not a silent miss.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from codegenie.output.sanitizer import _PATTERNS

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN_ROOT = _REPO_ROOT / "tests" / "golden" / "probes"


def _golden_paths() -> list[Path]:
    return sorted(_GOLDEN_ROOT.rglob("*.json"))


@pytest.mark.parametrize(
    "pattern_class,pattern",
    [(cls, pat) for cls, pat in _PATTERNS],
    ids=[cls for cls, _ in _PATTERNS],
)
def test_no_plaintext_pattern_in_any_golden(pattern_class: str, pattern: re.Pattern[str]) -> None:
    """No production secret pattern matches any committed golden text."""
    offenders: list[str] = []
    for path in _golden_paths():
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(str(path.relative_to(_REPO_ROOT)))
    assert not offenders, (
        f"Plaintext {pattern_class!r} match found in goldens: {offenders}. "
        f"SecretRedactor failure mode? Plaintext must NEVER appear in "
        f"goldens (ADR-0005). Pattern: {pattern.pattern!r}."
    )
