"""S5-04 AC-Own-1 — the lockfile policy path is codegenie-owned, never cwd-relative.

A unit test (NOT a fence test — `tests/fence/` is reserved for AST-walking
structural defenses): proves `LOCKFILE_POLICY_PATH` resolves to the
wheel-shipped in-package file and is immune to a hostile `tools/policy/`
planted under the process cwd.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.transforms.policy.lockfile_policy import (
    LOCKFILE_POLICY_PATH,
    LockfilePolicy,
)


def test_path_is_a_real_file() -> None:
    assert LOCKFILE_POLICY_PATH.is_file()


def test_path_resolves_under_codegenie_package_root() -> None:
    s = str(LOCKFILE_POLICY_PATH.resolve())
    assert "codegenie/transforms/policy/lockfile-policy.yaml" in s


def test_path_immune_to_hostile_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hostile = tmp_path / "tools" / "policy"
    hostile.mkdir(parents=True)
    (hostile / "lockfile-policy.yaml").write_text(
        "schema_version: 1\nallowed_registries: [https://attacker.example.com/]\n"
    )
    monkeypatch.chdir(tmp_path)
    result = LockfilePolicy.from_yaml(LOCKFILE_POLICY_PATH)
    assert result.is_ok()
    hosts = {str(r) for r in result.unwrap().allowed_registries}
    assert not any("attacker.example.com" in h for h in hosts)
