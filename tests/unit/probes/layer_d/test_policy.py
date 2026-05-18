"""Unit tests for ``PolicyProbe`` (S6-03)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from codegenie.probes.layer_d import policy as pol

from .conftest import _make_context, _make_repo


def _make_user_home(tmp_path: Path) -> Path:
    home = tmp_path / "user_home"
    (home / ".codegenie").mkdir(parents=True)
    return home


def test_policy_happy_path_emits_declared_repos(tmp_path: Path) -> None:
    """AC-8. Mutation caught: not projecting the ``policy_repos`` field."""
    repo = _make_repo(tmp_path)
    home = _make_user_home(tmp_path)
    target = tmp_path / "existing-policy-repo"
    target.mkdir()
    (home / ".codegenie" / "config.yaml").write_text(
        "policy_repos:\n"
        f"  - path: {target}\n    type: git\n"
        f"  - path: /nonexistent/policy/repo\n    type: git\n"
    )
    ctx = _make_context(tmp_path, config_overrides={"policy.user_home": str(home)})
    output = asyncio.run(pol.PolicyProbe().run(repo, ctx))
    assert output.confidence == "high"
    slice_ = pol.PolicySlice.model_validate(output.schema_slice)
    by_path = {r.path: r for r in slice_.policy_repos}
    assert by_path[str(target)].exists_on_disk is True
    assert by_path["/nonexistent/policy/repo"].exists_on_disk is False
    assert all(r.type == "git" for r in slice_.policy_repos)


def test_policy_config_absent_low(tmp_path: Path) -> None:
    """AC-10. Mutation caught: any raise on missing user config."""
    repo = _make_repo(tmp_path)
    home = tmp_path / "empty_home"
    home.mkdir()
    ctx = _make_context(tmp_path, config_overrides={"policy.user_home": str(home)})
    output = asyncio.run(pol.PolicyProbe().run(repo, ctx))
    assert output.confidence == "low"
    slice_ = pol.PolicySlice.model_validate(output.schema_slice)
    assert slice_.policy_repos == ()
    assert "policy_config_absent" in slice_.per_file_errors


def test_policy_malformed_yaml_low(tmp_path: Path) -> None:
    """AC-17. Mutation caught: leaking ``MalformedYAMLError`` past the probe."""
    repo = _make_repo(tmp_path)
    home = _make_user_home(tmp_path)
    (home / ".codegenie" / "config.yaml").write_text("- bare\n- list\n")
    ctx = _make_context(tmp_path, config_overrides={"policy.user_home": str(home)})
    output = asyncio.run(pol.PolicyProbe().run(repo, ctx))
    assert output.confidence == "low"
    slice_ = pol.PolicySlice.model_validate(output.schema_slice)
    assert slice_.policy_repos == ()
    assert "policy_config_malformed" in slice_.per_file_errors


def test_policy_field_not_a_list_recorded(tmp_path: Path) -> None:
    """AC-17. Mutation caught: silently coercing non-list ``policy_repos``."""
    repo = _make_repo(tmp_path)
    home = _make_user_home(tmp_path)
    (home / ".codegenie" / "config.yaml").write_text("policy_repos: 'string-not-list'\n")
    ctx = _make_context(tmp_path, config_overrides={"policy.user_home": str(home)})
    output = asyncio.run(pol.PolicyProbe().run(repo, ctx))
    slice_ = pol.PolicySlice.model_validate(output.schema_slice)
    assert "policy_repos_not_list" in slice_.per_file_errors
    assert slice_.policy_repos == ()


def test_policy_empty_config_high_confidence(tmp_path: Path) -> None:
    """AC-16. Mutation caught: emitting medium when ``policy_repos`` is
    legitimately absent but the config file parses cleanly."""
    repo = _make_repo(tmp_path)
    home = _make_user_home(tmp_path)
    (home / ".codegenie" / "config.yaml").write_text("other_key: value\n")
    ctx = _make_context(tmp_path, config_overrides={"policy.user_home": str(home)})
    output = asyncio.run(pol.PolicyProbe().run(repo, ctx))
    assert output.confidence == "high"
    slice_ = pol.PolicySlice.model_validate(output.schema_slice)
    assert slice_.policy_repos == ()


def test_policy_two_runs_byte_identical(tmp_path: Path) -> None:
    """AC-15."""
    repo = _make_repo(tmp_path)
    home = _make_user_home(tmp_path)
    (home / ".codegenie" / "config.yaml").write_text(
        "policy_repos:\n  - path: /b\n    type: git\n  - path: /a\n    type: git\n"
    )
    ctx = _make_context(tmp_path, config_overrides={"policy.user_home": str(home)})
    s1 = pol.PolicySlice.model_validate(asyncio.run(pol.PolicyProbe().run(repo, ctx)).schema_slice)
    s2 = pol.PolicySlice.model_validate(asyncio.run(pol.PolicyProbe().run(repo, ctx)).schema_slice)
    assert s1.model_dump_json() == s2.model_dump_json()
    assert [r.path for r in s1.policy_repos] == ["/a", "/b"]
