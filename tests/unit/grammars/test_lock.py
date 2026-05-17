"""Tests for ``codegenie.grammars.lock`` (02-ADR-0011 PyPI-wheel kernel).

The kernel is the single chokepoint every probe that needs a
tree-sitter ``Language`` calls through. These tests pin:

1. The kernel returns a usable ``Language`` for every supported name.
2. Memoization holds — repeat calls return the same ``Language``.
3. Unknown language names raise :class:`GrammarLoadRefused`.
4. A missing grammar package surfaces as :class:`GrammarLoadRefused`
   (the typed exception is the single-branch surface callers handle).

The legacy BLAKE3-of-binary tests were removed in 02-ADR-0011 §Consequences.
"""

from __future__ import annotations

import sys
from typing import get_args

import pytest

from codegenie.grammars.lock import (
    GrammarLoadRefused,
    SupportedLanguage,
    _build_language,
    language_for,
    supported_languages,
)


@pytest.fixture(autouse=True)
def _reset_kernel_memo() -> None:
    """Each test starts with an empty per-language cache."""
    _build_language.cache_clear()
    yield
    _build_language.cache_clear()


def test_supported_languages_matches_literal_type() -> None:
    """``SupportedLanguage`` literal arms and the dispatch table must agree —
    drift between the two breaks mypy's static admission check."""
    literal_arms = set(get_args(SupportedLanguage))
    assert set(supported_languages()) == literal_arms


@pytest.mark.parametrize("name", sorted(get_args(SupportedLanguage)))
def test_language_for_returns_usable_language(name: str) -> None:
    from tree_sitter import Language

    lang = language_for(name)  # type: ignore[arg-type]
    assert isinstance(lang, Language)


def test_language_for_is_memoized() -> None:
    a = language_for("typescript")
    b = language_for("typescript")
    assert a is b


def test_language_for_rejects_unknown_language() -> None:
    with pytest.raises(GrammarLoadRefused, match=r"unsupported language='elixir'"):
        language_for("elixir")  # type: ignore[arg-type]


def test_language_for_surfaces_missing_grammar_package_as_grammar_load_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate a closure-regression where ``tree_sitter_typescript`` is
    unavailable — the kernel surfaces the missing dep as
    :class:`GrammarLoadRefused`, not :class:`ImportError`. Single-branch
    handling is the contract callers depend on."""
    monkeypatch.setitem(sys.modules, "tree_sitter_typescript", None)
    with pytest.raises(GrammarLoadRefused, match=r"tree_sitter_typescript.*missing"):
        language_for("typescript")


def test_language_for_surfaces_factory_drift_as_grammar_load_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate the grammar package losing the capsule factory (upstream
    rename or layout change). Surfaces as :class:`GrammarLoadRefused` —
    same single-branch contract."""
    import tree_sitter_javascript as tsjs

    monkeypatch.delattr(tsjs, "language", raising=False)
    with pytest.raises(GrammarLoadRefused, match=r"did not expose"):
        language_for("javascript")


def test_grammar_load_refused_subclasses_runtime_error() -> None:
    """RuntimeError lineage: existing callers that catch ``RuntimeError``
    (e.g., probe-side defensive code) still trap the kernel's failure."""
    assert issubclass(GrammarLoadRefused, RuntimeError)
