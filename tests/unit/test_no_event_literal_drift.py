"""S1-10 AC-5 — pin the registry-pattern sweep against literal-drift.

After the sweep in commit #3 lifts the four call-site literals (parser cap,
two memo events, catalog load) to the single-source-of-truth registry in
``codegenie.logging``, no module under ``src/codegenie/`` other than
``logging.py`` may re-declare a string literal equal to one of those four
registered event-name values. ``probe.raw_artifact.truncated`` has no
current call-site; it lands as a constant in ``logging.py`` only and is
consumed in a later story.

The check is intentionally lightweight (``Path.rglob`` + substring match).
If false positives arise in Phase 2+, upgrade to an AST scan in S6-03's
adversarial sweep rather than weakening this test.
"""

from __future__ import annotations

from pathlib import Path

_REGISTERED_LITERALS: frozenset[str] = frozenset(
    {
        "probe.parser.cap_exceeded",
        "probe.memo.hit",
        "probe.memo.miss",
        "probe.catalog.load",
    }
)


def test_no_module_redeclares_a_registered_event_literal() -> None:
    root = Path("src/codegenie")
    offenders: list[tuple[str, str]] = []
    for py in root.rglob("*.py"):
        if py.name == "logging.py":
            continue
        text = py.read_text(encoding="utf-8")
        for lit in _REGISTERED_LITERALS:
            if f'"{lit}"' in text or f"'{lit}'" in text:
                offenders.append((str(py), lit))
    assert not offenders, (
        "registered event literals re-declared outside logging.py: " + repr(offenders)
    )
