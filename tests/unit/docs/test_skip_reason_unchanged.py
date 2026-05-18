"""S8-04 AC-9 — BLAKE3 freeze of ``test_phase3_handoff_smoke.py``.

The Phase-2 invariant: this story explicitly does NOT modify
``tests/adv/phase02/test_phase3_handoff_smoke.py``. The existing
``@pytest.mark.skip(reason=...)`` already cites ``ADR-0007`` +
``High-level-impl.md §Step 7`` (more durable than a GitHub issue number
that may move on repo migration). Phase 3's executor owns the unskip and
any reason-text update at the entry-gate review.

A future edit to the file triggers a loud test failure here, prompting an
ADR review before the change lands.
"""

from __future__ import annotations

from pathlib import Path

import blake3

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SMOKE_TEST = _REPO_ROOT / "tests" / "adv" / "phase02" / "test_phase3_handoff_smoke.py"

# Pinned at S8-04 land time. To intentionally change the file, regenerate
# this hash, attach an ADR amendment to 02-ADR-0006 / 02-ADR-0007, and
# update this constant in the same PR.
_EXPECTED_BLAKE3: str = "613f7f4e8102e2aa5f5ec0128c4da295191ac3ad5ca7ea8236a877979b886fc6"


def test_blake3_frozen() -> None:
    actual = blake3.blake3(_SMOKE_TEST.read_bytes()).hexdigest()
    if actual != _EXPECTED_BLAKE3:
        raise AssertionError(
            f"{_SMOKE_TEST} changed since S8-04 land time.\n"
            f"  expected: {_EXPECTED_BLAKE3}\n"
            f"  actual:   {actual}\n"
            "Phase 3 owns updates to this file (entry-gate review unskip per "
            "02-ADR-0007); any intentional change requires an ADR amendment to "
            "02-ADR-0006 / 02-ADR-0007 and a matching update to _EXPECTED_BLAKE3 "
            "in this test."
        )
