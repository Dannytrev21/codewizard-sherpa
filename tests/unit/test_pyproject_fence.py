"""Fence: enforce no-LLM-in-gather (ADR-0002, production ADR-0005).

The deliberate-negative tests invoke the SAME production code path as the live
test (see :mod:`codegenie._fence`). Mutating the scanner kills both. The story
that owns this file is ``docs/phases/00-bullet-tracer-foundations/stories/
S1-05-ci-fence-import-linter.md``.

Phase-4 amendment (ADR-0003 / S1-05): ``FORBIDDEN_LLM_SDKS`` *narrows honestly*
— ``anthropic`` moves out (admitted closure-wide as a runtime dep but
path-scoped at ``tests/fence/test_pyproject_fence_phase4.py`` to its single
callsite), and ``sentence-transformers`` + ``torch`` are added (so we do not
leave a hole for an alternative embeddings backend after ``fastembed`` becomes
a runtime dep). Six denied SDKs now, not five — the closure-scoped fence is
*stricter*, not relaxed. See ``phase-arch-design.md §Gap 5`` for the
authoritative correction of the stale "set is not edited" claim in
ADR-0003 §Decision / ``final-design.md §2.1``.
"""

from __future__ import annotations

import pytest

from codegenie._fence import (
    FORBIDDEN_LLM_SDKS,
    parse_runtime_dep_names_from_toml,
    scan_installed_distribution,
)

EXPECTED_FORBIDDEN_SET = frozenset(
    {
        "langgraph",
        "openai",
        "langchain",
        "transformers",
        "sentence-transformers",
        "torch",
    }
)


def test_fence_blocks_known_llm_sdks() -> None:
    # AC-4(a): live check against the actually-installed distribution.
    # Mutation guard: changing `&` to `|` in production dies here on any
    # non-empty `dev` install (pytest etc. would then count as "leaked").
    leaked = scan_installed_distribution("codewizard-sherpa")
    assert leaked == frozenset(), (
        f"LLM SDK leaked into [project].dependencies: {leaked}. "
        f"Route LLM deps through [project.optional-dependencies].agents "
        f"(ADR-0006) or path-scope per Phase-4 ADR-0003."
    )


def test_forbidden_set_is_exactly_adr_0002_closure() -> None:
    # AC-4(b): mutation guard — silently dropping `langchain` from the
    # production set dies here. After the Phase-4 ADR-0003 narrowing the set
    # is six members (anthropic moved to path-scope; sentence-transformers +
    # torch added).
    assert FORBIDDEN_LLM_SDKS == EXPECTED_FORBIDDEN_SET


@pytest.mark.parametrize("sdk", sorted(EXPECTED_FORBIDDEN_SET))
def test_fence_catches_each_planted_llm_sdk(sdk: str) -> None:
    # AC-4(c): plant ONE forbidden SDK at a time in synthetic deps; the
    # production parser MUST see it. Mutation guard: a bug that filters out
    # one SDK kills its parametrized case (6 cases, 6 independent guards).
    synthetic = f'[project]\nname = "fake"\ndependencies = ["click", "{sdk}>=0.1"]\n'
    names = parse_runtime_dep_names_from_toml(synthetic)
    assert names & FORBIDDEN_LLM_SDKS == {sdk}, (
        f"Fence check is broken — failed to catch planted `{sdk}`. Got: {names}"
    )


def test_fence_ignores_llm_sdk_when_planted_in_optional_extras() -> None:
    # AC-4(d): metamorphic complement — the SAME SDK in `optional-dependencies`
    # MUST be ignored (edge case #15). Mutation guard: a regression that
    # widens the fence to extras re-includes the planted SDK and dies.
    #
    # Phase-4 S1-05: re-planted from `anthropic` to `torch`. After the
    # narrowing `anthropic ∉ FORBIDDEN_LLM_SDKS`, so planting it here would
    # pass *vacuously* — its mutation guard would be dead. `torch` is
    # PHASE4_STILL_FORBIDDEN, so the metamorphic edge-case test keeps teeth.
    synthetic = (
        '[project]\nname = "fake"\ndependencies = ["click"]\n'
        '[project.optional-dependencies]\nagents = ["torch>=0.1"]\n'
    )
    names = parse_runtime_dep_names_from_toml(synthetic)
    assert names & FORBIDDEN_LLM_SDKS == set(), (
        f"Fence widened scope to optional-dependencies (edge case #15 violation). "
        f"Got: {names & FORBIDDEN_LLM_SDKS}"
    )


def test_fence_helper_strips_version_specifiers_and_extras_markers() -> None:
    # AC-4(e): mutation guard — a sloppy parser that compares raw `requires`
    # strings against bare names misses every version-specced or extras-
    # bracketed dep.
    synthetic = (
        '[project]\nname = "fake"\n'
        "dependencies = [\n"
        '  "openai>=0.1",\n'
        '  "langchain[all]<2.0",\n'
        '  "click; python_version >= \\"3.11\\"",\n'
        "]\n"
    )
    names = parse_runtime_dep_names_from_toml(synthetic)
    assert names == {"openai", "langchain", "click"}, (
        f"Parser must strip version specs / extras / markers. Got: {names}"
    )


def test_fence_canonicalizes_underscore_spelling() -> None:
    # AC-19: the canonicalization closes a real fence hole — `sentence_transformers`
    # (underscore form) is the IMPORT name; the DISTRIBUTION name (and the
    # FORBIDDEN_LLM_SDKS spelling) is `sentence-transformers` (hyphen). Without
    # `packaging.utils.canonicalize_name` in `_name_of`, a contributor writing
    # the underscore form in `[project.dependencies]` would slip the fence.
    # Mutation guard: deleting the `canonicalize_name` call dies here.
    synthetic = '[project]\nname = "fake"\ndependencies = ["click", "sentence_transformers>=0.1"]\n'
    names = parse_runtime_dep_names_from_toml(synthetic)
    assert names & FORBIDDEN_LLM_SDKS == {"sentence-transformers"}, (
        f"Underscore-spelled `sentence_transformers` must canonicalize to the "
        f"hyphen form `sentence-transformers` and trip the fence. Got: {names}"
    )
