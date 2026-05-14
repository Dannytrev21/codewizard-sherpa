"""Fixture-based parity test between the ``pyarn`` and hand-rolled
``_yarn.parse`` paths — Story S3-04, Gap 3.

Both invocations go through the public ``_yarn.parse(path)`` entrypoint
so the shared ``open_capped`` size-cap (S3-03 AC-3) and the
``_pyarn_parse`` adapter (S3-03 AC-13) are exercised on both sides. A
``monkeypatch.setattr(_yarn, "_HAS_PYARN", False)`` toggles the dispatch
mid-test; ``pyarn`` is never imported here directly.

When ``pyarn`` is not installed in this environment, the entire module is
skipped (per AC-2). The CI matrix must include at least one job with
``pyarn`` installed so the parity test exercises in CI.

Sources:

- ``docs/phases/01-context-gather-layer-a-node/stories/S3-04-yarn-parser-parity-oracle.md``
  §"Acceptance criteria" AC-1, AC-2.
- ``docs/phases/01-context-gather-layer-a-node/ADRs/0003-yarn-lock-parser-choice.md``
  §"Implementer's land-time selection".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.probes._lockfiles import _yarn

CORPUS_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "_yarn_corpus"
LOCKFILES = sorted(CORPUS_DIR.glob("*/yarn.lock"))

pytestmark = pytest.mark.skipif(
    not _yarn._HAS_PYARN,
    reason="pyarn not installed; parity test requires both parsers",
)


@pytest.mark.parametrize("lockfile", LOCKFILES, ids=lambda p: p.parent.name)
def test_pyarn_and_handrolled_paths_produce_identical_yarnlock(
    lockfile: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-1. Drive both parser paths through the public ``parse(path)``
    entrypoint; compare the two ``YarnLock`` dicts for direct equality.
    A drift between the two parsers ships a red CI on the corpus fixture
    that surfaces it.
    """
    pyarn_path_out = _yarn.parse(lockfile)
    monkeypatch.setattr(_yarn, "_HAS_PYARN", False)
    handrolled_out = _yarn.parse(lockfile)
    assert pyarn_path_out == handrolled_out
