"""S5-04 AC-Codeowners-1 — codegenie-owned header + CODEOWNERS gating.

Binary pass/fail, no story-author judgment call: every policy YAML carries the
`codegenie-owned` header (the documented control of last resort), and when a
CODEOWNERS file exists both policy paths are listed in it.
"""

from __future__ import annotations

from pathlib import Path

from codegenie.transforms.policy.lockfile_policy import LOCKFILE_POLICY_PATH

_HEADER = "codegenie-owned"


def _codeowners_paths() -> list[Path]:
    return [p for p in (Path("CODEOWNERS"), Path(".github/CODEOWNERS")) if p.is_file()]


def test_policy_files_carry_codegenie_owned_header() -> None:
    for p in (LOCKFILE_POLICY_PATH, Path("tools/policy/lockfile-policy.yaml")):
        assert _HEADER in p.read_text(encoding="utf-8"), f"missing codegenie-owned header in {p}"


def test_codeowners_lists_both_policy_paths_when_present() -> None:
    files = _codeowners_paths()
    if not files:
        return  # other branch of AC-Codeowners-1 — header-only control
    expected = {
        "tools/policy/lockfile-policy.yaml",
        "src/codegenie/transforms/policy/lockfile-policy.yaml",
    }
    listed: set[str] = set()
    for cf in files:
        for line in cf.read_text(encoding="utf-8").splitlines():
            for path in expected:
                if path in line:
                    listed.add(path)
    assert listed == expected, f"CODEOWNERS missing {expected - listed}"
