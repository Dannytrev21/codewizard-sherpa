"""S5-04 AC-File-2 — the repo-root mirror is byte-for-byte equal to the shipped copy.

`tools/policy/lockfile-policy.yaml` is the human-review surface; the in-package
copy is the runtime-loaded one. They must never drift.
"""

from __future__ import annotations

from pathlib import Path

from codegenie.transforms.policy.lockfile_policy import LOCKFILE_POLICY_PATH


def test_repo_root_mirror_byte_for_byte_equal_to_shipped() -> None:
    mirror = Path("tools/policy/lockfile-policy.yaml").resolve()
    assert mirror.is_file(), "canonical mirror missing — see Files-to-touch"
    assert mirror.read_bytes() == LOCKFILE_POLICY_PATH.read_bytes(), (
        "tools/policy/lockfile-policy.yaml drifted from "
        "src/codegenie/transforms/policy/lockfile-policy.yaml; the mirror is the "
        "human-review surface but the in-package copy is loaded at runtime — "
        "keep them equal."
    )
