"""S7-11 AC-1/AC-2/AC-3 — cassette-set presence + sanitizer-shape acceptance.

Loud-skips when the cassettes don't exist yet (operator hasn't run
the recording session); unskips automatically once the operator runs
`make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1`. This shape
is the "extend, don't fail on absent" pattern S7-10's real-plugin
test established (S7-10 AC-7).
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parents[2]
_CASSETTES_ROOT = _REPO_ROOT / "tests" / "cassettes" / "anthropic"


@pytest.mark.parametrize(
    ("subdir", "story_id", "ac_id"),
    [
        ("s6_07_determinism", "S6-07", "AC-1"),
        ("s7_06_e2e_breaking_change", "S7-06", "AC-2"),
        ("s7_07_e2e_replay_lands_rag", "S7-07", "AC-3"),
    ],
)
def test_cassette_set_present_or_loudly_skips(subdir: str, story_id: str, ac_id: str) -> None:
    """For each of S6-07/S7-06/S7-07: cassettes exist under the story-
    specific subdir AND at least one .yaml is present. Loud-skip when
    absent so a fresh master doesn't fail; runs unconditionally once
    the operator records.
    """
    cassettes_dir = _CASSETTES_ROOT / subdir
    if not cassettes_dir.exists():
        pytest.skip(
            f"S7-11 {ac_id}: {story_id} cassettes not recorded yet at "
            f"{cassettes_dir}. Operator path: read "
            f"docs/phases/04-vuln-llm-fallback-rag/stories/S7-11-cassette-"
            f"authorization-bridge.md, then run "
            f"`make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1`."
        )
    cassettes = list(cassettes_dir.glob("*.yaml"))
    assert cassettes, (
        f"S7-11 {ac_id}: {cassettes_dir} exists but contains no .yaml cassettes. "
        f"Either re-run `make refresh-cassettes` to populate, or remove the "
        f"empty directory if the recording session was aborted."
    )


def test_cassettes_lock_covers_all_recorded_cassettes_or_skips() -> None:
    """AC-4 — every recorded cassette MUST appear in cassettes.lock so
    S3-05's CI scanner verifies BLAKE3 sums on the next CI run.

    Loud-skips when no story-specific cassettes are recorded yet.
    """
    story_dirs = [
        _CASSETTES_ROOT / "s6_07_determinism",
        _CASSETTES_ROOT / "s7_06_e2e_breaking_change",
        _CASSETTES_ROOT / "s7_07_e2e_replay_lands_rag",
    ]
    recorded = [cassette for d in story_dirs if d.exists() for cassette in d.glob("*.yaml")]
    if not recorded:
        pytest.skip(
            "No S6-07/S7-06/S7-07 cassettes recorded yet — AC-4 unreachable. "
            "See S7-11 story for operator workflow."
        )
    lock_path = _CASSETTES_ROOT / "cassettes.lock"
    assert lock_path.exists()
    lock_body = lock_path.read_text()
    missing = [c for c in recorded if c.name not in lock_body]
    assert not missing, (
        f"S7-11 AC-4: cassettes recorded but cassettes.lock not refreshed. "
        f"Missing entries for: {[c.name for c in missing]}. "
        f"Run `make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1` to "
        f"recompute the BLAKE3 sums + append to the lock."
    )
