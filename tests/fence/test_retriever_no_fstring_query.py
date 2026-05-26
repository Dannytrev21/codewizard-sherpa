"""Phase-4 S5-01 AC-3 — AST fence: ``SolvedExampleRetriever.query`` MUST
not construct a ``Query`` directly, build query text via f-strings or
``+``-concatenation, or access ``q.text``.

Mutation rejected: an executor "helpfully" inlining ``Query(...)`` or
``f"cve={advisory.id}"`` inside the dispatch fails this test loud. The
query/text construction policy lives in the *injected* builder
callables (S7-02 ships the plugin-owned production builders).
"""

from __future__ import annotations

import ast
import inspect

from codegenie.rag import retriever as retriever_module
from codegenie.rag.retriever import SolvedExampleRetriever


def _query_method_ast() -> ast.AsyncFunctionDef | ast.FunctionDef:
    tree = ast.parse(inspect.getsource(retriever_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "SolvedExampleRetriever":
            for sub in node.body:
                if isinstance(sub, ast.AsyncFunctionDef | ast.FunctionDef) and sub.name == "query":
                    return sub
    raise AssertionError("Could not locate SolvedExampleRetriever.query in AST")


def test_ac3_no_fstring_in_query() -> None:
    """No ``f""`` strings inside ``query()`` — query-text construction must
    flow through the injected ``query_text_builder`` callable."""
    fn = _query_method_ast()
    for node in ast.walk(fn):
        assert not isinstance(node, ast.JoinedStr), (
            "f-string found inside SolvedExampleRetriever.query — the "
            "injected query_text_builder owns query-text rendering."
        )


def test_ac3_no_string_concatenation_in_query() -> None:
    """No ``+`` with string operands inside ``query()`` body."""
    fn = _query_method_ast()
    for node in ast.walk(fn):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            # Look only at literal-string-operand concatenations.
            sides = (node.left, node.right)
            for side in sides:
                if isinstance(side, ast.Constant) and isinstance(side.value, str):
                    raise AssertionError(
                        "String concatenation found inside "
                        "SolvedExampleRetriever.query — the injected "
                        "query_text_builder owns query-text rendering."
                    )


def test_ac3_no_direct_query_construction_in_query() -> None:
    """No ``Query(...)`` call inside ``query()`` — the injected
    ``query_builder`` owns Query construction."""
    fn = _query_method_ast()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "Query":
                raise AssertionError(
                    "Direct Query(...) construction found inside "
                    "SolvedExampleRetriever.query — use the injected "
                    "query_builder callable."
                )


def test_ac3_no_q_dot_text_attribute_access() -> None:
    """No ``q.text`` access — the Query model carries typed fields only,
    not a ``.text`` attribute. Text comes from the injected renderer."""
    fn = _query_method_ast()
    for node in ast.walk(fn):
        if isinstance(node, ast.Attribute) and node.attr == "text":
            value = node.value
            if isinstance(value, ast.Name) and value.id == "q":
                raise AssertionError(
                    "q.text access found inside SolvedExampleRetriever.query "
                    "— text comes from query_text_builder(q)."
                )


def test_ac1_no_concrete_imports_of_chromadb_fastembed_onnxruntime() -> None:
    """AC-1 — only Protocols and injected callables; the retriever module
    must not import the concrete heavy-dep packages."""
    tree = ast.parse(inspect.getsource(retriever_module))
    forbidden = {"chromadb", "fastembed", "onnxruntime"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            assert mod not in forbidden, (
                f"retriever.py must not import {mod!r} — use Protocols only."
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                assert top not in forbidden, (
                    f"retriever.py must not import {top!r} — use Protocols only."
                )


def test_solved_example_retriever_is_frozen_dataclass() -> None:
    """The retriever is a frozen dataclass — no mutable cross-invocation state."""
    import dataclasses

    assert dataclasses.is_dataclass(SolvedExampleRetriever)
    params = SolvedExampleRetriever.__dataclass_params__  # type: ignore[attr-defined]
    assert params.frozen is True, "SolvedExampleRetriever must be frozen"
