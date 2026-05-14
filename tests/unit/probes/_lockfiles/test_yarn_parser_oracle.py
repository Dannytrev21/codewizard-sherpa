"""Property-based oracle for ``_yarn.parse`` — Story S3-04, Gap 3.

Invariants derived from the lockfile bytes (not from either parser's
implementation) so a coordinated drift across both parser paths ships a
red CI. Three invariants:

1. Anchored-name presence — every parser-emitted entry name must appear
   at a start-of-locator position in the lockfile bytes.
2. Version locality — every version string must appear within ±5 lines
   of the matching entry header.
3. Count parity — number of parsed entries equals the count of
   entry-header lines in the bytes.

The ``force_handrolled`` parametrize toggles ``_yarn._HAS_PYARN`` so both
parser paths are exercised on the same fixture under both states. The
``_check_invariant_*`` helpers live here; the self-check module
(``test_yarn_parser_oracle_self_check.py``) imports them so a single
source-of-truth defines each invariant (rule-of-two threshold per CLAUDE.md
"Simplicity first" — extract to ``_oracle_helpers.py`` only at a third
consumer).

Sources:

- ``docs/phases/01-context-gather-layer-a-node/stories/S3-04-yarn-parser-parity-oracle.md``
  §"Acceptance criteria" AC-3..AC-6 — invariant definitions.
- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Gap analysis" Gap 3 — two-direction validation rationale.
- ``docs/phases/01-context-gather-layer-a-node/ADRs/0003-yarn-lock-parser-choice.md``
  — the parity test is the contract enforcement.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.probes._lockfiles import _yarn
from codegenie.probes._lockfiles._yarn import YarnLock

CORPUS_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "_yarn_corpus"
LOCKFILES = sorted(CORPUS_DIR.glob("*/yarn.lock"))


def _entry_header_lines(body: str) -> list[str]:
    """Entry-header lines: column-0 start, end with ':', skip comments and
    the ``__metadata:`` block-header (yarn berry sentinel).
    """
    out: list[str] = []
    for raw in body.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#") or line.startswith(" "):
            continue
        if line == "__metadata:":
            continue
        if line.endswith(":"):
            out.append(line[:-1])
    return out


def _name_appears_anchored(name: str, body: str) -> bool:
    """Invariant 1 anchor: ``name`` must appear at a start-of-locator
    position so a parser that invents ``lodash`` against a body of
    ``lodash-es`` is caught.
    """
    return (
        f'"{name}@' in body
        or f", {name}@" in body
        or f"\n{name}@" in body
        or body.startswith(f"{name}@")
    )


def _check_invariant_1(result: YarnLock, body: str) -> None:
    for entry_key in result.get("entries", {}):
        for spec in entry_key.split(", "):
            name = spec.rsplit("@", 1)[0].strip('"')
            assert _name_appears_anchored(name, body), (
                f"parser invented entry {name!r} — not anchored in lockfile bytes"
            )


def _check_invariant_2(result: YarnLock, body: str) -> None:
    lines = body.splitlines()
    for entry_key, entry in result.get("entries", {}).items():
        version = entry.get("version")
        if not version:
            continue
        first_spec = entry_key.split(", ", 1)[0].strip('"')
        name = first_spec.rsplit("@", 1)[0]
        header_idx = next(
            (i for i, line in enumerate(lines) if name in line and line.rstrip().endswith(":")),
            None,
        )
        assert header_idx is not None, f"header for {name!r} not found"
        window = "\n".join(lines[max(0, header_idx - 5) : header_idx + 6])
        assert version in window, f"version {version!r} for {name!r} not within ±5 lines of header"


def _check_invariant_3(result: YarnLock, body: str) -> None:
    assert len(result.get("entries", {})) == len(_entry_header_lines(body)), (
        "entry count diverges from entry-header line count"
    )


@pytest.mark.parametrize("lockfile", LOCKFILES, ids=lambda p: p.parent.name)
@pytest.mark.parametrize("force_handrolled", [True, False])
def test_oracle_invariants_hold_on_corpus(
    lockfile: Path, force_handrolled: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-3..AC-6. Run all three invariants against every corpus fixture
    under both parser paths. ``force_handrolled=True`` monkeypatches
    ``_HAS_PYARN`` to ``False``; ``force_handrolled=False`` leaves it at
    its detected value so the ``_pyarn_parse`` adapter is exercised when
    pyarn is installed in this environment.
    """
    if force_handrolled:
        monkeypatch.setattr(_yarn, "_HAS_PYARN", False)
    body = lockfile.read_text()
    result = _yarn.parse(lockfile)
    _check_invariant_1(result, body)
    _check_invariant_2(result, body)
    _check_invariant_3(result, body)
