"""S5-04 — CveProbe tests (Layer C, grype).

Covers Acceptance Criteria 8–14 of
``docs/phases/02-context-gather-layers-b-g/stories/S5-04-sbom-cve-probes.md``.
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import random
from pathlib import Path

import pytest

from codegenie.errors import ToolMissingError
from codegenie.exec import ProcessResult
from codegenie.output.paths import raw_dir
from codegenie.probes.base import ProbeContext, RepoSnapshot
from codegenie.probes.layer_c import cve as cve_mod
from codegenie.probes.layer_c._cve_models import (
    GrypeJsonSchema,
    _ProcessExited,
    _SbomArtifactMissing,
    _ToolMissing,
)
from codegenie.probes.layer_c.cve import (
    _TOP_FINDINGS_N,
    CveProbe,
    _classify_grype_outcome,
    _top_findings,
)
from codegenie.probes.registry import default_registry

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "grype"


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


def _write_sbom_slice(
    repo_root: Path,
    *,
    artifact_uri: str,
    built_image_digest: str = "sha256:cafe1234cafe5678",
    outcome_kind: str = "ran",
    write_raw_tool: bool = True,
    raw_tool_bytes: bytes | None = None,
) -> None:
    """Set up an upstream sbom.json + syft-sbom.json (the latter at the
    artifact_uri path) so CveProbe sees a populated upstream."""
    rd = raw_dir(repo_root)
    rd.mkdir(parents=True, exist_ok=True)
    sbom_slice = {
        "artifact_uri": artifact_uri,
        "built_image_digest": built_image_digest,
        "package_count": 4,
        "outcome": {"kind": outcome_kind},
        "confidence": "high",
    }
    (rd / "sbom.json").write_text(json.dumps(sbom_slice, sort_keys=True))
    if write_raw_tool and outcome_kind == "ran":
        target = Path(artifact_uri)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw_tool_bytes or (FIXTURES / "no_findings.json").read_bytes())


def _run_probe(tmp_path: Path) -> dict[str, object]:
    return asyncio.run(CveProbe().run(_repo(tmp_path), _ctx(tmp_path))).schema_slice


# ---------------------------------------------------------------------------
# AC-8 / AC-9 — class attributes + registry
# ---------------------------------------------------------------------------


def test_cve_probe_class_attributes_pinned() -> None:
    """AC-8 — class-attribute pin."""
    assert CveProbe.name == "cve"
    assert CveProbe.layer == "C"
    assert CveProbe.tier == "base"
    assert CveProbe.applies_to_tasks == ["*"]
    assert CveProbe.applies_to_languages == ["*"]
    assert CveProbe.requires == ["sbom"]


def test_cve_registry_entry_carries_heaviness_only() -> None:
    entries = [e for e in default_registry.sorted_for_dispatch() if e.cls is CveProbe]
    assert len(entries) == 1
    entry = entries[0]
    assert entry.heaviness == "medium"
    assert entry.runs_last is False
    fields = {f.name for f in entry.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    assert "requires" not in fields


def test_cve_declared_inputs_literal() -> None:
    assert CveProbe().declared_inputs == ["image-digest:<resolved>"]


# ---------------------------------------------------------------------------
# AC-10 — upstream-unavailable table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture, expected_reason",
    [
        ("missing", "upstream_unavailable"),
        ("not_ran", "upstream_unavailable"),
        ("no_artifact_uri", "upstream_unavailable"),
        ("unparseable", "upstream_unavailable"),
    ],
)
def test_cve_upstream_unavailable_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fixture: str,
    expected_reason: str,
) -> None:
    spy_called = False

    async def _spy(*args: object, **kwargs: object) -> ProcessResult:
        nonlocal spy_called
        spy_called = True
        return ProcessResult(returncode=0, stdout=b"{}", stderr=b"")

    monkeypatch.setattr(cve_mod, "run_external_cli", _spy)

    rd = raw_dir(tmp_path)
    rd.mkdir(parents=True, exist_ok=True)

    if fixture == "missing":
        pass  # No sbom.json → read_raw_slices returns {}
    elif fixture == "not_ran":
        (rd / "sbom.json").write_text(json.dumps({"outcome": {"kind": "skipped"}}))
    elif fixture == "no_artifact_uri":
        (rd / "sbom.json").write_text(
            json.dumps({"outcome": {"kind": "ran"}, "built_image_digest": "sha256:abc"})
        )
    elif fixture == "unparseable":
        (rd / "sbom.json").write_text("[1,2,3]")  # top-level non-dict, dropped

    out = _run_probe(tmp_path)
    assert out["cve"]["outcome"]["kind"] == "skipped"  # type: ignore[index]
    assert out["cve"]["outcome"]["reason"] == expected_reason  # type: ignore[index]
    assert not spy_called, "grype must NOT be invoked when upstream slice absent/incomplete"


# ---------------------------------------------------------------------------
# AC-10 — sbom-artifact-missing path: slice says ran but file missing
# ---------------------------------------------------------------------------


def test_cve_sbom_artifact_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-10 — sbom.json says ran with artifact_uri, but the file at that
    path was deleted; CveProbe must emit ScannerFailed(reason=
    sbom_artifact_missing) and NOT invoke grype."""
    spy_called = False

    async def _spy(*args: object, **kwargs: object) -> ProcessResult:
        nonlocal spy_called
        spy_called = True
        return ProcessResult(returncode=0, stdout=b"{}", stderr=b"")

    monkeypatch.setattr(cve_mod, "run_external_cli", _spy)
    rd = raw_dir(tmp_path)
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "sbom.json").write_text(
        json.dumps(
            {
                "outcome": {"kind": "ran"},
                "artifact_uri": str(rd / "syft-sbom.json"),
                "built_image_digest": "sha256:abc",
            }
        )
    )
    # syft-sbom.json is intentionally NOT written.

    out = _run_probe(tmp_path)
    assert out["cve"]["outcome"]["kind"] == "failed"  # type: ignore[index]
    assert out["cve"]["outcome"]["reason"] == "sbom_artifact_missing"  # type: ignore[index]
    assert not spy_called


# ---------------------------------------------------------------------------
# AC-11 / AC-12 — outcome variants
# ---------------------------------------------------------------------------


def test_cve_tool_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _raise(*args: object, **kwargs: object) -> ProcessResult:
        raise ToolMissingError("grype")

    monkeypatch.setattr(cve_mod, "run_external_cli", _raise)
    rd = raw_dir(tmp_path)
    _write_sbom_slice(tmp_path, artifact_uri=str(rd / "syft-sbom.json"))
    out = _run_probe(tmp_path)
    assert out["cve"]["outcome"]["kind"] == "skipped"  # type: ignore[index]
    assert out["cve"]["outcome"]["reason"] == "tool_missing"  # type: ignore[index]


def test_cve_non_zero_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fail(*args: object, **kwargs: object) -> ProcessResult:
        return ProcessResult(returncode=3, stdout=b"", stderr=b"grype: db not found")

    monkeypatch.setattr(cve_mod, "run_external_cli", _fail)
    rd = raw_dir(tmp_path)
    _write_sbom_slice(tmp_path, artifact_uri=str(rd / "syft-sbom.json"))
    out = _run_probe(tmp_path)
    assert out["cve"]["outcome"]["kind"] == "failed"  # type: ignore[index]
    assert out["cve"]["outcome"]["exit_code"] == 3  # type: ignore[index]


def test_cve_invalid_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _truncated(*args: object, **kwargs: object) -> ProcessResult:
        return ProcessResult(returncode=0, stdout=b'{ "matches": [', stderr=b"")

    monkeypatch.setattr(cve_mod, "run_external_cli", _truncated)
    rd = raw_dir(tmp_path)
    _write_sbom_slice(tmp_path, artifact_uri=str(rd / "syft-sbom.json"))
    out = _run_probe(tmp_path)
    assert out["cve"]["outcome"]["kind"] == "failed"  # type: ignore[index]
    assert out["cve"]["outcome"]["reason"] == "invalid_json"  # type: ignore[index]


def test_cve_happy_path_populates_slice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture_bytes = (FIXTURES / "hello_world.json").read_bytes()

    async def _ok(*args: object, **kwargs: object) -> ProcessResult:
        return ProcessResult(returncode=0, stdout=fixture_bytes, stderr=b"")

    monkeypatch.setattr(cve_mod, "run_external_cli", _ok)
    rd = raw_dir(tmp_path)
    _write_sbom_slice(tmp_path, artifact_uri=str(rd / "syft-sbom.json"))
    out = _run_probe(tmp_path)
    cve = out["cve"]
    assert cve["outcome"]["kind"] == "ran"  # type: ignore[index]
    assert cve["scanner"] == "grype"  # type: ignore[index]
    assert cve["total"] == 4  # type: ignore[index]
    assert cve["by_severity"]["critical"] == 1  # type: ignore[index]
    assert cve["by_severity"]["high"] == 1  # type: ignore[index]
    assert cve["by_severity"]["medium"] == 1  # type: ignore[index]
    assert cve["by_severity"]["negligible"] == 1  # type: ignore[index]
    assert cve["by_source"]["apk"] == 3  # type: ignore[index]
    assert cve["by_source"]["npm"] == 1  # type: ignore[index]
    # top_findings deterministic: severity desc → package name asc → CVE id asc
    top = cve["top_findings"]  # type: ignore[index]
    assert top[0]["severity"] == "critical"  # type: ignore[index]
    assert top[0]["cve_id"] == "CVE-2024-0001"  # type: ignore[index]


# ---------------------------------------------------------------------------
# AC-13 — two-file write
# ---------------------------------------------------------------------------


def test_cve_two_files_written_on_happy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_bytes = (FIXTURES / "hello_world.json").read_bytes()

    async def _ok(*args: object, **kwargs: object) -> ProcessResult:
        return ProcessResult(returncode=0, stdout=fixture_bytes, stderr=b"")

    monkeypatch.setattr(cve_mod, "run_external_cli", _ok)
    rd = raw_dir(tmp_path)
    _write_sbom_slice(tmp_path, artifact_uri=str(rd / "syft-sbom.json"))
    _run_probe(tmp_path)
    assert (rd / "cve.json").is_file()
    assert (rd / "grype-cves.json").is_file()
    assert (rd / "grype-cves.json").read_bytes() == fixture_bytes


def test_cve_no_raw_artifact_on_invalid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _truncated(*args: object, **kwargs: object) -> ProcessResult:
        return ProcessResult(returncode=0, stdout=b'{ "matches":', stderr=b"")

    monkeypatch.setattr(cve_mod, "run_external_cli", _truncated)
    rd = raw_dir(tmp_path)
    _write_sbom_slice(tmp_path, artifact_uri=str(rd / "syft-sbom.json"))
    out = _run_probe(tmp_path)
    assert (rd / "cve.json").is_file()
    assert not (rd / "grype-cves.json").exists()
    assert out["cve"]["artifact_uri"] is None  # type: ignore[index]


# ---------------------------------------------------------------------------
# AC — _TOP_FINDINGS_N constant + deterministic truncation
# ---------------------------------------------------------------------------


def test_top_findings_n_constant_is_twenty() -> None:
    assert _TOP_FINDINGS_N == 20


def _build_50_findings() -> list[dict[str, object]]:
    """Deterministic 50-finding fixture, fixed regardless of randomness."""
    severities = ["Critical", "High", "Medium", "Low", "Negligible"]
    pkgs = ["aaa", "bbb", "ccc", "ddd", "eee", "fff", "ggg"]
    out: list[dict[str, object]] = []
    for i in range(50):
        out.append(
            {
                "vulnerability": {
                    "id": f"CVE-X-{i:05d}",
                    "severity": severities[i % len(severities)],
                },
                "artifact": {
                    "name": pkgs[i % len(pkgs)],
                    "version": "1.0",
                    "type": "apk",
                },
            }
        )
    return out


def test_top_findings_deterministic_under_permutation() -> None:
    """AC — top_findings is byte-identical across permutations of THE SAME input."""
    base = _build_50_findings()
    parsed_a = GrypeJsonSchema.model_validate_json(json.dumps({"matches": base}).encode())
    out_a = _top_findings(parsed_a)
    assert len(out_a) == 20

    # 5 distinct permutations of the same finding list — each must yield
    # byte-identical top_findings.
    for seed in (1, 7, 13, 42, 99):
        perm = list(base)
        random.Random(seed).shuffle(perm)
        parsed_p = GrypeJsonSchema.model_validate_json(json.dumps({"matches": perm}).encode())
        out_p = _top_findings(parsed_p)
        assert out_p == out_a, f"permutation seed={seed} produced non-identical top_findings"


# ---------------------------------------------------------------------------
# AC-22 — no trivy field
# ---------------------------------------------------------------------------


def test_cve_no_trivy_field(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 2 scope guard — slice MUST NOT carry a ``cross_validated_with`` field."""
    fixture_bytes = (FIXTURES / "no_findings.json").read_bytes()

    async def _ok(*args: object, **kwargs: object) -> ProcessResult:
        return ProcessResult(returncode=0, stdout=fixture_bytes, stderr=b"")

    monkeypatch.setattr(cve_mod, "run_external_cli", _ok)
    rd = raw_dir(tmp_path)
    _write_sbom_slice(tmp_path, artifact_uri=str(rd / "syft-sbom.json"))
    out = _run_probe(tmp_path)
    assert "cross_validated_with" not in out["cve"]  # type: ignore[operator]
    assert out["cve"]["scanner"] == "grype"  # type: ignore[index]


# ---------------------------------------------------------------------------
# AC — Pydantic extra asymmetry
# ---------------------------------------------------------------------------


def test_pydantic_extra_asymmetry_cve() -> None:
    assert GrypeJsonSchema.model_config.get("extra") == "allow"
    schema_path = (
        Path(__file__).resolve().parents[4]
        / "src"
        / "codegenie"
        / "schema"
        / "probes"
        / "layer_c"
        / "cve.schema.json"
    )
    schema = json.loads(schema_path.read_text())
    assert schema["additionalProperties"] is False


# ---------------------------------------------------------------------------
# AC — AST audits
# ---------------------------------------------------------------------------


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


def test_ast_audit_cve_uses_kernel() -> None:
    source = Path(cve_mod.__file__).read_text()  # type: ignore[arg-type]
    assert "read_raw_slices" in _ast_imports(source)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "glob":
                pytest.fail(f"forbidden Path.glob call in cve.py at line {node.lineno}")
            if node.func.attr == "loads":
                pytest.fail(f"forbidden json.loads call in cve.py at line {node.lineno}")


def test_ast_audit_cve_uses_run_external_cli_not_run_allowlisted() -> None:
    source = Path(cve_mod.__file__).read_text()  # type: ignore[arg-type]
    imports = _ast_imports(source)
    assert "run_external_cli" in imports
    assert "run_allowlisted" not in imports


# ---------------------------------------------------------------------------
# AC — Pure classifier discipline
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "attempt, expected_kind",
    [
        (_ToolMissing(), "skipped"),
        (_SbomArtifactMissing(expected_path="/x/y"), "failed"),
        (_ProcessExited(exit_code=0, stdout=b'{"matches":[]}', stderr_tail=""), "ran"),
        (_ProcessExited(exit_code=5, stdout=b"", stderr_tail="boom"), "failed"),
        (_ProcessExited(exit_code=0, stdout=b"{ not json", stderr_tail=""), "failed"),
    ],
)
def test_classify_grype_outcome_table(attempt: object, expected_kind: str) -> None:
    out = _classify_grype_outcome(attempt)  # type: ignore[arg-type]
    assert out.kind == expected_kind


def test_classify_grype_outcome_is_pure() -> None:
    a = _ProcessExited(exit_code=0, stdout=b'{"matches":[]}', stderr_tail="")
    first = _classify_grype_outcome(a)
    for _ in range(50):
        again = _classify_grype_outcome(a)
        assert again.model_dump() == first.model_dump()


def test_classify_grype_outcome_never_raises_random_bytes() -> None:
    """AC (totality) — random binary stdout never raises from the classifier."""
    import os as _os

    for _ in range(100):
        stdout = _os.urandom(64)
        exit_code = (stdout[0] if stdout else 0) % 3
        attempt = _ProcessExited(exit_code=exit_code, stdout=stdout, stderr_tail="")
        outcome = _classify_grype_outcome(attempt)
        assert outcome.kind in {"ran", "skipped", "failed"}


# ---------------------------------------------------------------------------
# Sub-schema rejection — additionalProperties: false
# ---------------------------------------------------------------------------


def test_cve_schema_rejects_unknown_top_level_field() -> None:
    """AC — emitted slice schema rejects unknown top-level fields."""
    import jsonschema

    schema_path = (
        Path(__file__).resolve().parents[4]
        / "src"
        / "codegenie"
        / "schema"
        / "probes"
        / "layer_c"
        / "cve.schema.json"
    )
    schema = json.loads(schema_path.read_text())
    valid = {
        "cve": {
            "artifact_uri": None,
            "scanner": "grype",
            "scanned_image_digest": None,
            "total": 0,
            "by_severity": {
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "negligible": 0,
            },
            "by_source": {},
            "top_findings": [],
            "outcome": {"kind": "skipped"},
            "confidence": "unavailable",
        }
    }
    jsonschema.validate(valid, schema)
    invalid = {**valid, "extra_top_level": True}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, schema)


def test_sbom_schema_rejects_unknown_top_level_field() -> None:
    import jsonschema

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
    valid = {
        "sbom": {
            "artifact_uri": None,
            "built_image_digest": None,
            "package_count": 0,
            "packages_by_source": {},
            "os_packages_classification": {
                "runtime_required": 0,
                "build_only": 0,
                "convenience": 0,
                "unknown": 0,
            },
            "npm_packages_native_module_count": 0,
            "total_size_bytes": None,
            "outcome": {"kind": "skipped"},
            "confidence": "unavailable",
        }
    }
    jsonschema.validate(valid, schema)
    invalid = {**valid, "boom": 1}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, schema)
