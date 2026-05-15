"""Unit tests for ``NodeManifestProbe`` — S3-05 acceptance criteria.

Numbered AC tags map to the story
``docs/phases/01-context-gather-layer-a-node/stories/S3-05-node-manifest-probe.md``.

Test discipline notes:

- AC-7 is an architectural test: ``run()`` operates only through the
  module-scope dispatch registries; per-format string equality or
  isinstance branches are forbidden. ``inspect.getsource`` is the
  observable enforcement.
- AC-15 is the exact-match-vs-substring kill: ``@types/bcrypt``,
  ``bcryptjs``, ``bcrypt-utils`` are NOT hits for ``bcrypt``.
- AC-18 is the broader-net subprocess refusal: ``subprocess.run``,
  ``subprocess.Popen``, ``os.spawnv``, ``os.execv``, ``os.execvp``, and
  ``asyncio.create_subprocess_exec`` are all monkey-patched to record;
  every recorded list must be empty after ``run()`` resolves.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import jsonschema
import pytest

from codegenie.catalogs import NATIVE_MODULES_CATALOG_VERSION
from codegenie.coordinator.budget import ResourceBudget
from codegenie.errors import (
    DepthCapExceeded,
    MalformedLockfileError,
    SizeCapExceeded,
    SymlinkRefusedError,
)
from codegenie.probes.base import ProbeOutput, RepoSnapshot

# ---------- helpers ---------------------------------------------------------


def _make_snapshot(root: Path) -> RepoSnapshot:
    return RepoSnapshot(root=root, git_commit=None, detected_languages={}, config={})


def _build_repo(
    tmp_path: Path,
    *,
    pnpm_lock: bool = False,
    npm_lock: bool = False,
    yarn_lock: bool = False,
    bun_lock: bool = False,
    deps: dict[str, str] | None = None,
    optional_deps: dict[str, str] | None = None,
    bundled_deps: list[str] | None = None,
) -> Path:
    pkg: dict[str, object] = {"name": "x", "version": "1.0.0", "dependencies": deps or {}}
    if optional_deps is not None:
        pkg["optionalDependencies"] = optional_deps
    if bundled_deps is not None:
        pkg["bundledDependencies"] = bundled_deps
    (tmp_path / "package.json").write_text(json.dumps(pkg))
    if pnpm_lock:
        body = "lockfileVersion: '9.0'\npackages:\n"
        if deps:
            for name, ver in deps.items():
                body += f"  /{name}@{ver.lstrip('^~')}: {{}}\n"
        else:
            body = "lockfileVersion: '9.0'\npackages: {}\n"
        (tmp_path / "pnpm-lock.yaml").write_text(body)
    if npm_lock:
        packages: dict[str, object] = {}
        if deps:
            for name, ver in deps.items():
                packages[f"node_modules/{name}"] = {"version": ver.lstrip("^~")}
        (tmp_path / "package-lock.json").write_text(
            json.dumps({"lockfileVersion": 3, "packages": packages})
        )
    if yarn_lock:
        body = ""
        if deps:
            for name, ver in deps.items():
                body += f'{name}@{ver}:\n  version "{ver.lstrip("^~")}"\n'
        else:
            body = "# empty\n"
        (tmp_path / "yarn.lock").write_text(body)
    if bun_lock:
        (tmp_path / "bun.lockb").write_bytes(b"\x00" * 8)
    return tmp_path


# ---------- AC-1, AC-2, AC-17, AC-21, AC-22 ---------------------------------


def test_probe_contract_attributes_pin_acs() -> None:
    from codegenie.probes.node_manifest import NodeManifestProbe

    cls = NodeManifestProbe
    assert cls.name == "node_manifest"
    assert cls.layer == "A"
    assert cls.tier == "base"
    assert cls.applies_to_languages == ["javascript", "typescript"]
    assert cls.applies_to_tasks == ["*"]
    assert cls.requires == ["language_detection"]
    assert cls.timeout_seconds == 30
    assert cls.version == "0.1.0"
    # AC-1
    assert cls.declared_resource_budget == ResourceBudget(
        raw_artifact_mb=50, raw_artifact_truncate_mb=25
    )
    assert cls.declared_resource_budget.raw_artifact_truncate_mb == 25
    assert cls.declared_resource_budget.raw_artifact_mb == 50
    # AC-2 — node_modules must never appear in declared_inputs
    assert not any("node_modules" in inp for inp in cls.declared_inputs)
    # AC-17 — ADR-0006 invariant: removing this line MUST break a test.
    assert "src/codegenie/catalogs/native_modules.yaml" in cls.declared_inputs, (
        "ADR-0006: native_modules.yaml must be in declared_inputs so editing "
        "the catalog invalidates this probe's cache. Phase 7 depends on this."
    )
    # AC-22 — param naming
    sig = inspect.signature(cls.run)
    assert list(sig.parameters)[:3] == ["self", "repo", "ctx"]
    # Dead attribute from the pre-hardening draft must not exist.
    assert not hasattr(cls, "declared_raw_artifact_budget_mb")


def test_resource_budget_swap_raises() -> None:
    """AC-21 — ResourceBudget(__post_init__) enforces truncate <= mb."""
    with pytest.raises(ValueError):
        ResourceBudget(raw_artifact_mb=25, raw_artifact_truncate_mb=50)


# ---------- AC-7 — registry/strategy seam -----------------------------------


def test_run_does_not_branch_on_parser_kind() -> None:
    """AC-7 architectural test — ``run()`` operates only through the registries."""
    from codegenie.probes.node_manifest import NodeManifestProbe

    src = inspect.getsource(NodeManifestProbe.run)
    for forbidden in (
        '"pnpm" ==',
        '"yarn" ==',
        '"npm" ==',
        '== "pnpm"',
        '== "yarn"',
        '== "npm"',
    ):
        assert forbidden not in src, f"run() branches on {forbidden!r}; AC-7 violated"
    # No per-format isinstance branches inside run().
    assert not re.search(r"isinstance\([^)]+,\s*PnpmLock\)", src)
    assert not re.search(r"isinstance\([^)]+,\s*NpmLock\)", src)
    assert not re.search(r"isinstance\([^)]+,\s*YarnLock\)", src)


def test_register_probe_decorator_populates_default_registry() -> None:
    """AC-13 — ``@register_probe`` + explicit import wires into ``default_registry``."""
    import codegenie.probes  # noqa: F401 — triggers explicit imports
    from codegenie.probes.node_manifest import NodeManifestProbe
    from codegenie.probes.registry import default_registry

    names = {p.name for p in default_registry.all_probes()}
    assert "node_manifest" in names
    assert NodeManifestProbe in default_registry.all_probes()


# ---------- AC-20 — non-edit of _lockfiles/__init__.py ----------------------


def test_lockfiles_init_remains_inert() -> None:
    """AC-20 — S3-02 / S3-03 invariant re-asserted at S3-05 land."""
    from codegenie.probes import _lockfiles

    assert getattr(_lockfiles, "__all__", None) == []


# ---------- AC-3, AC-9, AC-16, AC-23 ---------------------------------------


@pytest.mark.asyncio
async def test_happy_path_pnpm_with_bcrypt(tmp_path: Path) -> None:
    from codegenie.probes.node_manifest import NodeManifestProbe

    repo_root = _build_repo(tmp_path, pnpm_lock=True, deps={"bcrypt": "^5.1.0"})
    ctx = MagicMock()
    ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    assert isinstance(out, ProbeOutput)
    assert out.confidence == "high"
    slc = out.schema_slice["manifests"]
    # AC-9 — catalog_version is the file-level integer.
    assert slc["catalog_version"] == NATIVE_MODULES_CATALOG_VERSION
    assert slc["primary"]["native_modules"]["detected"] is True
    pkgs = slc["primary"]["native_modules"]["packages"]
    # AC-16 — name is normalized, not the raw lockfile key "/bcrypt@5.1.0".
    assert {p["name"] for p in pkgs} == {"bcrypt"}
    assert pkgs[0]["version"] == "5.1.0"


@pytest.mark.asyncio
async def test_emits_probe_start_event(tmp_path: Path) -> None:
    """AC-23 — structlog discipline: probe.start emitted with probe name."""
    from structlog.testing import capture_logs

    from codegenie.probes.node_manifest import NodeManifestProbe

    repo_root = _build_repo(tmp_path, pnpm_lock=True, deps={"x": "^1"})
    ctx = MagicMock()
    ctx.parsed_manifest = None
    with capture_logs() as logs:
        await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    start_events = [e for e in logs if e.get("event") == "probe.start"]
    assert any(e.get("probe") == "node_manifest" for e in start_events)


# ---------- AC-4 / AC-5 — lockfile precedence + multi-lockfile -------------


@pytest.mark.asyncio
async def test_single_lockfile_keeps_confidence_high(tmp_path: Path) -> None:
    """AC-5 — kills the always-low mutant."""
    from codegenie.probes.node_manifest import NodeManifestProbe

    repo_root = _build_repo(tmp_path, pnpm_lock=True, deps={"x": "^1.0.0"})
    ctx = MagicMock()
    ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    assert out.confidence == "high"
    assert "lockfile.multi_present" not in out.warnings


@pytest.mark.asyncio
async def test_multi_lockfile_emits_warning_independent_of_confidence(tmp_path: Path) -> None:
    """AC-5 — split assertion; kills the 'drop the warning but keep low' mutant."""
    from codegenie.probes.node_manifest import NodeManifestProbe

    repo_root = _build_repo(tmp_path, pnpm_lock=True, npm_lock=True, deps={"x": "^1"})
    ctx = MagicMock()
    ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    assert "lockfile.multi_present" in out.warnings


@pytest.mark.asyncio
async def test_multi_lockfile_downgrades_confidence_independent_of_warning(tmp_path: Path) -> None:
    """AC-5 — split assertion; kills the 'drop low but keep warning' mutant."""
    from codegenie.probes.node_manifest import NodeManifestProbe

    repo_root = _build_repo(tmp_path, pnpm_lock=True, yarn_lock=True, deps={"x": "^1"})
    ctx = MagicMock()
    ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    assert out.confidence == "low"


@pytest.mark.asyncio
async def test_bun_lockb_copresent_trips_multi_but_is_not_parsed(tmp_path: Path) -> None:
    """AC-4 — bun.lockb counts for multi-detect but is never the selected parsed format."""
    from codegenie.probes.node_manifest import NodeManifestProbe

    repo_root = _build_repo(tmp_path, pnpm_lock=True, bun_lock=True, deps={"bcrypt": "^5.1.0"})
    ctx = MagicMock()
    ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    assert "lockfile.multi_present" in out.warnings
    assert out.schema_slice["manifests"]["primary"]["lockfile"]["name"] == "pnpm-lock.yaml"


@pytest.mark.asyncio
async def test_lockfile_precedence_pnpm_over_yarn_over_npm(tmp_path: Path) -> None:
    """AC-4 — kills the 'precedence reordered' mutant.

    Precedence (parseable subset): pnpm > yarn > npm.
    """
    from codegenie.probes.node_manifest import NodeManifestProbe

    repo_root = _build_repo(
        tmp_path, pnpm_lock=True, yarn_lock=True, npm_lock=True, deps={"x": "^1"}
    )
    ctx = MagicMock()
    ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    assert out.schema_slice["manifests"]["primary"]["lockfile"]["name"] == "pnpm-lock.yaml"

    # Remove pnpm → yarn wins over npm.
    (tmp_path / "pnpm-lock.yaml").unlink()
    out = await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    assert out.schema_slice["manifests"]["primary"]["lockfile"]["name"] == "yarn.lock"


# ---------- AC-10 — optional / bundled deps --------------------------------


@pytest.mark.asyncio
async def test_optional_and_bundled_deps_extraction(tmp_path: Path) -> None:
    """AC-10 — present → length / list."""
    from codegenie.probes.node_manifest import NodeManifestProbe

    repo_root = _build_repo(
        tmp_path,
        pnpm_lock=True,
        deps={"a": "^1"},
        optional_deps={"b": "^2", "c": "^3"},
        bundled_deps=["d", "e"],
    )
    ctx = MagicMock()
    ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    primary = out.schema_slice["manifests"]["primary"]
    assert primary["optional_dependencies"] == 2
    assert primary["bundled_dependencies"] == ["d", "e"]


@pytest.mark.asyncio
async def test_optional_and_bundled_deps_absent(tmp_path: Path) -> None:
    """AC-10 — absent → 0 / []."""
    from codegenie.probes.node_manifest import NodeManifestProbe

    repo_root = _build_repo(tmp_path, pnpm_lock=True, deps={"a": "^1"})
    ctx = MagicMock()
    ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    primary = out.schema_slice["manifests"]["primary"]
    assert primary["optional_dependencies"] == 0
    assert primary["bundled_dependencies"] == []


# ---------- AC-8 / AC-15 — exact-match cross-reference --------------------


@pytest.mark.parametrize(
    "resolved,expected_names",
    [
        ({"bcrypt": "5.1.1"}, {"bcrypt"}),
        ({"@types/bcrypt": "1.0.0"}, set()),
        ({"bcryptjs": "2.4.3"}, set()),
        ({"bcrypt-utils": "1.2.0"}, set()),
        ({"bcrypt": "5.1.1", "bcryptjs": "2.4.3"}, {"bcrypt"}),
    ],
)
def test_cross_reference_exact_match_not_substring(
    resolved: dict[str, str], expected_names: set[str]
) -> None:
    from codegenie.catalogs import NATIVE_MODULES
    from codegenie.probes.node_manifest import _cross_reference_native_modules

    hits = _cross_reference_native_modules(resolved, NATIVE_MODULES)
    assert {h["name"] for h in hits} == expected_names


def test_cross_reference_propagates_catalog_entry_fields() -> None:
    """AC-8 — NativeModuleHit reflects catalog entry verbatim."""
    from codegenie.catalogs import NATIVE_MODULES
    from codegenie.probes.node_manifest import _cross_reference_native_modules

    hits = _cross_reference_native_modules({"bcrypt": "5.1.1"}, NATIVE_MODULES)
    assert len(hits) == 1
    hit = hits[0]
    bcrypt_entry = NATIVE_MODULES["bcrypt"]
    assert hit["name"] == "bcrypt"
    assert hit["version"] == "5.1.1"
    assert hit["requires_node_gyp"] is bcrypt_entry.requires_node_gyp
    assert hit["system_deps_required"] == list(bcrypt_entry.system_deps_required)
    assert hit["binary_artifacts_glob"] == list(bcrypt_entry.binary_artifacts_glob)
    assert hit["catalog_entry_version"] == bcrypt_entry.catalog_entry_version


# ---------- AC-16 — flatten helpers normalize keys -------------------------


def test_flatten_pnpm_normalizes_v9_keys() -> None:
    from codegenie.probes.node_manifest import _flatten_pnpm

    parsed: dict[str, object] = {
        "packages": {"/bcrypt@5.1.1": {}, "/@types/bcrypt@1.0.0(peer@^1)": {}}
    }
    out = _flatten_pnpm(parsed)
    assert out == {"bcrypt": "5.1.1", "@types/bcrypt": "1.0.0"}


def test_flatten_pnpm_normalizes_v6_slash_keys() -> None:
    from codegenie.probes.node_manifest import _flatten_pnpm

    parsed: dict[str, object] = {"packages": {"/bcrypt/5.1.1": {}}}
    out = _flatten_pnpm(parsed)
    assert out.get("bcrypt") == "5.1.1"


def test_flatten_npm_normalizes_v3_keys() -> None:
    from codegenie.probes.node_manifest import _flatten_npm

    parsed = {
        "lockfileVersion": 3,
        "packages": {
            "": {"version": "1.0.0"},  # root package, must be skipped
            "node_modules/bcrypt": {"version": "5.1.1"},
            "node_modules/@types/bcrypt": {"version": "1.0.0"},
        },
    }
    out = _flatten_npm(parsed)
    assert out == {"bcrypt": "5.1.1", "@types/bcrypt": "1.0.0"}


def test_flatten_npm_walks_v1_dependencies_tree() -> None:
    from codegenie.probes.node_manifest import _flatten_npm

    parsed = {
        "lockfileVersion": 1,
        "dependencies": {
            "bcrypt": {"version": "5.1.1"},
            "parent": {
                "version": "2.0.0",
                "dependencies": {"child": {"version": "3.0.0"}},
            },
        },
    }
    out = _flatten_npm(parsed)
    assert out["bcrypt"] == "5.1.1"
    assert out["parent"] == "2.0.0"
    assert out["child"] == "3.0.0"


def test_flatten_yarn_normalizes_comma_joined_and_scoped() -> None:
    from codegenie.probes.node_manifest import _flatten_yarn

    parsed = {
        "entries": {
            "bcrypt@^5.1.0, bcrypt@^5.0": {"version": "5.1.1"},
            "@types/bcrypt@^1.0.0": {"version": "1.0.0"},
        }
    }
    out = _flatten_yarn(parsed)
    assert out == {"bcrypt": "5.1.1", "@types/bcrypt": "1.0.0"}


# ---------- AC-6 — error-ID translation -----------------------------------


@pytest.mark.parametrize(
    "kind,exc_cls,expected",
    [
        ("pnpm", SizeCapExceeded, "pnpm_lock.size_cap_exceeded"),
        ("pnpm", DepthCapExceeded, "pnpm_lock.depth_cap_exceeded"),
        ("pnpm", MalformedLockfileError, "pnpm_lock.malformed"),
        ("pnpm", SymlinkRefusedError, "pnpm_lock.symlink_refused"),
        ("npm", SizeCapExceeded, "npm_lock.size_cap_exceeded"),
        ("npm", MalformedLockfileError, "npm_lock.malformed"),
        ("yarn", SizeCapExceeded, "yarn_lock.size_cap_exceeded"),
        ("yarn", MalformedLockfileError, "yarn_lock.malformed"),
        ("yarn", SymlinkRefusedError, "yarn_lock.symlink_refused"),
    ],
)
def test_error_id_table_matches_adr_0007_pattern(
    kind: str, exc_cls: type[BaseException], expected: str
) -> None:
    from codegenie.probes.node_manifest import ParserKind, _error_id

    parser_kind: ParserKind = kind  # type: ignore[assignment]
    assert _error_id(parser_kind, exc_cls(f"/p: {exc_cls.__name__}")) == expected
    assert re.fullmatch(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$", expected)


# ---------- AC-18 — no subprocess (broader net) ---------------------------


@pytest.mark.asyncio
async def test_no_subprocess_for_dep_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-18 — broader monkey-patch net catches future contributors reaching for
    Popen / os.execv / asyncio.create_subprocess_exec, not just subprocess.run.
    """
    from codegenie.probes.node_manifest import NodeManifestProbe

    calls: dict[str, list[tuple[tuple[object, ...], dict[str, object]]]] = {
        k: [] for k in ("run", "Popen", "spawnv", "execv", "execvp", "create_subprocess_exec")
    }
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls["run"].append((a, k)))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: calls["Popen"].append((a, k)))
    monkeypatch.setattr(os, "spawnv", lambda *a, **k: calls["spawnv"].append((a, k)))
    monkeypatch.setattr(os, "execv", lambda *a, **k: calls["execv"].append((a, k)))
    monkeypatch.setattr(os, "execvp", lambda *a, **k: calls["execvp"].append((a, k)))
    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        lambda *a, **k: calls["create_subprocess_exec"].append((a, k)),
    )

    repo_root = _build_repo(tmp_path, pnpm_lock=True, deps={"x": "^1"})
    ctx = MagicMock()
    ctx.parsed_manifest = None
    await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    for kind, recorded in calls.items():
        assert recorded == [], f"forbidden subprocess shape invoked: {kind}"


# ---------- AC-3 / AC-6 — oversized lockfile via os.fstat monkey-patch ----


@pytest.mark.asyncio
async def test_oversized_lockfile_degrades_gracefully(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """AC-6 — SizeCapExceeded → typed error_id → confidence=low, gather continues.

    Forces the size-cap path via parser-level monkey-patch (avoids the 60 MB
    tmpfs write the original draft prescribed and isolates the lockfile-parser
    failure path from package.json reads). The shape of the assertion — typed
    error_id on ``out.errors`` + ``confidence="low"`` — pins AC-6 cleanly:
    swallowing ``SizeCapExceeded`` into a bare ``CodegenieError`` would
    break the contract.
    """
    from codegenie.probes import node_manifest as nm
    from codegenie.probes.node_manifest import NodeManifestProbe

    repo_root = _build_repo(tmp_path, pnpm_lock=True, deps={"x": "^1"})

    def _raise_size_cap(_path: Path) -> object:
        raise SizeCapExceeded(f"{_path}: simulated oversized lockfile")

    monkeypatch.setitem(nm._PARSERS, "pnpm", _raise_size_cap)
    ctx = MagicMock()
    ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(_make_snapshot(repo_root), ctx)
    assert out.confidence == "low"
    assert "pnpm_lock.size_cap_exceeded" in out.errors


# ---------- AC-11 / AC-14 — sub-schema rejection at JSON Pointer ----------


@pytest.fixture
def _node_manifest_subschema() -> dict[str, object]:
    from importlib.resources import files

    path = files("codegenie.schema.probes").joinpath("node_manifest.schema.json")
    parsed: dict[str, object] = json.loads(path.read_text())
    return parsed


@pytest.mark.parametrize(
    "inject_at,expected_pointer_suffix",
    [
        ([], "extra_at_root"),
        (["primary"], "extra_in_primary"),
        (["primary", "native_modules", "packages", 0], "extra_in_hit"),
    ],
)
def test_subschema_rejects_extra_field_at_pointer(
    _node_manifest_subschema: dict[str, object],
    inject_at: list[object],
    expected_pointer_suffix: str,
) -> None:
    manifests_slice: dict[str, object] = {
        "primary": {
            "path": "package.json",
            "direct_dependencies": {"runtime": 1, "dev": 0},
            "declared_engines": {},
            "lockfile": {"name": "pnpm-lock.yaml"},
            "native_modules": {
                "detected": True,
                "packages": [
                    {
                        "name": "bcrypt",
                        "version": "5.1.1",
                        "requires_node_gyp": True,
                        "system_deps_required": [],
                        "binary_artifacts_glob": [],
                        "catalog_entry_version": 1,
                    }
                ],
            },
            "optional_dependencies": 0,
            "bundled_dependencies": [],
        },
        "catalog_version": 1,
        "warnings": [],
        "errors": [],
    }
    slice_payload: dict[str, object] = {"manifests": manifests_slice}
    target: object = manifests_slice
    for k in inject_at:
        target = target[k]  # type: ignore[index]
    target[expected_pointer_suffix] = "bogus"  # type: ignore[index]

    with pytest.raises(jsonschema.ValidationError) as exc:
        jsonschema.validate(slice_payload, _node_manifest_subschema)
    # The failing key surfaces in exc.message because additionalProperties: false
    # names the offending property in the validator's diagnostic.
    assert expected_pointer_suffix in exc.value.message


# ---------- AC-12 — prose in warnings rejected ----------------------------


def test_subschema_rejects_prose_in_warnings(
    _node_manifest_subschema: dict[str, object],
) -> None:
    payload: dict[str, object] = {
        "manifests": {
            "primary": None,
            "catalog_version": 1,
            "warnings": ["This Helm chart looks production-ready"],
            "errors": [],
        }
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, _node_manifest_subschema)


def test_subschema_accepts_well_formed_warning_id(
    _node_manifest_subschema: dict[str, object],
) -> None:
    """Sanity-check the positive arm: a properly shaped slice passes."""
    payload: dict[str, object] = {
        "manifests": {
            "primary": None,
            "catalog_version": 1,
            "warnings": ["lockfile.multi_present"],
            "errors": ["pnpm_lock.malformed"],
        }
    }
    jsonschema.validate(payload, _node_manifest_subschema)


# ---------- AC-19 — failure paths assert typed IDs, not bare CodegenieError --


@pytest.mark.asyncio
async def test_malformed_pnpm_lockfile_emits_typed_error(tmp_path: Path) -> None:
    """AC-19 — failure path asserts specific typed error_id, never bare CodegenieError."""
    from codegenie.probes.node_manifest import NodeManifestProbe

    (tmp_path / "package.json").write_text('{"name":"x","version":"1.0.0"}')
    # Garbage YAML — CSafeLoader will choke on the bad tag.
    (tmp_path / "pnpm-lock.yaml").write_text("!!python/object: bad\n")
    ctx = MagicMock()
    ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(_make_snapshot(tmp_path), ctx)
    assert "pnpm_lock.malformed" in out.errors
    assert out.confidence == "low"


# ---------- AC-3 — package.json read paths (memo, missing, malformed) ----


@pytest.mark.asyncio
async def test_malformed_package_json_emits_typed_error_and_low_confidence(
    tmp_path: Path,
) -> None:
    """AC-3 — `MalformedJSONError` on package.json yields ``primary=None``,
    confidence=low, typed error_id in ``out.errors``; gather continues.
    """
    from codegenie.probes.node_manifest import NodeManifestProbe

    (tmp_path / "package.json").write_text("{not valid json")
    ctx = MagicMock()
    ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(_make_snapshot(tmp_path), ctx)
    assert out.confidence == "low"
    assert any(err.startswith("package_json.") for err in out.errors), out.errors
    assert out.schema_slice["manifests"]["primary"] is None


@pytest.mark.asyncio
async def test_missing_package_json_emits_empty_primary_high_confidence(
    tmp_path: Path,
) -> None:
    """AC-3 — A repo with no package.json still emits a slice. The probe
    returns a minimal ``primary`` with empty dep counts and ``confidence=high``;
    skipping the slice would break envelope merging downstream.
    """
    from codegenie.probes.node_manifest import NodeManifestProbe

    ctx = MagicMock()
    ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(_make_snapshot(tmp_path), ctx)
    assert out.confidence == "high"
    primary = out.schema_slice["manifests"]["primary"]
    assert primary["direct_dependencies"] == {"runtime": 0, "dev": 0}
    assert primary["native_modules"]["detected"] is False


@pytest.mark.asyncio
async def test_package_json_memo_hit_short_circuits_safe_json_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-3 / S1-07 — when ``ctx.parsed_manifest`` returns a memoed mapping
    the probe must NOT call ``safe_json.load`` (the memo's whole purpose).
    """
    from codegenie.parsers import safe_json
    from codegenie.probes.node_manifest import NodeManifestProbe

    (tmp_path / "package.json").write_text('{"name":"x","version":"1.0.0"}')

    calls: list[Path] = []
    real_load = safe_json.load

    def _tracking_load(path: Path, *args: object, **kwargs: object) -> object:
        calls.append(path)
        return real_load(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(safe_json, "load", _tracking_load)

    ctx = MagicMock()
    ctx.parsed_manifest = lambda _p: {"name": "x", "dependencies": {"left-pad": "1.0.0"}}
    out = await NodeManifestProbe().run(_make_snapshot(tmp_path), ctx)
    assert calls == [], f"memo hit should short-circuit safe_json.load; got {calls}"
    assert out.schema_slice["manifests"]["primary"]["direct_dependencies"]["runtime"] == 1


# ---------- AC-16 — defensive type guards in flatteners -------------------


def test_flatteners_return_empty_on_non_mapping_inputs() -> None:
    """AC-16 — the three pure flatteners tolerate bad top-level shapes
    (parser returned a non-mapping, or shape with non-mapping `packages` /
    `entries`). Each returns ``{}`` rather than raising; the probe then
    proceeds with zero resolved deps and confidence drops only when the
    parser itself raised.
    """
    from codegenie.probes.node_manifest import (
        _flatten_npm,
        _flatten_pnpm,
        _flatten_yarn,
    )

    assert _flatten_pnpm("not a mapping") == {}  # type: ignore[arg-type]
    assert _flatten_pnpm({"packages": "not a mapping"}) == {}
    assert _flatten_npm("not a mapping") == {}  # type: ignore[arg-type]
    assert _flatten_npm({"packages": {"node_modules/x": "not a mapping"}}) == {}
    assert _flatten_yarn("not a mapping") == {}  # type: ignore[arg-type]
    assert _flatten_yarn({"entries": "not a mapping"}) == {}


# ---------- S5-01 AC-12 — DepthCapExceeded on package.json --------------


@pytest.mark.asyncio
async def test_deeply_nested_package_json_emits_depth_cap_error(tmp_path: Path) -> None:
    """S5-01 AC-12 — a depth-bombed ``package.json`` fires :class:`DepthCapExceeded`
    inside ``_read_package_json``; the probe maps it to
    ``package_json.depth_cap_exceeded`` on ``ProbeOutput.errors`` and the slice
    short-circuits to ``primary=None`` with ``confidence=low``.

    Closed-world equality on ``out.errors`` is the kill — a regression that drops
    ``DepthCapExceeded`` from the catch-tuple would either bubble (CodegenieError
    at the coordinator) or land an unmapped key in errors.
    """
    from codegenie.probes.node_manifest import NodeManifestProbe

    depth = 200
    payload = "1"
    for _ in range(depth):
        payload = '{"a": ' + payload + "}"
    (tmp_path / "package.json").write_text(payload)

    ctx = MagicMock()
    ctx.parsed_manifest = None
    out = await NodeManifestProbe().run(_make_snapshot(tmp_path), ctx)
    assert out.confidence == "low"
    assert out.errors == ["package_json.depth_cap_exceeded"], out.errors
    assert out.schema_slice["manifests"]["primary"] is None
