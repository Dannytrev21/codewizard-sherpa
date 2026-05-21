"""S5-04 — SbomProbe tests (Layer C, syft).

Covers Acceptance Criteria 1–8, 15, 16, 17, 22 of
``docs/phases/02-context-gather-layers-b-g/stories/S5-04-sbom-cve-probes.md``.
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
from pathlib import Path

import pytest

from codegenie.errors import ToolMissingError
from codegenie.exec import ProcessResult
from codegenie.output.paths import raw_dir
from codegenie.probes import _shared as _shared_mod  # noqa: F401 — exercises the kernel import
from codegenie.probes._shared.scanner_outcome import (
    ScannerRan,
)
from codegenie.probes.base import ProbeContext, RepoSnapshot
from codegenie.probes.layer_c import sbom as sbom_mod
from codegenie.probes.layer_c._sbom_models import (
    SyftJsonSchema,
    _ProcessExited,
    _ToolMissing,
)
from codegenie.probes.layer_c.sbom import (
    SbomProbe,
    _classify_syft_outcome,
)
from codegenie.probes.registry import default_registry

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "syft"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _repo(p: Path) -> RepoSnapshot:
    return RepoSnapshot(root=p, git_commit=None, detected_languages={}, config={})


def _ctx(p: Path) -> ProbeContext:
    return ProbeContext(
        cache_dir=p / "_c",
        output_dir=p / "_o",
        workspace=p / "_w",
        logger=logging.getLogger("t"),
        config={},
    )


def _write_runtime_trace_slice(repo_root: Path, payload: dict[str, object]) -> None:
    rd = raw_dir(repo_root)
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "runtime_trace.json").write_text(json.dumps(payload))


def _ran_runtime_trace(
    digest: str = "sha256:cafebabecafebabecafebabecafebabe",
) -> dict[str, object]:
    return {
        "built_image_digest": digest,
        "trace_coverage_confidence": "high",
        "scenarios_run": ["startup", "smoke_test"],
        "scenarios_failed": [],
    }


def _run_probe(tmp_path: Path) -> dict[str, object]:
    return asyncio.run(SbomProbe().run(_repo(tmp_path), _ctx(tmp_path))).schema_slice


# ---------------------------------------------------------------------------
# AC-1 / AC-2 — class attributes + registry shape
# ---------------------------------------------------------------------------


def test_sbom_probe_class_attributes_pinned() -> None:
    """AC-1 — class attribute pin (mutation-resistant)."""
    assert SbomProbe.name == "sbom"
    assert SbomProbe.layer == "C"
    assert SbomProbe.tier == "base"
    assert SbomProbe.applies_to_tasks == ["*"]
    assert SbomProbe.applies_to_languages == ["*"]
    assert SbomProbe.requires == ["runtime_trace"]


def test_sbom_registry_entry_carries_heaviness_only() -> None:
    """AC-1 — registry entry has heaviness + runs_last only; no ``requires`` key."""
    entries = [e for e in default_registry.sorted_for_dispatch() if e.cls is SbomProbe]
    assert len(entries) == 1
    entry = entries[0]
    assert entry.heaviness == "medium"
    assert entry.runs_last is False
    # The registry-entry dataclass field surface — ``requires`` must NOT
    # appear (02-ADR-0003 Option D).
    fields = {f.name for f in entry.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    assert "requires" not in fields


def test_sbom_declared_inputs_literal() -> None:
    """AC-2 — declared_inputs is exact-string-equal to the AC literal."""
    assert SbomProbe().declared_inputs == ["Dockerfile", "image-digest:<resolved>"]
    # Mutation guard: ``image-digest:resolved`` (no angle brackets) flips red.
    assert "image-digest:<resolved>" in SbomProbe().declared_inputs


# ---------------------------------------------------------------------------
# AC-3 — upstream-unavailable table (4 sub-cases)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture, expected_kind",
    [
        ("missing", "skipped"),  # (a) read_raw_slices returns {}
        ("unparseable", "skipped"),  # (b) malformed payload (handled by read_raw_slices)
        ("not_ran", "skipped"),  # (c) outcome != ran (confidence=unavailable)
        ("null_digest", "skipped"),  # (d) built_image_digest is None
    ],
)
def test_sbom_upstream_unavailable_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixture: str, expected_kind: str
) -> None:
    # Stub run_external_cli to a spy that fails if invoked.
    spy_called = False

    async def _spy(*args: object, **kwargs: object) -> ProcessResult:
        nonlocal spy_called
        spy_called = True
        return ProcessResult(returncode=0, stdout=b"{}", stderr=b"")

    monkeypatch.setattr(sbom_mod, "run_external_cli", _spy)

    if fixture == "missing":
        pass  # No runtime_trace.json on disk → read_raw_slices returns {}
    elif fixture == "unparseable":
        rd = raw_dir(tmp_path)
        rd.mkdir(parents=True, exist_ok=True)
        # JSON top-level non-dict is silently dropped by read_raw_slices.
        (rd / "runtime_trace.json").write_text("[1,2,3]")
    elif fixture == "not_ran":
        _write_runtime_trace_slice(
            tmp_path,
            {"built_image_digest": "sha256:abc", "trace_coverage_confidence": "unavailable"},
        )
    elif fixture == "null_digest":
        _write_runtime_trace_slice(
            tmp_path, {"built_image_digest": None, "trace_coverage_confidence": "high"}
        )

    out = _run_probe(tmp_path)
    assert out["sbom"]["outcome"]["kind"] == expected_kind  # type: ignore[index]
    assert out["sbom"]["outcome"].get("reason") == "upstream_unavailable"  # type: ignore[union-attr]
    assert out["sbom"]["confidence"] == "unavailable"  # type: ignore[index]
    assert not spy_called, "syft must NOT be invoked when upstream slice absent"


# ---------------------------------------------------------------------------
# AC-4 — sibling-slice read via read_raw_slices kernel
# ---------------------------------------------------------------------------


def test_sbom_reads_runtime_trace_via_read_raw_slices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-4 — SbomProbe.run calls read_raw_slices(raw_dir(...)) exactly once."""
    call_count = 0
    real_read = sbom_mod.read_raw_slices

    def _spy(rd: Path) -> object:
        nonlocal call_count
        call_count += 1
        return real_read(rd)

    monkeypatch.setattr(sbom_mod, "read_raw_slices", _spy)

    async def _missing_syft(*args: object, **kwargs: object) -> ProcessResult:
        raise ToolMissingError("syft")

    monkeypatch.setattr(sbom_mod, "run_external_cli", _missing_syft)
    _write_runtime_trace_slice(tmp_path, _ran_runtime_trace())
    _run_probe(tmp_path)
    assert call_count == 1


# ---------------------------------------------------------------------------
# AC-5 — outcome variants
# ---------------------------------------------------------------------------


def test_sbom_tool_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-5 — syft on PATH-miss → ScannerSkipped(tool_missing)."""

    async def _raise(*args: object, **kwargs: object) -> ProcessResult:
        raise ToolMissingError("syft")

    monkeypatch.setattr(sbom_mod, "run_external_cli", _raise)
    _write_runtime_trace_slice(tmp_path, _ran_runtime_trace())
    out = _run_probe(tmp_path)
    assert out["sbom"]["outcome"]["kind"] == "skipped"  # type: ignore[index]
    assert out["sbom"]["outcome"]["reason"] == "tool_missing"  # type: ignore[index]


def test_sbom_non_zero_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-5 — syft non-zero exit → ScannerFailed."""

    async def _fail(*args: object, **kwargs: object) -> ProcessResult:
        return ProcessResult(returncode=2, stdout=b"", stderr=b"syft: image not found")

    monkeypatch.setattr(sbom_mod, "run_external_cli", _fail)
    _write_runtime_trace_slice(tmp_path, _ran_runtime_trace())
    out = _run_probe(tmp_path)
    assert out["sbom"]["outcome"]["kind"] == "failed"  # type: ignore[index]
    assert out["sbom"]["outcome"]["exit_code"] == 2  # type: ignore[index]
    assert "image not found" in out["sbom"]["outcome"]["stderr_tail"]  # type: ignore[index]


def test_sbom_invalid_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-5 — syft emits truncated JSON → ScannerFailed(reason=invalid_json)."""

    async def _truncated(*args: object, **kwargs: object) -> ProcessResult:
        return ProcessResult(returncode=0, stdout=b'{ "artifacts": [ { "id":', stderr=b"")

    monkeypatch.setattr(sbom_mod, "run_external_cli", _truncated)
    _write_runtime_trace_slice(tmp_path, _ran_runtime_trace())
    out = _run_probe(tmp_path)
    assert out["sbom"]["outcome"]["kind"] == "failed"  # type: ignore[index]
    assert out["sbom"]["outcome"]["reason"] == "invalid_json"  # type: ignore[index]


def test_sbom_happy_path_populates_slice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-5/AC-6 — syft success → ScannerRan + populated slice."""
    fixture_bytes = (FIXTURES / "hello_world.json").read_bytes()

    async def _ok(*args: object, **kwargs: object) -> ProcessResult:
        return ProcessResult(returncode=0, stdout=fixture_bytes, stderr=b"")

    monkeypatch.setattr(sbom_mod, "run_external_cli", _ok)
    _write_runtime_trace_slice(tmp_path, _ran_runtime_trace())
    out = _run_probe(tmp_path)
    sbom = out["sbom"]
    assert sbom["outcome"]["kind"] == "ran"  # type: ignore[index]
    assert sbom["package_count"] == 4  # type: ignore[index]
    assert sbom["packages_by_source"]["apk"] == 2  # type: ignore[index]
    assert sbom["packages_by_source"]["npm"] == 2  # type: ignore[index]
    assert sbom["os_packages_classification"]["runtime_required"] == 2  # type: ignore[index]
    assert sbom["npm_packages_native_module_count"] == 1  # type: ignore[index]
    assert sbom["total_size_bytes"] == 12345678  # type: ignore[index]
    assert sbom["built_image_digest"].startswith("sha256:")  # type: ignore[union-attr]
    assert sbom["confidence"] == "high"  # type: ignore[index]


# ---------------------------------------------------------------------------
# AC-7 — two-file write discipline
# ---------------------------------------------------------------------------


def test_sbom_two_files_written_on_happy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-7 — sbom.json (typed slice) AND syft-sbom.json (raw bytes)."""
    fixture_bytes = (FIXTURES / "hello_world.json").read_bytes()

    async def _ok(*args: object, **kwargs: object) -> ProcessResult:
        return ProcessResult(returncode=0, stdout=fixture_bytes, stderr=b"")

    monkeypatch.setattr(sbom_mod, "run_external_cli", _ok)
    _write_runtime_trace_slice(tmp_path, _ran_runtime_trace())
    _run_probe(tmp_path)
    rd = raw_dir(tmp_path)
    assert (rd / "sbom.json").is_file()
    assert (rd / "syft-sbom.json").is_file()
    # Raw tool bytes byte-identical to fixture.
    assert (rd / "syft-sbom.json").read_bytes() == fixture_bytes


def test_sbom_no_raw_artifact_on_invalid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-7 / AC-V (bad-JSON) — only sbom.json written; artifact_uri is None."""

    async def _truncated(*args: object, **kwargs: object) -> ProcessResult:
        return ProcessResult(returncode=0, stdout=b'{ "artifacts": [ { "id":', stderr=b"")

    monkeypatch.setattr(sbom_mod, "run_external_cli", _truncated)
    _write_runtime_trace_slice(tmp_path, _ran_runtime_trace())
    out = _run_probe(tmp_path)
    rd = raw_dir(tmp_path)
    assert (rd / "sbom.json").is_file()
    assert not (rd / "syft-sbom.json").exists()
    assert out["sbom"]["artifact_uri"] is None  # type: ignore[index]


# ---------------------------------------------------------------------------
# AC-V (Pydantic discipline) — extra=allow on tool schema, forbid on emitted
# ---------------------------------------------------------------------------


def test_pydantic_extra_asymmetry_sbom() -> None:
    """AC — SyftJsonSchema tolerates extras (forward-compat with syft)."""
    assert SyftJsonSchema.model_config.get("extra") == "allow"
    # Emitted slice schema is the strict side.
    schema_path = (
        Path(__file__).resolve().parents[4]
        / "src"
        / "codegenie"
        / "schema"
        / "probes"
        / "layer_c"
        / "sbom.schema.json"
    )
    schema = json.loads(schema_path.read_text())
    assert schema["additionalProperties"] is False


# ---------------------------------------------------------------------------
# AC — AST audits (sibling-slice via read_raw_slices; run_external_cli only)
# ---------------------------------------------------------------------------


def _ast_calls(module_source: str) -> set[str]:
    """Return the set of all ast.Call function-name leaves in *module_source*."""
    tree = ast.parse(module_source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def _ast_imports(module_source: str) -> set[str]:
    tree = ast.parse(module_source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
    return names


def test_ast_audit_sbom_uses_kernel() -> None:
    """AC — AST audit: read_raw_slices imported; no open-coded disk IO on raw_dir."""
    source = Path(sbom_mod.__file__).read_text()  # type: ignore[arg-type]
    assert "read_raw_slices" in _ast_imports(source)
    # No `Path.glob` or `Path.open` or `json.loads(Path(...).read_text())` in sbom.py
    # (These calls are present in the read_raw_slices kernel itself, not here.)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "glob":
                pytest.fail(f"forbidden Path.glob call in sbom.py at line {node.lineno}")
            if node.func.attr == "loads":
                # json.loads on a file's read_text counts as forbidden open-coded
                # disk IO; permitted only inside read_raw_slices.
                pytest.fail(f"forbidden json.loads call in sbom.py at line {node.lineno}")


def test_ast_audit_sbom_uses_run_external_cli_not_run_allowlisted() -> None:
    """AC — AST audit: run_external_cli imported; run_allowlisted NOT imported."""
    source = Path(sbom_mod.__file__).read_text()  # type: ignore[arg-type]
    imports = _ast_imports(source)
    assert "run_external_cli" in imports
    assert "run_allowlisted" not in imports


# ---------------------------------------------------------------------------
# AC — Pure classifier discipline (totality + purity)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "attempt, expected_kind",
    [
        (_ToolMissing(), "skipped"),
        (_ProcessExited(exit_code=0, stdout=b'{"artifacts":[]}', stderr_tail=""), "ran"),
        (_ProcessExited(exit_code=2, stdout=b"", stderr_tail="boom"), "failed"),
        (_ProcessExited(exit_code=0, stdout=b"{ not json", stderr_tail=""), "failed"),
    ],
)
def test_classify_syft_outcome_table(attempt: object, expected_kind: str) -> None:
    out = _classify_syft_outcome(attempt)  # type: ignore[arg-type]
    assert out.kind == expected_kind


def test_classify_syft_outcome_is_pure_no_side_effects() -> None:
    """AC — classifier is a pure function: same input → same output, never raises."""
    a = _ProcessExited(exit_code=0, stdout=b'{"artifacts":[]}', stderr_tail="")
    first = _classify_syft_outcome(a)
    for _ in range(50):
        again = _classify_syft_outcome(a)
        assert again.model_dump() == first.model_dump()


def test_classify_syft_outcome_never_raises_random_bytes() -> None:
    """AC (totality) — random binary stdout never raises from the classifier."""
    import os as _os

    for _ in range(100):
        stdout = _os.urandom(64)
        exit_code = (stdout[0] if stdout else 0) % 3
        attempt = _ProcessExited(exit_code=exit_code, stdout=stdout, stderr_tail="")
        outcome = _classify_syft_outcome(attempt)
        assert outcome.kind in {"ran", "skipped", "failed"}


# ---------------------------------------------------------------------------
# AC — Mutation-resistance table — six wrong-stubs each must fail ≥ 1 test
# ---------------------------------------------------------------------------


def test_classifier_mutation_always_ran_breaks_invalid_json() -> None:
    """Mutation: classifier that returns ScannerRan regardless of input —
    must be caught by the invalid_json AC test path."""

    # Synthetic mutant inline:
    def _mutant_classifier(attempt: object) -> object:
        return ScannerRan(findings=[])

    attempt = _ProcessExited(exit_code=0, stdout=b"{ not json", stderr_tail="")
    correct = _classify_syft_outcome(attempt)
    mutated = _mutant_classifier(attempt)
    assert correct.kind != mutated.kind  # type: ignore[attr-defined]


def test_classifier_mutation_drop_tool_check_breaks_tool_missing() -> None:
    """Mutation: ignoring _ToolMissing → ScannerRan on missing tool."""
    correct = _classify_syft_outcome(_ToolMissing())
    assert correct.kind == "skipped"
    # The mutated path would have returned ScannerRan (or raised); either way
    # the AC test_sbom_tool_missing flips red — covered by that test.


def test_no_image_digest_token_in_declared_inputs_mutation() -> None:
    """Mutation: dropping the ``image-digest:<resolved>`` token breaks the
    cache-correctness contract (02-ADR-0004 §Consequences)."""
    di = SbomProbe().declared_inputs
    assert "image-digest:<resolved>" in di
    # Sibling-mutation: token mis-spelled (no angle brackets).
    assert "image-digest:resolved" not in di
