"""Tests for ``NodeReflectionProbe`` (S4-06).

Grammar loading goes through the 02-ADR-0011 PyPI-wheel kernel
(:func:`codegenie.grammars.lock.language_for`). The legacy
``GrammarLoadRefused`` exception type is preserved for the grammar-
unavailable failure path.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import logging
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from codegenie.grammars.lock import GrammarLoadRefused
from codegenie.probes.base import ProbeContext, RepoSnapshot
from codegenie.probes.layer_b import node_reflection as nr
from codegenie.probes.layer_b.node_reflection import (
    _DECORATOR_DEP_TRUTH_TABLE,
    _ERROR_IDS,
    _REFLECTION_QUERIES,
    _WARNING_IDS,
    NodeReflectionProbe,
    _decorator_flags,
    _derive_confidence_impact,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
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


def _run(snapshot: RepoSnapshot, ctx: ProbeContext) -> dict[str, Any]:
    probe = NodeReflectionProbe()
    out = asyncio.run(probe.run(snapshot, ctx))
    return {
        "schema_slice": out.schema_slice,
        "confidence": out.confidence,
        "warnings": out.warnings,
        "errors": out.errors,
    }


# ---------------------------------------------------------------------------
# T-R1 — Probe contract attributes (AC-R1)
# ---------------------------------------------------------------------------


def test_probe_contract_attributes() -> None:
    probe = NodeReflectionProbe()
    assert probe.name == "node_reflection"
    assert probe.version == "0.1.0"
    assert probe.layer == "B"
    assert probe.tier == "base"
    assert probe.applies_to_languages == ["javascript", "typescript"]
    assert probe.applies_to_tasks == ["*"]
    assert probe.requires == ["language_detection"]
    assert probe.timeout_seconds == 60
    assert probe.cache_strategy == "content"
    sig = inspect.signature(NodeReflectionProbe.run)
    assert list(sig.parameters) == ["self", "repo", "ctx"]


# ---------------------------------------------------------------------------
# T-R3 — No direct lock file IO; no kernel redeclaration (AC-R2)
# ---------------------------------------------------------------------------


def test_no_direct_lockfile_io_no_kernel_redeclaration() -> None:
    """The probe imports the kernel surface; does NOT redeclare
    GrammarLoadRefused; does NOT touch ``tools/grammars.lock``
    directly; does NOT import a per-grammar PyPI package."""
    src = Path(nr.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)

    # (a) No GrammarLoadRefused class definition.
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            assert node.name != "GrammarLoadRefused", (
                "GrammarLoadRefused must be imported from the kernel, not redeclared"
            )

    # (b) No direct import of per-grammar PyPI packages.
    forbidden_imports = {"tree_sitter_typescript", "tree_sitter_javascript"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden_imports, (
                    f"probe must not import {alias.name!r} directly; "
                    f"go through codegenie.grammars.lock.language_for"
                )
        if isinstance(node, ast.ImportFrom):
            assert node.module not in forbidden_imports, (
                f"probe must not import from {node.module!r} directly"
            )

    # (c) Kernel surface IS imported.
    found_kernel_import = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "codegenie.grammars.lock":
            names = {alias.name for alias in node.names}
            assert "language_for" in names
            assert "GrammarLoadRefused" in names
            found_kernel_import = True
    assert found_kernel_import, "must import the kernel surface"

    # (d) No string literal naming ``tools/grammars``.
    assert "tools/grammars" not in src, "probe must not reference tools/grammars paths"


# ---------------------------------------------------------------------------
# T-R4 — Per-pattern detection (AC-R3)
# ---------------------------------------------------------------------------


def test_eval_usage_detected(repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext) -> None:
    (repo_root / "a.ts").write_bytes(b'const x = eval("foo");\n')
    out = _run(snapshot, ctx)
    assert out["schema_slice"]["reflection"]["eval_usage"] == 1


def test_function_constructor_detected(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    (repo_root / "a.ts").write_bytes(b'const f = new Function("return 1");\n')
    out = _run(snapshot, ctx)
    assert out["schema_slice"]["reflection"]["function_constructor_usage"] == 1


def test_dynamic_require_detected(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    (repo_root / "a.ts").write_bytes(b"const m = require(modName);\n")
    out = _run(snapshot, ctx)
    assert out["schema_slice"]["reflection"]["dynamic_require_count"] == 1


def test_dynamic_import_detected(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    (repo_root / "a.ts").write_bytes(b"const m = import(spec);\n")
    out = _run(snapshot, ctx)
    assert out["schema_slice"]["reflection"]["dynamic_import_count"] == 1


def test_prototype_manipulation_detected(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    (repo_root / "a.ts").write_bytes(b"obj.prototype.foo = 1;\nbar.__proto__ = baz;\n")
    out = _run(snapshot, ctx)
    assert out["schema_slice"]["reflection"]["prototype_manipulation_count"] >= 2


def test_decorator_detected(repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext) -> None:
    (repo_root / "a.ts").write_bytes(b"class Foo {\n  @Controller()\n  bar() {}\n}\n")
    out = _run(snapshot, ctx)
    assert out["schema_slice"]["reflection"]["decorator_usage"]["custom_decorators_detected"] >= 1


def test_env_var_count_and_code_path_affecting(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    (repo_root / "a.ts").write_bytes(
        b"if (process.env.DEBUG) { run(); }\nconst x = process.env.PORT;\n"
    )
    out = _run(snapshot, ctx)
    env = out["schema_slice"]["reflection"]["env_var_reads"]
    assert env["count"] >= 2
    assert env["code_path_affecting"] >= 1


def test_dynamic_property_access_distinct_from_string_index(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    """``obj[varName]`` counts; ``obj["literal"]`` does NOT — the index
    is a string literal, not dynamic."""
    (repo_root / "a.ts").write_bytes(b'const x = obj[varName];\nconst y = obj["literal"];\n')
    out = _run(snapshot, ctx)
    assert out["schema_slice"]["reflection"]["dynamic_property_access_count"] == 1


# ---------------------------------------------------------------------------
# T-R5 — Grammar unavailable path (AC-R8)
# ---------------------------------------------------------------------------


def test_grammar_unavailable_emits_honest_slice(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
    snapshot: RepoSnapshot,
    ctx: ProbeContext,
) -> None:
    """Simulate a kernel failure (e.g., missing grammar package). The
    probe emits ``confidence='low'`` + ``confidence_impact='high'``
    (inverted-semantics: we couldn't measure, so high impact). NO
    tree-sitter Query runs and NO ``Parser`` is constructed."""
    (repo_root / "a.ts").write_bytes(b'eval("never reached");\n')

    def _refuse(name: str) -> Any:
        raise GrammarLoadRefused(f"forced refusal for {name!r}")

    monkeypatch.setattr("codegenie.probes.layer_b.node_reflection.language_for", _refuse)

    out = _run(snapshot, ctx)
    assert out["confidence"] == "low"
    assert out["schema_slice"]["reflection"]["confidence_impact"] == "high"
    assert out["schema_slice"]["reflection"]["eval_usage"] == 0
    assert out["schema_slice"]["reflection"]["affected_files"] == []
    assert "node_reflection.grammar_unavailable" in out["errors"]


# ---------------------------------------------------------------------------
# T-R6 — Decorator usage from package.json deps (AC-R5)
# ---------------------------------------------------------------------------


def test_decorator_usage_via_package_json(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    pkg = {
        "dependencies": {"@nestjs/core": "10", "class-validator": "0.14"},
        "devDependencies": {},
    }
    (repo_root / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
    out = _run(snapshot, ctx)
    dec = out["schema_slice"]["reflection"]["decorator_usage"]
    assert dec["nestjs"] is True
    assert dec["typeorm"] is False
    assert dec["class_validator"] is True


def test_decorator_flags_helper_falsy_when_pkg_none() -> None:
    flags = _decorator_flags(None)
    assert flags == {key: False for key, _ in _DECORATOR_DEP_TRUTH_TABLE}


# ---------------------------------------------------------------------------
# T-R7/R8 — confidence_impact derivation (inverted semantics; AC-R7)
# ---------------------------------------------------------------------------


def test_eval_usage_promotes_high_confidence_impact(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    (repo_root / "a.ts").write_bytes(b'eval("x");\n')
    out = _run(snapshot, ctx)
    assert out["schema_slice"]["reflection"]["confidence_impact"] == "high"


def test_all_counts_zero_low_confidence_impact(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    """No reflection patterns + no decorator deps → low impact
    (HIGH confidence in static analysis — inverted semantics)."""
    (repo_root / "a.ts").write_bytes(b"export const x = 1;\n")
    out = _run(snapshot, ctx)
    assert out["schema_slice"]["reflection"]["confidence_impact"] == "low"


def test_function_constructor_promotes_high_confidence_impact(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    (repo_root / "a.ts").write_bytes(b'new Function("return 1");\n')
    out = _run(snapshot, ctx)
    assert out["schema_slice"]["reflection"]["confidence_impact"] == "high"


def test_derive_helper_three_arm_truth_table() -> None:
    # eval > 0 → high
    assert (
        _derive_confidence_impact({"eval_usage": 1, "function_constructor_usage": 0}, {}) == "high"
    )
    # All zero + no decorator → low
    assert (
        _derive_confidence_impact(
            {"eval_usage": 0, "function_constructor_usage": 0, "decorator": 0}, {"nestjs": False}
        )
        == "low"
    )
    # Mixed signal → medium
    assert (
        _derive_confidence_impact(
            {"eval_usage": 0, "function_constructor_usage": 0, "decorator": 5},
            {"nestjs": True},
        )
        == "medium"
    )


# ---------------------------------------------------------------------------
# AC-X4 — Warning + error IDs match ADR-0007
# ---------------------------------------------------------------------------


def test_warning_and_error_ids_match_adr_0007() -> None:
    pattern = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    for ident in _WARNING_IDS | _ERROR_IDS:
        assert pattern.match(ident), f"ADR-0007 violation: {ident!r}"


# ---------------------------------------------------------------------------
# AC-X9 — Determinism (byte-identical reruns)
# ---------------------------------------------------------------------------


def test_probe_is_deterministic_on_fixture(
    repo_root: Path, snapshot: RepoSnapshot, ctx: ProbeContext
) -> None:
    (repo_root / "a.ts").write_bytes(b'eval("x");\nif (process.env.PORT) { run(); }\n')
    (repo_root / "b.ts").write_bytes(b"obj.prototype.foo = 1;\n")
    out1 = _run(snapshot, ctx)
    out2 = _run(snapshot, ctx)
    a = json.dumps(out1["schema_slice"], sort_keys=True)
    b = json.dumps(out2["schema_slice"], sort_keys=True)
    assert a == b


# ---------------------------------------------------------------------------
# AC-X2 — Pattern catalog is Open/Closed (data not branches)
# ---------------------------------------------------------------------------


def test_reflection_queries_is_a_module_level_constant() -> None:
    """``_REFLECTION_QUERIES`` is the data-driven dispatch table —
    adding a pattern is a dict-entry, not a branch edit."""
    assert isinstance(_REFLECTION_QUERIES, Mapping)
    assert "eval_usage" in _REFLECTION_QUERIES
    assert "prototype_manipulation" in _REFLECTION_QUERIES


# ---------------------------------------------------------------------------
# Registry membership (AC-X5)
# ---------------------------------------------------------------------------


def test_probe_registered_with_medium_heaviness() -> None:
    """02-ADR-0003 requires ``heaviness="medium"`` for per-file
    tree-sitter Query workloads to mirror S4-04 parity."""
    from codegenie.probes import registry as reg

    entries = {e.cls.name: e for e in reg.default_registry.sorted_for_dispatch()}
    assert "node_reflection" in entries
    assert entries["node_reflection"].heaviness == "medium"
