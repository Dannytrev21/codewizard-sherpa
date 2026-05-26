"""Phase-4 S7-02 — RAG query builder tests.

Pins the pure-function contract S5-01's retriever reads against:

* AC-FILE / AC-SHAPE — two free functions exported, signatures pinned.
* AC-FIELDS — `build` populates every Query field by named keyword.
* AC-VALUES — canonical npm/node task-class triple values.
* AC-FAILURE-MODE — `_FAILURE_MODE_DEFAULT = "build_break"`.
* AC-RENDER — `render_query_text` produces the canonical string.
* AC-DIGEST-DETERMINISM / AC-MODEL-DUMP-EQUALITY — two identical
  inputs → byte-equal Query.
* AC-PURITY — no `await`/`open`/global mutation in either function.
* AC-NO-FSTRING-IN-BUILD — `build` body uses no f-strings / string
  concatenation / `.format()`.
* AC-FENCE-IMPORT — no anthropic/chromadb/fastembed/onnxruntime
  imports.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import sys
from pathlib import Path
from types import ModuleType
from typing import Final

from codegenie.fallback.contracts import CveAdvisory, RepoContext
from codegenie.rag.models import Query
from codegenie.types.identifiers import CveId, PackageId

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
_BUILDER_PATH: Final[Path] = (
    _REPO_ROOT
    / "plugins"
    / "vulnerability-remediation--node--npm"
    / "recipes"
    / "rag_query_builder.py"
)


def _load_builder_module() -> ModuleType:
    mod_name = "_test_rag_query_builder"
    spec = importlib.util.spec_from_file_location(mod_name, _BUILDER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


_MODULE = _load_builder_module()
build = _MODULE.build
render_query_text = _MODULE.render_query_text


def _advisory(cve_id: str = "CVE-2026-1234", pkg: str = "express@1.0.0") -> CveAdvisory:
    return CveAdvisory(
        cve_id=CveId(cve_id),
        affected_package=PackageId(pkg),
        description="placeholder",
    )


def _ctx() -> RepoContext:
    return RepoContext(repo_root="/tmp/repo")


# --- AC-FILE / AC-SHAPE ---------------------------------------------------


def test_ac_file_module_exports_exactly_two_functions() -> None:
    assert set(_MODULE.__all__) == {"build", "render_query_text"}
    assert callable(_MODULE.build)
    assert callable(_MODULE.render_query_text)


def test_ac_shape_build_signature() -> None:
    sig = inspect.signature(build)
    params = list(sig.parameters)
    assert params == ["advisory", "repo_ctx"]


def test_ac_shape_render_signature() -> None:
    sig = inspect.signature(render_query_text)
    assert list(sig.parameters) == ["q"]


# --- AC-FIELDS / AC-VALUES / AC-FAILURE-MODE ------------------------------


def test_ac_fields_build_populates_every_query_field() -> None:
    q = build(_advisory(), _ctx())
    assert q.task_class == "vuln_remediation"
    assert q.language == "typescript"
    assert q.build_system == "npm"
    assert q.cve_id == "CVE-2026-1234"
    assert q.affected_package == "express@1.0.0"
    assert q.failure_mode == "build_break"


def test_ac_values_canonical_triple() -> None:
    q = build(_advisory(), _ctx())
    assert (q.task_class, q.language, q.build_system) == (
        "vuln_remediation",
        "typescript",
        "npm",
    )


def test_ac_failure_mode_default_is_build_break() -> None:
    assert _MODULE._FAILURE_MODE_DEFAULT == "build_break"


# --- AC-RENDER ------------------------------------------------------------


def test_ac_render_canonical_format() -> None:
    q = build(_advisory("CVE-2026-RENDER01", "lodash@4.17.21"), _ctx())
    text = render_query_text(q)
    expected = (
        "vuln_remediation/typescript/npm | cve=CVE-2026-RENDER01 | "
        "package=lodash@4.17.21 | failure_mode=build_break"
    )
    assert text == expected


# --- AC-DIGEST-DETERMINISM / AC-MODEL-DUMP-EQUALITY -----------------------


def test_ac_digest_determinism_two_calls_byte_equal() -> None:
    """build(adv, ctx).model_dump_json() is byte-equal across two calls."""
    a, c = _advisory(), _ctx()
    q1 = build(a, c)
    q2 = build(a, c)
    assert q1.model_dump_json() == q2.model_dump_json()


def test_ac_field_perturbation_changes_query() -> None:
    """Changing the CVE or package field changes the Query."""
    base = build(_advisory(cve_id="CVE-2026-AAA"), _ctx())
    perturbed_cve = build(_advisory(cve_id="CVE-2026-BBB"), _ctx())
    perturbed_pkg = build(_advisory(pkg="axios@1.0.0"), _ctx())
    assert base.model_dump_json() != perturbed_cve.model_dump_json()
    assert base.model_dump_json() != perturbed_pkg.model_dump_json()


# --- AC-PURITY + AC-NO-FSTRING-IN-BUILD -----------------------------------


def _build_function_ast() -> ast.AsyncFunctionDef | ast.FunctionDef:
    tree = ast.parse(_BUILDER_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == "build":
            return node
    raise AssertionError("`build` not found")


def test_ac_purity_no_await_no_global_in_build() -> None:
    fn = _build_function_ast()
    for node in ast.walk(fn):
        assert not isinstance(node, ast.Await), "no await in build"
        assert not isinstance(node, ast.Global), "no global in build"
        assert not isinstance(node, ast.Nonlocal), "no nonlocal in build"


def test_ac_no_fstring_in_build() -> None:
    fn = _build_function_ast()
    for node in ast.walk(fn):
        assert not isinstance(node, ast.JoinedStr), (
            "f-string found inside build() — text-rendering belongs in render_query_text"
        )


def test_ac_no_string_concat_in_build() -> None:
    fn = _build_function_ast()
    for node in ast.walk(fn):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            sides = (node.left, node.right)
            for side in sides:
                if isinstance(side, ast.Constant) and isinstance(side.value, str):
                    raise AssertionError(
                        "string concatenation in build() — text-rendering "
                        "belongs in render_query_text"
                    )


# --- AC-FENCE-IMPORT ------------------------------------------------------


def test_ac_fence_no_llm_sdk_imports() -> None:
    source = _BUILDER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {
        "anthropic",
        "chromadb",
        "fastembed",
        "onnxruntime",
        "openai",
        "langchain",
        "langgraph",
        "transformers",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            assert mod not in forbidden, f"forbidden import: {mod}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                assert top not in forbidden, f"forbidden import: {top}"


# --- AC-RETURN-TYPE -------------------------------------------------------


def test_ac_build_returns_query_instance() -> None:
    q = build(_advisory(), _ctx())
    assert isinstance(q, Query)
