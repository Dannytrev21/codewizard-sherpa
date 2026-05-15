"""Red tests for S2-02 — ``NodeBuildSystemProbe``.

Pins AC-1..AC-22 from
``docs/phases/01-context-gather-layer-a-node/stories/S2-02-node-build-system-probe.md``.

Helpers are defined inline (matches the S2-01 idiom).

**Deviation from the story's literal test code:** ``codegenie.exec.run_allowlisted``
is an ``async def`` in this codebase (see ``src/codegenie/exec.py:175``). The
story's stub uses a sync lambda returning ``SimpleNamespace`` which would fail
``await``. The stubs here are ``async def`` returning the same ``ProcessResult``-
shaped object so the seam contract is preserved (AC-12 / T-15 intent: monkeypatch
``codegenie.exec.run_allowlisted`` and assert the probe routes through it).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import types
from pathlib import Path
from typing import Any

import pytest

from codegenie.probes.base import ProbeContext, ProbeOutput, RepoSnapshot

ADR_0007 = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


# ---------- helpers ----------------------------------------------------------


def _stub_exec_returning(
    monkeypatch: pytest.MonkeyPatch,
    stdout: bytes,
    returncode: int = 0,
) -> list[list[str]]:
    """Install an async stub at ``codegenie.exec.run_allowlisted``.

    Returns a list that records every ``argv`` the probe passed through — the
    list lives across the call so T-15 can assert the routing.
    """
    import codegenie.exec

    calls: list[list[str]] = []

    async def _stub(argv: list[str], **kw: Any) -> Any:
        calls.append(list(argv))
        return types.SimpleNamespace(stdout=stdout, returncode=returncode, stderr=b"")

    monkeypatch.setattr(codegenie.exec, "run_allowlisted", _stub)
    return calls


def _stub_exec_raising(monkeypatch: pytest.MonkeyPatch, exc: BaseException) -> None:
    import codegenie.exec

    async def _raise(*a: Any, **kw: Any) -> Any:
        raise exc

    monkeypatch.setattr(codegenie.exec, "run_allowlisted", _raise)


def _snapshot(root: Path) -> RepoSnapshot:
    return RepoSnapshot(
        root=root,
        git_commit=None,
        detected_languages={"typescript": 1},
        config={},
    )


def _ctx(root: Path, parsed_manifest: Any = None) -> ProbeContext:
    return ProbeContext(
        cache_dir=root / ".cache",
        output_dir=root / ".out",
        workspace=root,
        logger=logging.getLogger("test"),
        config={},
        parsed_manifest=parsed_manifest,
    )


def _run_probe(root: Path, parsed_manifest: Any = None) -> ProbeOutput:
    # By default, stub `run_allowlisted` to raise FileNotFoundError so tests that
    # don't care about the version-cross-check don't depend on a real `node`
    # binary on $PATH (CI hosts may not have one).
    from codegenie.probes.node_build_system import NodeBuildSystemProbe

    return asyncio.run(NodeBuildSystemProbe().run(_snapshot(root), _ctx(root, parsed_manifest)))


def _minimal_envelope_with_node_build_system(
    *, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    slice_payload: dict[str, Any] = {
        "package_manager": "npm",
        "package_manager_version": None,
        "additional_lockfiles": [],
        "commands": {},
        "bundler": None,
        "typescript": None,
        "node_version_pinned": None,
        "node_version_constraint": None,
        "node_version_resolved_locally": None,
        "output_artifacts": [],
        "warnings": [],
    }
    if extra:
        slice_payload.update(extra)
    return {
        "schema_version": "0.1.0",
        "generated_at": "2026-05-14T00:00:00Z",
        "repo": {"root": "/x", "git_commit": None},
        "probes": {"node_build_system": {"build_system": slice_payload}},
    }


def _no_node_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make sure `node --version` is silent regardless of host PATH."""
    import codegenie.exec
    from codegenie.errors import ToolMissingError

    async def _raise(*a: Any, **kw: Any) -> Any:
        raise ToolMissingError("node not installed (test default)")

    monkeypatch.setattr(codegenie.exec, "run_allowlisted", _raise)


@pytest.fixture(autouse=True)
def _silence_node_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default to a no-node-on-PATH posture for every test in this module.

    Individual tests override by calling ``_stub_exec_returning`` /
    ``_stub_exec_raising`` AFTER the fixture has installed the silent default —
    `monkeypatch.setattr` on the same attribute replaces it.
    """
    _no_node_on_path(monkeypatch)


# ---------- AC-1: probe contract attributes ---------------------------------


def test_probe_contract_attributes_match_arch_design() -> None:
    """T-9. AC-1. Drift in any class attribute breaks Wave-1 ordering / cache keys."""
    from codegenie.probes.node_build_system import NodeBuildSystemProbe as P

    assert P.name == "node_build_system"
    assert P.version == "0.1.0"
    assert P.layer == "A"
    assert P.tier == "task_specific"
    assert P.applies_to_languages == ["javascript", "typescript"]  # list, not tuple
    assert P.applies_to_tasks == ["*"]
    assert P.requires == ["language_detection"]
    assert P.timeout_seconds == 30
    assert len(P.declared_inputs) == 14
    for expected in (
        "package.json",
        "pnpm-workspace.yaml",
        "lerna.json",
        "nx.json",
        "turbo.json",
        ".nvmrc",
        ".node-version",
        ".tool-versions",
        "tsconfig.json",
        "tsconfig.*.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "bun.lockb",
    ):
        assert expected in P.declared_inputs, f"missing: {expected}"


# ---------- AC-2 / AC-19: lockfile precedence -------------------------------


@pytest.mark.parametrize(
    "present,expected_pm,expected_runners,expect_warn",
    [
        (
            {"bun.lockb", "pnpm-lock.yaml", "yarn.lock", "package-lock.json"},
            "bun",
            ["pnpm-lock.yaml", "yarn.lock", "package-lock.json"],
            True,
        ),
        (
            {"pnpm-lock.yaml", "yarn.lock", "package-lock.json"},
            "pnpm",
            ["yarn.lock", "package-lock.json"],
            True,
        ),
        # Per ADR-0013 (S2-02a): a bare ``yarn.lock`` with no Berry markers
        # resolves to ``yarn-classic`` via the safe-default path.
        ({"yarn.lock", "package-lock.json"}, "yarn-classic", ["package-lock.json"], True),
        ({"package-lock.json"}, "npm", [], False),
        ({"bun.lockb", "package-lock.json"}, "bun", ["package-lock.json"], True),
    ],
)
def test_lockfile_precedence_total_ordering(
    tmp_path: Path,
    present: set[str],
    expected_pm: str,
    expected_runners: list[str],
    expect_warn: bool,
) -> None:
    """T-1. AC-2 + AC-19. Runners-up ordered by PRECEDENCE, not alpha."""
    (tmp_path / "package.json").write_text("{}")
    for f in present:
        (tmp_path / f).write_text("x")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == expected_pm
    assert s["additional_lockfiles"] == expected_runners
    assert ("package_manager.multi_lockfile" in s["warnings"]) is expect_warn


def test_lockfile_precedence_tuple_order_locked() -> None:
    """T-1b. AC-2 ordering invariant: the module constant must not drift."""
    from codegenie.probes.node_build_system import _LOCKFILE_PRECEDENCE

    assert _LOCKFILE_PRECEDENCE == (
        ("bun.lockb", "bun"),
        ("pnpm-lock.yaml", "pnpm"),
        ("yarn.lock", "yarn"),
        ("package-lock.json", "npm"),
    )


# ---------- AC-3 / AC-18: scripts -------------------------------------------


def test_scripts_recorded_verbatim_and_never_evaluated(tmp_path: Path) -> None:
    """T-2. AC-3."""
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest", "build": "rm -rf dist && tsc"}})
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '6.0'")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["commands"] == {"test": "vitest", "build": "rm -rf dist && tsc"}


@pytest.mark.parametrize(
    "pkg_body,expected",
    [
        ({}, {}),
        ({"scripts": None}, {}),
        ({"scripts": {}}, {}),
        ({"scripts": {"x": "ok", "y": 42}}, {"x": "ok"}),
        ({"scripts": {"x": "ok", "y": ["array"]}}, {"x": "ok"}),
    ],
)
def test_scripts_edge_cases(
    tmp_path: Path, pkg_body: dict[str, Any], expected: dict[str, str]
) -> None:
    """T-11. AC-18."""
    (tmp_path / "package.json").write_text(json.dumps(pkg_body))
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["commands"] == expected


# ---------- AC-4a / AC-4b: tsconfig extends ---------------------------------


def test_extends_depth_4_ok_depth_5_warns(tmp_path: Path) -> None:
    """T-10. AC-4a — off-by-one mutation passes cycle test but fails this one."""
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "tsconfig.json").write_text('{"extends":"./a.json"}')
    (tmp_path / "a.json").write_text('{"extends":"./b.json"}')
    (tmp_path / "b.json").write_text('{"extends":"./c.json"}')
    (tmp_path / "c.json").write_text('{"extends":"./d.json"}')
    (tmp_path / "d.json").write_text('{"compilerOptions":{"strict":true}}')
    s_ok = _run_probe(tmp_path).schema_slice["build_system"]
    assert "tsconfig.extends_depth_exceeded" not in s_ok["warnings"]
    (tmp_path / "d.json").write_text('{"extends":"./e.json"}')
    (tmp_path / "e.json").write_text("{}")
    s_bad = _run_probe(tmp_path).schema_slice["build_system"]
    assert "tsconfig.extends_depth_exceeded" in s_bad["warnings"]
    assert "tsconfig.extends_cycle" not in s_bad["warnings"]


@pytest.mark.parametrize(
    "files",
    [
        {"tsconfig.json": '{"extends":"./tsconfig.json"}'},
        {
            "tsconfig.json": '{"extends":"./a.json"}',
            "a.json": '{"extends":"tsconfig.json"}',
        },
        {
            "tsconfig.json": '{"extends":"./a.json"}',
            "a.json": '{"extends":"./b.json"}',
            "b.json": '{"extends":"./tsconfig.json"}',
        },
    ],
)
def test_tsconfig_extends_cycles_detected(tmp_path: Path, files: dict[str, str]) -> None:
    """T-3. AC-4b. `./a.json` and `a.json` MUST resolve to the same absolute path."""
    (tmp_path / "package.json").write_text("{}")
    for n, b in files.items():
        (tmp_path / n).write_text(b)
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert "tsconfig.extends_cycle" in s["warnings"]
    assert "tsconfig.extends_depth_exceeded" not in s["warnings"]


# ---------- AC-5 / AC-17: node version sources + routing --------------------


@pytest.mark.parametrize(
    "files,pinned,constraint",
    [
        (
            {
                ".nvmrc": "v18.17.0",
                ".node-version": "v20.0.0",
                ".tool-versions": "node 21.0.0\n",
            },
            "v18.17.0",
            None,
        ),
        (
            {".node-version": "v20.0.0", ".tool-versions": "node 21.0.0\n"},
            "v20.0.0",
            None,
        ),
        ({".tool-versions": "python 3.11\nnode 21.0.0\n"}, "21.0.0", None),
        ({}, None, None),
        ({".nvmrc": "v18.17.0"}, "v18.17.0", ">=20.0.0"),
    ],
)
def test_node_version_precedence(
    tmp_path: Path, files: dict[str, str], pinned: str | None, constraint: str | None
) -> None:
    """T-4. AC-5 + AC-17. engines.node ROUTES to node_version_constraint."""
    pkg = {"engines": {"node": constraint}} if constraint else {}
    (tmp_path / "package.json").write_text(json.dumps(pkg))
    for n, b in files.items():
        (tmp_path / n).write_text(b)
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["node_version_pinned"] == pinned
    assert s["node_version_constraint"] == constraint


# ---------- AC-6a: success ---------------------------------------------------


def test_node_version_success_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """T-5a. AC-6a — clean `vX.Y.Z` stdout lands in resolved_locally; high confidence."""
    _stub_exec_returning(monkeypatch, b"v20.10.0\n")
    (tmp_path / "package.json").write_text("{}")
    out = _run_probe(tmp_path)
    s = out.schema_slice["build_system"]
    assert s["node_version_resolved_locally"] == "v20.10.0"
    assert out.confidence == "high"
    assert out.errors == []


# ---------- AC-6b: hostile shim ---------------------------------------------


def test_node_version_hostile_shim_warns_but_stays_high(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """T-5. AC-6b + AC-11. Every emitted ID matches ADR-0007."""
    _stub_exec_returning(monkeypatch, b"x\x00")
    (tmp_path / "package.json").write_text("{}")
    out = _run_probe(tmp_path)
    s = out.schema_slice["build_system"]
    assert s["node_version_resolved_locally"] is None
    assert "node.version_unparseable" in s["warnings"]
    for w in s["warnings"]:
        assert ADR_0007.match(w), f"warning ID violates ADR-0007: {w!r}"
    assert out.confidence == "high"
    assert out.errors == []


# ---------- AC-6c: absent / timeout / exec-error ----------------------------


def test_node_version_filenotfound_silently_skipped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """T-6a. AC-6c — FileNotFoundError is silent."""
    _stub_exec_raising(monkeypatch, FileNotFoundError())
    (tmp_path / "package.json").write_text("{}")
    out = _run_probe(tmp_path)
    s = out.schema_slice["build_system"]
    assert s["node_version_resolved_locally"] is None
    assert all(not w.startswith("node.") for w in s["warnings"])
    assert out.errors == []
    assert out.confidence == "high"


def test_node_version_tool_missing_silently_skipped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """T-6b. AC-6c — ToolMissingError (binary absent on PATH) is silent."""
    from codegenie.errors import ToolMissingError

    _stub_exec_raising(monkeypatch, ToolMissingError("node missing"))
    (tmp_path / "package.json").write_text("{}")
    out = _run_probe(tmp_path)
    s = out.schema_slice["build_system"]
    assert s["node_version_resolved_locally"] is None
    assert all(not w.startswith("node.") for w in s["warnings"])
    assert out.errors == []
    assert out.confidence == "high"


def test_node_version_timeout_silently_skipped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """T-6c. AC-6c — ProbeTimeoutError is silent."""
    from codegenie.errors import ProbeTimeoutError

    _stub_exec_raising(monkeypatch, ProbeTimeoutError("node timed out"))
    (tmp_path / "package.json").write_text("{}")
    out = _run_probe(tmp_path)
    s = out.schema_slice["build_system"]
    assert s["node_version_resolved_locally"] is None
    assert all(not w.startswith("node.") for w in s["warnings"])
    assert out.errors == []
    assert out.confidence == "high"


def test_node_version_nonzero_exit_silently_skipped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """T-6d. AC-6c — non-zero returncode (exec-error) is silent."""
    _stub_exec_returning(monkeypatch, b"node: command failed\n", returncode=127)
    (tmp_path / "package.json").write_text("{}")
    out = _run_probe(tmp_path)
    s = out.schema_slice["build_system"]
    assert s["node_version_resolved_locally"] is None
    assert all(not w.startswith("node.") for w in s["warnings"])
    assert out.errors == []
    assert out.confidence == "high"


# ---------- AC-7: declared-vs-resolved disagreement ------------------------


def test_version_declared_resolved_disagree_warns_high_confidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """T-13. AC-7 disagree case."""
    _stub_exec_returning(monkeypatch, b"v20.10.0\n")
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / ".nvmrc").write_text("v18.17.0")
    out = _run_probe(tmp_path)
    s = out.schema_slice["build_system"]
    assert s["node_version_resolved_locally"] == "v20.10.0"
    assert s["node_version_pinned"] == "v18.17.0"
    assert "node.version_declared_resolved_disagree" in s["warnings"]
    assert out.confidence == "high"


def test_version_declared_resolved_agree_emits_no_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """T-14a. AC-7 agreement case — no false alarm."""
    _stub_exec_returning(monkeypatch, b"v20.10.0\n")
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / ".nvmrc").write_text("v20.10.0")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert "node.version_declared_resolved_disagree" not in s["warnings"]


def test_version_disagree_silently_skipped_when_unparseable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """T-14b. AC-7 silent-skip — `.nvmrc` `lts/hydrogen` is not semver."""
    _stub_exec_returning(monkeypatch, b"v20.10.0\n")
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / ".nvmrc").write_text("lts/hydrogen")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert "node.version_declared_resolved_disagree" not in s["warnings"]


# ---------- AC-8: packageManager declaration --------------------------------


def test_package_manager_declaration_disagreement(tmp_path: Path) -> None:
    """T-7a. AC-8 disagree case (lockfile wins)."""
    (tmp_path / "package.json").write_text('{"packageManager": "yarn@3.0.0"}')
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '6.0'")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "pnpm"
    assert "package_manager.declaration_lockfile_disagree" in s["warnings"]


def test_package_manager_declaration_agreement(tmp_path: Path) -> None:
    """T-7b. AC-8 agreement case — no warning."""
    (tmp_path / "package.json").write_text('{"packageManager": "pnpm@8.6.0"}')
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '6.0'")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager"] == "pnpm"
    assert "package_manager.declaration_lockfile_disagree" not in s["warnings"]


# ---------- AC-9: bundler ----------------------------------------------------


@pytest.mark.parametrize(
    "deps_order",
    [
        ["webpack", "rollup"],
        ["rollup", "webpack"],
        ["vite", "esbuild", "webpack"],
    ],
)
def test_bundler_deterministic_alpha_first_hit(tmp_path: Path, deps_order: list[str]) -> None:
    """T-12. AC-9 — alpha-sorted via `_BUNDLERS_SORTED`."""
    deps = {n: "^1.0.0" for n in deps_order}
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": deps}))
    bundler = _run_probe(tmp_path).schema_slice["build_system"]["bundler"]
    candidates = {"esbuild", "parcel", "rollup", "turbopack", "vite", "webpack"}
    expected = sorted(d for d in deps_order if d in candidates)[0]
    assert bundler == expected


def test_bundler_none_when_no_bundler_dep(tmp_path: Path) -> None:
    """T-12b. AC-9 — null case."""
    (tmp_path / "package.json").write_text('{"dependencies":{"lodash":"^4"}}')
    assert _run_probe(tmp_path).schema_slice["build_system"]["bundler"] is None


# ---------- AC-12: env-strip seam (load-bearing) -----------------------------


def test_env_strip_seam_routes_through_run_allowlisted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """T-15. AC-12. Probe MUST go through codegenie.exec.run_allowlisted."""
    import codegenie.exec

    calls: list[list[str]] = []

    async def sentinel(argv: list[str], **kw: Any) -> Any:
        calls.append(list(argv))
        return types.SimpleNamespace(stdout=b"v20.10.0\n", returncode=0, stderr=b"")

    monkeypatch.setattr(codegenie.exec, "run_allowlisted", sentinel)
    (tmp_path / "package.json").write_text("{}")
    _run_probe(tmp_path)
    assert calls, "probe bypassed codegenie.exec.run_allowlisted"
    assert calls[0][:2] == ["node", "--version"]


# ---------- AC-13: memo branch ----------------------------------------------


def test_package_json_read_via_memo_when_present(tmp_path: Path) -> None:
    """T-17. AC-13 memo branch. Counting wrapper proves call_count == 1."""
    calls: list[Path] = []

    def memo(path: Path) -> dict[str, Any]:
        calls.append(path)
        return {"scripts": {"test": "vitest"}}

    (tmp_path / "package.json").write_text("garbage-but-memo-wins")
    out = _run_probe(tmp_path, parsed_manifest=memo)
    assert len(calls) == 1
    assert calls[0].name == "package.json"
    assert out.schema_slice["build_system"]["commands"] == {"test": "vitest"}


def test_package_json_read_via_safe_json_when_memo_none(tmp_path: Path) -> None:
    """T-18. AC-13 fallback branch (`ctx.parsed_manifest is None`)."""
    (tmp_path / "package.json").write_text('{"scripts":{"test":"vitest"}}')
    out = _run_probe(tmp_path)
    assert out.schema_slice["build_system"]["commands"] == {"test": "vitest"}


# ---------- AC-14: typed-exception → errors[] ------------------------------


def test_package_json_size_cap_lands_in_errors(tmp_path: Path) -> None:
    """T-16a. AC-14."""
    big = "x" * (5 * 1024 * 1024 + 16)
    (tmp_path / "package.json").write_text(big)
    out = _run_probe(tmp_path)
    assert "package_json.size_cap_exceeded" in out.errors
    assert out.confidence == "low"
    assert "build_system" in out.schema_slice


def test_package_json_malformed_lands_in_errors(tmp_path: Path) -> None:
    """T-16b. AC-14."""
    (tmp_path / "package.json").write_text('{"scripts":{"test":"vitest"')
    out = _run_probe(tmp_path)
    assert "package_json.malformed" in out.errors
    assert out.confidence == "low"


def test_package_json_symlink_refused_lands_in_errors(tmp_path: Path) -> None:
    """T-16c. AC-14 — symlink target's content must NOT leak."""
    outside = tmp_path.parent / "evil.json"
    outside.write_text('{"scripts": {"test": "rm -rf /"}}')
    (tmp_path / "package.json").symlink_to(outside)
    out = _run_probe(tmp_path)
    assert "package_json.symlink_refused" in out.errors
    assert out.confidence == "low"
    assert out.schema_slice["build_system"].get("commands", {}) == {}


# ---------- AC-15: output_artifacts -----------------------------------------


@pytest.mark.parametrize(
    "pkg_body,expected",
    [
        ({"files": ["dist/**", "README.md"]}, ["dist/**", "README.md"]),
        ({}, []),
        ({"files": None}, []),
        ({"files": {}}, []),
        ({"files": [1, "ok"]}, []),
    ],
)
def test_output_artifacts_from_package_json_files(
    tmp_path: Path, pkg_body: dict[str, Any], expected: list[str]
) -> None:
    """T-21. AC-15."""
    (tmp_path / "package.json").write_text(json.dumps(pkg_body))
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["output_artifacts"] == expected


# ---------- AC-16: package_manager_version is null in Phase 1 ---------------


def test_package_manager_version_is_null_in_phase_1(tmp_path: Path) -> None:
    """T-22. AC-16."""
    (tmp_path / "package.json").write_text('{"packageManager": "pnpm@8.6.0"}')
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '6.0'")
    s = _run_probe(tmp_path).schema_slice["build_system"]
    assert s["package_manager_version"] is None


# ---------- AC-20: registry membership + filter -----------------------------


def test_registry_membership_and_for_task_filter() -> None:
    """T-23. AC-20."""
    from codegenie.probes import default_registry
    from codegenie.probes.node_build_system import NodeBuildSystemProbe

    assert NodeBuildSystemProbe in default_registry.all_probes()
    for langs in [
        frozenset({"javascript"}),
        frozenset({"typescript"}),
        frozenset({"javascript", "typescript"}),
    ]:
        assert NodeBuildSystemProbe in default_registry.for_task("*", langs)
    assert NodeBuildSystemProbe not in default_registry.for_task("*", frozenset({"go"}))


# ---------- AC-21: sub-schema rejects extra field --------------------------


def test_sub_schema_rejects_extra_field_under_node_build_system() -> None:
    """T-24. AC-21."""
    from codegenie.errors import SchemaValidationError
    from codegenie.schema.validator import validate

    envelope = _minimal_envelope_with_node_build_system(extra={"rogue_field": True})
    with pytest.raises(SchemaValidationError) as excinfo:
        validate(envelope)
    msg = str(excinfo.value)
    assert "probes.node_build_system" in msg
    assert "rogue_field" in msg


# ---------- AC-11: warning + error ID frozenset invariant ------------------


def test_warning_and_error_ids_match_adr_0007() -> None:
    """T-25. AC-11."""
    from codegenie.probes import node_build_system as nbs

    assert nbs._WARNING_IDS, "module-level warning IDs frozenset missing"
    assert nbs._ERROR_IDS, "module-level error IDs frozenset missing"
    for i in (*nbs._WARNING_IDS, *nbs._ERROR_IDS):
        assert ADR_0007.match(i), f"violates ADR-0007: {i!r}"


# ---------- cross-cutting: determinism --------------------------------------


def test_two_runs_byte_equal(tmp_path: Path) -> None:
    """T-26. Reproducibility (production/design.md 'deterministic end-to-end')."""
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {"test": "vitest", "build": "tsc"},
                "dependencies": {"vite": "^5", "rollup": "^4", "express": "^4"},
            }
        )
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '6.0'")
    (tmp_path / "package-lock.json").write_text("{}")
    a = _run_probe(tmp_path).schema_slice
    b = _run_probe(tmp_path).schema_slice
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ---------- structlog parser_kind anchor ------------------------------------


def test_parser_kind_field_emitted_on_tsconfig_parse(tmp_path: Path) -> None:
    """T-20. Observability anchor: `parser_kind` field present on parse events."""
    from structlog.testing import capture_logs

    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "tsconfig.json").write_text('{"compilerOptions":{"strict":true}}')
    with capture_logs() as logs:
        _run_probe(tmp_path)
    assert any(e.get("parser_kind") == "jsonc" for e in logs)


# ---------- AC-10 / sub-schema: slice optional at envelope -----------------


def test_node_build_system_slice_optional_at_envelope() -> None:
    """AC-10 — non-Node repo (no node_build_system probe block) MUST validate."""
    from codegenie.schema.validator import validate

    envelope = {
        "schema_version": "0.1.0",
        "generated_at": "2026-05-14T00:00:00Z",
        "repo": {"root": "/x", "git_commit": None},
        "probes": {
            "language_detection": {
                "language_stack": {
                    "counts": {"go": 1},
                    "primary": "go",
                    "framework_hints": [],
                    "monorepo": None,
                }
            }
        },
    }
    validate(envelope)
