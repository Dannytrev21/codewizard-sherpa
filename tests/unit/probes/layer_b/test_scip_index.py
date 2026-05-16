"""Tests for ``ScipIndexProbe`` (S4-03 — ACs 1..19, T-01..T-Sj-2)."""

from __future__ import annotations

import ast
import json
import logging
from pathlib import Path

import pytest

from codegenie.cache.keys import key_for
from codegenie.errors import ProbeTimeoutError, ToolMissingError
from codegenie.exec import ProcessResult
from codegenie.exec import tool_versions as tv
from codegenie.indices.freshness import CommitsBehind, Fresh, IndexerError, Stale
from codegenie.indices.registry import default_freshness_registry
from codegenie.probes.base import ProbeContext, RepoSnapshot, Task
from codegenie.probes.layer_b import scip_index as si
from codegenie.probes.layer_b.scip_index import (
    _WARNING_IDS,
    ScipIndexProbe,
    _build_scip_argv,
    _compute_indexable_merkle,
    _count_indexable_files,
    _walk_indexable_files,
)
from codegenie.probes.layer_b.scip_slice import SemanticIndexSlice
from codegenie.probes.registry import default_registry
from codegenie.types.identifiers import IndexName

# ---------------------------------------------------------------------------
# Test helpers / fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_tool_version_memo() -> None:
    """Each test starts with an empty tool_versions memo."""
    tv.clear_for_tests()
    yield
    tv.clear_for_tests()


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    """Initialize a tmp git repo with one tracked .ts file at HEAD."""
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
    (tmp_path / "main.ts").write_text("export const x = 1;\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "."],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "-m", "init"],
        check=True,
        capture_output=True,
    )
    return tmp_path


@pytest.fixture
def snapshot(repo_root: Path) -> RepoSnapshot:
    return RepoSnapshot(
        root=repo_root,
        git_commit=None,
        detected_languages={"typescript": 1},
        config={},
    )


@pytest.fixture
def ctx(repo_root: Path) -> ProbeContext:
    output_dir = repo_root / ".codegenie" / "context"
    output_dir.mkdir(parents=True, exist_ok=True)
    return ProbeContext(
        cache_dir=repo_root / ".codegenie" / "cache",
        output_dir=output_dir,
        workspace=repo_root / ".codegenie" / "workspace",
        logger=logging.getLogger("test"),
        config={},
    )


async def _stub_writes_blob(probe_id, argv, *, cwd, timeout_s, max_stdout_bytes=64 * 1024 * 1024):  # type: ignore[no-untyped-def]
    """T-04 canonical stub: writes the blob then returns a real ProcessResult."""
    out_path = Path(argv[argv.index("--output") + 1])
    out_path.write_bytes(b"FAKE-SCIP-BLOB")
    summary = b'{"files_indexed": 1, "indexer_warnings": 0, "symbol_count": 7}'
    return ProcessResult(returncode=0, stdout=summary, stderr=b"")


async def _prime_version_to(monkeypatch: pytest.MonkeyPatch, version: str) -> None:
    """Prime the tool_versions memo to a known value so probe.version is deterministic."""

    async def _stub(probe_name, argv, *, cwd, timeout_s, max_stdout_bytes=64 * 1024 * 1024):  # type: ignore[no-untyped-def]
        return ProcessResult(returncode=0, stdout=version.encode("utf-8") + b"\n", stderr=b"")

    monkeypatch.setattr("codegenie.exec.tool_versions.run_external_cli", _stub)
    await tv.resolve_tool_version("scip-typescript")


# ---------------------------------------------------------------------------
# T-01 — Probe contract attributes (AC-1)
# ---------------------------------------------------------------------------


def test_probe_contract_attributes() -> None:
    probe = ScipIndexProbe()
    assert probe.name == "scip_index"
    assert probe.layer == "B"
    assert probe.tier == "base"
    assert "typescript" in probe.applies_to_languages
    assert "javascript" in probe.applies_to_languages
    assert probe.applies_to_tasks == ["*"]
    assert probe.requires == ["language_detection", "node_build_system"]
    assert probe.timeout_seconds == 300
    assert probe.cache_strategy == "content"
    # run signature is two-arg per ABC
    import inspect

    sig = inspect.signature(ScipIndexProbe.run)
    params = list(sig.parameters)
    assert params == ["self", "repo", "ctx"]


def test_version_is_property_returning_string() -> None:
    """AC-2: ``version`` is a @property that includes the resolved tool version."""
    assert isinstance(ScipIndexProbe.version, property)
    probe = ScipIndexProbe()
    import re

    assert re.match(r"^0\.1\.\d+\+scip-typescript-.+$", probe.version), probe.version


# ---------------------------------------------------------------------------
# T-02 — Argv composition is a pure helper (AC-3)
# ---------------------------------------------------------------------------


def test_build_scip_argv_shape(tmp_path: Path) -> None:
    blob = tmp_path / ".codegenie" / "context" / "raw" / "scip-index.scip"
    argv = _build_scip_argv(tmp_path, blob)
    assert argv == [
        "scip-typescript",
        "index",
        "--cwd",
        str(tmp_path),
        "--output",
        str(blob),
        "--infer-tsconfig",
    ]


# ---------------------------------------------------------------------------
# T-03 — No direct subprocess use (AC-3)
# ---------------------------------------------------------------------------


def test_no_direct_subprocess_usage() -> None:
    """AST-walk the probe module; no subprocess/Popen/os.system calls."""
    source = Path(si.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    banned = {"Popen", "system", "popen", "spawn"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr in banned:
                raise AssertionError(f"forbidden attribute call in scip_index.py: {ast.dump(node)}")
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "run":
                if isinstance(func.value, ast.Name) and func.value.id == "subprocess":
                    raise AssertionError("subprocess.run() forbidden in probe")


# ---------------------------------------------------------------------------
# T-04 — Blob lands at expected path; slice URI is repo-relative (AC-4)
# ---------------------------------------------------------------------------


async def test_blob_lands_at_expected_path(
    monkeypatch: pytest.MonkeyPatch, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    await _prime_version_to(monkeypatch, "0.3.21")
    monkeypatch.setattr("codegenie.exec.run_external_cli", _stub_writes_blob)
    monkeypatch.setattr(si._exec, "run_external_cli", _stub_writes_blob)

    output = await ScipIndexProbe().run(snapshot, ctx)

    blob_path = ctx.output_dir / "raw" / "scip-index.scip"
    assert blob_path.is_file()
    assert blob_path.read_bytes() == b"FAKE-SCIP-BLOB"
    slice_ = output.schema_slice["semantic_index"]
    assert slice_["scip_index_uri"] == ".codegenie/context/raw/scip-index.scip"


# ---------------------------------------------------------------------------
# T-05 — Slice fields per localv2.md §5.2 B1 (AC-5)
# ---------------------------------------------------------------------------


async def test_slice_fields_localv2_compliance(
    monkeypatch: pytest.MonkeyPatch, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    await _prime_version_to(monkeypatch, "0.3.21")
    # Plant a .js file — should NOT be counted in files_in_repo.
    (snapshot.root / "extra.js").write_text("// js\n", encoding="utf-8")

    monkeypatch.setattr(si._exec, "run_external_cli", _stub_writes_blob)

    output = await ScipIndexProbe().run(snapshot, ctx)
    slice_ = output.schema_slice["semantic_index"]

    # Required keys present.
    required = {
        "scip_index_uri",
        "indexer",
        "indexer_version",
        "files_indexed",
        "files_in_repo",
        "coverage_pct",
        "last_indexed_commit",
        "last_indexed_at",
        "indexer_errors",
        "indexer_warnings",
    }
    assert required.issubset(slice_.keys())
    assert slice_["indexer"] == "scip-typescript"
    assert slice_["files_in_repo"] == 1, "only .ts counted, .js excluded"
    assert slice_["files_indexed"] == 1
    assert slice_["coverage_pct"] == 100.0
    assert slice_["indexer_errors"] == 0
    # Optional field from summary stub present.
    assert slice_.get("symbol_count") == 7
    # Validates as SemanticIndexSlice (round-trip through the smart constructor).
    SemanticIndexSlice.model_validate(slice_)


# ---------------------------------------------------------------------------
# T-06 — Cache-key sensitivity via probe.version (AC-2)
# ---------------------------------------------------------------------------


class _FakeProbe:
    """Minimal probe-like used to derive a cache key against a controlled version."""

    name = "scip_index"
    declared_inputs = ["**/*.ts"]

    def __init__(self, version: str) -> None:
        self.version = version


def test_cache_key_sensitive_to_tool_version_via_probe_version(
    snapshot: RepoSnapshot,
) -> None:
    task = Task(type="distroless_migration", options={})
    p_a = _FakeProbe("0.1.0+scip-typescript-1.0.0")
    p_b = _FakeProbe("0.1.0+scip-typescript-2.0.0")
    k_a = key_for(p_a, snapshot, task)
    k_b = key_for(p_b, snapshot, task)
    assert k_a != k_b, "tool-version change must invalidate cache key"


def test_cache_key_sensitive_to_ts_file_set(snapshot: RepoSnapshot, tmp_path: Path) -> None:
    """Merkle channel: adding a .ts file (changes the size-manifest) invalidates the key.

    NOTE: ``content_hash_of_inputs`` hashes ``(path, st_size)`` tuples — see
    ``src/codegenie/hashing.py``. So a same-size content swap does NOT
    invalidate; adding a file (new path) or growing a file (new size) does.
    """
    task = Task(type="distroless_migration", options={})
    p = _FakeProbe("0.1.0+scip-typescript-1.0.0")
    k_before = key_for(p, snapshot, task)
    (snapshot.root / "added.ts").write_text("export const z = 3;\n", encoding="utf-8")
    k_after = key_for(p, snapshot, task)
    assert k_before != k_after, "new .ts file must invalidate cache key"


# ---------------------------------------------------------------------------
# T-07 — Timeout path emits typed IndexerError-flavored slice (AC-6)
# ---------------------------------------------------------------------------


async def test_timeout_path_emits_typed_error(
    monkeypatch: pytest.MonkeyPatch, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    await _prime_version_to(monkeypatch, "0.3.21")

    async def _raise_timeout(probe_id, argv, *, cwd, timeout_s, max_stdout_bytes=64 * 1024 * 1024):  # type: ignore[no-untyped-def]
        # Pre-touch the blob to verify it gets deleted on timeout.
        out_path = Path(argv[argv.index("--output") + 1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"PARTIAL")
        raise ProbeTimeoutError("simulated 300s timeout")

    monkeypatch.setattr(si._exec, "run_external_cli", _raise_timeout)
    output = await ScipIndexProbe().run(snapshot, ctx)
    slice_ = output.schema_slice["semantic_index"]

    assert slice_["indexer_errors"] == 1
    assert "scip_index.timeout" in output.warnings
    assert output.confidence == "low"
    assert not (ctx.output_dir / "raw" / "scip-index.scip").exists(), "partial blob must be deleted"
    json_path = ctx.output_dir / "raw" / "scip.json"
    assert json_path.is_file(), "scip.json MUST be written on timeout"

    # Feed through S4-01's published scip_freshness via the freshness registry.
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    freshness = default_freshness_registry.dispatch_one(
        IndexName("scip"), {IndexName("scip"): payload}, head=payload["last_indexed_commit"]
    )
    assert isinstance(freshness, Stale)
    assert isinstance(freshness.reason, IndexerError)
    assert freshness.reason.message == "indexer_reported_1_errors"


# ---------------------------------------------------------------------------
# T-08 — Non-zero exit path (AC-7)
# ---------------------------------------------------------------------------


async def test_non_zero_exit_path(
    monkeypatch: pytest.MonkeyPatch, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    await _prime_version_to(monkeypatch, "0.3.21")

    async def _exit_two(probe_id, argv, *, cwd, timeout_s, max_stdout_bytes=64 * 1024 * 1024):  # type: ignore[no-untyped-def]
        out_path = Path(argv[argv.index("--output") + 1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"PARTIAL")
        result = ProcessResult(returncode=2, stdout=b"", stderr=b"bad tsconfig\n")
        return result

    monkeypatch.setattr(si._exec, "run_external_cli", _exit_two)
    output = await ScipIndexProbe().run(snapshot, ctx)
    slice_ = output.schema_slice["semantic_index"]

    assert slice_["indexer_errors"] == 1
    assert "scip_index.exit_nonzero" in output.warnings
    # stderr text MUST NOT be in the slice (only in structured log).
    flat = json.dumps(slice_)
    assert "bad tsconfig" not in flat
    assert not (ctx.output_dir / "raw" / "scip-index.scip").exists()
    assert (ctx.output_dir / "raw" / "scip.json").is_file()


# ---------------------------------------------------------------------------
# T-09 — Walker exclusion invariant (AC-9)
# ---------------------------------------------------------------------------


def test_walker_exclusion_invariant(tmp_path: Path) -> None:
    """The walker excludes node_modules / dist / build / .git AND excludes .js/.jsx."""
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "extra.ts").write_text("//", encoding="utf-8")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "bar.ts").write_text("//", encoding="utf-8")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "c.ts").write_text("//", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "d.ts").write_text("//", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "baz.ts").write_text("//", encoding="utf-8")
    (tmp_path / "src" / "zap.tsx").write_text("//", encoding="utf-8")
    (tmp_path / "src" / "quux.js").write_text("//", encoding="utf-8")

    assert _count_indexable_files(tmp_path) == 2, "baz.ts + zap.tsx only"

    # Symmetric exclusion: Merkle unchanged when node_modules/extra.ts is added.
    merkle_with = _compute_indexable_merkle(tmp_path)
    (tmp_path / "node_modules" / "another.ts").write_text("//", encoding="utf-8")
    merkle_after_adding_excluded = _compute_indexable_merkle(tmp_path)
    assert merkle_with == merkle_after_adding_excluded, (
        "adding files under excluded dirs must not change Merkle"
    )


def test_walker_helpers_share_underlying_iterator(tmp_path: Path) -> None:
    """Structural invariant: count and merkle both route through _walk_indexable_files."""
    (tmp_path / "a.ts").write_text("//", encoding="utf-8")
    (tmp_path / "b.tsx").write_text("//", encoding="utf-8")
    files = list(_walk_indexable_files(tmp_path))
    assert _count_indexable_files(tmp_path) == len(files)


# ---------------------------------------------------------------------------
# T-10 — Tool-missing path (AC-8)
# ---------------------------------------------------------------------------


async def test_tool_missing_path(
    monkeypatch: pytest.MonkeyPatch, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    async def _raise(probe_id, argv, *, cwd, timeout_s, max_stdout_bytes=64 * 1024 * 1024):  # type: ignore[no-untyped-def]
        raise ToolMissingError("scip-typescript not found")

    # Both the resolver path AND the probe path raise; resolver must return "unknown".
    monkeypatch.setattr("codegenie.exec.tool_versions.run_external_cli", _raise)
    monkeypatch.setattr(si._exec, "run_external_cli", _raise)

    output = await ScipIndexProbe().run(snapshot, ctx)
    slice_ = output.schema_slice["semantic_index"]

    assert slice_["indexer_version"] == "unknown"
    assert "scip_index.tool_missing" in output.warnings
    assert (ctx.output_dir / "raw" / "scip.json").is_file()

    payload = json.loads((ctx.output_dir / "raw" / "scip.json").read_text(encoding="utf-8"))
    freshness = default_freshness_registry.dispatch_one(
        IndexName("scip"), {IndexName("scip"): payload}, head=payload["last_indexed_commit"]
    )
    assert isinstance(freshness, Stale)
    assert isinstance(freshness.reason, IndexerError)


# ---------------------------------------------------------------------------
# T-11 — raw_artifact_dir_unwritable short-circuit (AC-4)
# ---------------------------------------------------------------------------


async def test_raw_artifact_dir_unwritable(
    monkeypatch: pytest.MonkeyPatch, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    await _prime_version_to(monkeypatch, "0.3.21")
    # Make ctx.output_dir/raw be a file, not a directory — mkdir will fail.
    raw_path = ctx.output_dir / "raw"
    raw_path.write_text("not a dir", encoding="utf-8")

    spy_called: list[bool] = []

    async def _spy(probe_id, argv, *, cwd, timeout_s, max_stdout_bytes=64 * 1024 * 1024):  # type: ignore[no-untyped-def]
        spy_called.append(True)
        return ProcessResult(returncode=0, stdout=b"{}", stderr=b"")

    monkeypatch.setattr(si._exec, "run_external_cli", _spy)
    output = await ScipIndexProbe().run(snapshot, ctx)

    assert "scip_index.raw_artifact_dir_unwritable" in output.errors
    assert output.confidence == "low"
    assert not spy_called, "probe must not invoke run_external_cli when dir unwritable"


# ---------------------------------------------------------------------------
# T-12 — Warning ID frozenset matches ADR-0007 regex (AC-13)
# ---------------------------------------------------------------------------


def test_warning_ids_match_adr_0007() -> None:
    import re

    pattern = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    assert _WARNING_IDS  # non-empty frozenset
    for wid in _WARNING_IDS:
        assert pattern.match(wid), f"ADR-0007 violation: {wid!r}"


def test_run_only_emits_declared_warning_ids() -> None:
    """T-12b: AST-walk run() + helpers; every warnings.append literal is in _WARNING_IDS."""
    src = Path(si.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    seen: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "warnings"
        ):
            if (
                node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                seen.add(node.args[0].value)
    # The literals appended dynamically (via warning_id parameter) are tested
    # via T-07/T-08/T-10. Direct literals must all be members.
    for s in seen:
        assert s in _WARNING_IDS, f"undeclared warning id literal in run(): {s!r}"


# ---------------------------------------------------------------------------
# T-13 — Registry membership + for_task filter (AC-14)
# ---------------------------------------------------------------------------


def test_registry_membership_heaviness_heavy() -> None:
    entries = default_registry.sorted_for_dispatch()
    matches = [e for e in entries if e.cls is ScipIndexProbe]
    assert matches, "ScipIndexProbe not in registry"
    assert matches[0].heaviness == "heavy"
    assert matches[0].runs_last is False

    ts = default_registry.for_task("*", frozenset({"typescript"}))
    js = default_registry.for_task("*", frozenset({"javascript"}))
    go = default_registry.for_task("*", frozenset({"go"}))
    assert ScipIndexProbe in ts
    assert ScipIndexProbe in js
    assert ScipIndexProbe not in go


# ---------------------------------------------------------------------------
# T-19 — scip.json keys match B2 consumer (AC-16)
# ---------------------------------------------------------------------------


async def test_scip_json_keys_match_b2_consumer(
    monkeypatch: pytest.MonkeyPatch, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    await _prime_version_to(monkeypatch, "0.3.21")
    monkeypatch.setattr(si._exec, "run_external_cli", _stub_writes_blob)
    await ScipIndexProbe().run(snapshot, ctx)

    json_path = ctx.output_dir / "raw" / "scip.json"
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    required = {
        "last_indexed_commit",
        "files_indexed",
        "files_in_repo",
        "indexer_errors",
        "last_indexed_at",
    }
    assert required.issubset(payload.keys())

    # Healthy run → Fresh.
    healthy = default_freshness_registry.dispatch_one(
        IndexName("scip"), {IndexName("scip"): payload}, head=payload["last_indexed_commit"]
    )
    assert isinstance(healthy, Fresh)

    # Vary one key at a time: commits behind.
    commits_behind = default_freshness_registry.dispatch_one(
        IndexName("scip"), {IndexName("scip"): payload}, head="0" * 40
    )
    assert isinstance(commits_behind, Stale)
    assert isinstance(commits_behind.reason, CommitsBehind)

    # Indexer errors > 0.
    payload_e = dict(payload)
    payload_e["indexer_errors"] = 1
    err = default_freshness_registry.dispatch_one(
        IndexName("scip"), {IndexName("scip"): payload_e}, head=payload["last_indexed_commit"]
    )
    assert isinstance(err, Stale)
    assert isinstance(err.reason, IndexerError)


# ---------------------------------------------------------------------------
# T-Sj-2 — warm-cache hand-off: scip.json in raw_artifacts (AC-17)
# ---------------------------------------------------------------------------


async def test_warm_cache_replays_scip_json(
    monkeypatch: pytest.MonkeyPatch, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    await _prime_version_to(monkeypatch, "0.3.21")
    monkeypatch.setattr(si._exec, "run_external_cli", _stub_writes_blob)

    out1 = await ScipIndexProbe().run(snapshot, ctx)
    json_path = ctx.output_dir / "raw" / "scip.json"
    assert json_path in out1.raw_artifacts
    first_bytes = json_path.read_bytes()

    out2 = await ScipIndexProbe().run(snapshot, ctx)
    assert json_path in out2.raw_artifacts
    second_bytes = json_path.read_bytes()
    # Bytes equal modulo the timestamp — strip last_indexed_at before comparing.
    p1 = json.loads(first_bytes)
    p2 = json.loads(second_bytes)
    p1.pop("last_indexed_at")
    p2.pop("last_indexed_at")
    assert p1 == p2


# ---------------------------------------------------------------------------
# T-19b — slice envelope and scip.json share one model (AC-18)
# ---------------------------------------------------------------------------


async def test_slice_envelope_and_scip_json_share_one_model(
    monkeypatch: pytest.MonkeyPatch, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    await _prime_version_to(monkeypatch, "0.3.21")
    monkeypatch.setattr(si._exec, "run_external_cli", _stub_writes_blob)

    output = await ScipIndexProbe().run(snapshot, ctx)
    envelope = output.schema_slice["semantic_index"]
    sidecar = json.loads((ctx.output_dir / "raw" / "scip.json").read_text(encoding="utf-8"))

    assert envelope == sidecar, "envelope and scip.json must be byte-identical dicts"
