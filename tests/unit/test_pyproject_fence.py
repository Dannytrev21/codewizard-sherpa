"""Fence: enforce no-LLM-in-gather (ADR-0002, production ADR-0005).

The deliberate-negative tests invoke the SAME production code path as the live
test (see :mod:`codegenie._fence`). Mutating the scanner kills both. The story
that owns this file is ``docs/phases/00-bullet-tracer-foundations/stories/
S1-05-ci-fence-import-linter.md``.
"""

from __future__ import annotations

import pytest

from codegenie._fence import (
    FORBIDDEN_LLM_SDKS,
    parse_runtime_dep_names_from_toml,
    scan_installed_distribution,
)

EXPECTED_FORBIDDEN_SET = frozenset(
    {"anthropic", "langgraph", "openai", "langchain", "transformers"}
)


def test_fence_blocks_known_llm_sdks() -> None:
    # AC-4(a): live check against the actually-installed distribution.
    # Mutation guard: changing `&` to `|` in production dies here on any
    # non-empty `dev` install (pytest etc. would then count as "leaked").
    leaked = scan_installed_distribution("codewizard-sherpa")
    assert leaked == frozenset(), (
        f"LLM SDK leaked into [project].dependencies: {leaked}. "
        f"Route LLM deps through [project.optional-dependencies].agents per ADR-0006."
    )


def test_forbidden_set_is_exactly_adr_0002_closure() -> None:
    # AC-4(b): mutation guard — silently dropping `langchain` from the
    # production set dies here.
    assert FORBIDDEN_LLM_SDKS == EXPECTED_FORBIDDEN_SET


@pytest.mark.parametrize("sdk", sorted(EXPECTED_FORBIDDEN_SET))
def test_fence_catches_each_planted_llm_sdk(sdk: str) -> None:
    # AC-4(c): plant ONE forbidden SDK at a time in synthetic deps; the
    # production parser MUST see it. Mutation guard: a bug that filters out
    # one SDK kills its parametrized case (5 cases, 5 independent guards).
    synthetic = f'[project]\nname = "fake"\ndependencies = ["click", "{sdk}>=0.1"]\n'
    names = parse_runtime_dep_names_from_toml(synthetic)
    assert names & FORBIDDEN_LLM_SDKS == {sdk}, (
        f"Fence check is broken — failed to catch planted `{sdk}`. Got: {names}"
    )


def test_fence_ignores_llm_sdk_when_planted_in_optional_extras() -> None:
    # AC-4(d): metamorphic complement — the SAME SDK in `optional-dependencies`
    # MUST be ignored (edge case #15). Mutation guard: a regression that
    # widens the fence to extras re-includes anthropic and dies.
    synthetic = (
        '[project]\nname = "fake"\ndependencies = ["click"]\n'
        '[project.optional-dependencies]\nagents = ["anthropic>=0.1"]\n'
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
        '  "anthropic>=0.1",\n'
        '  "langchain[all]<2.0",\n'
        '  "click; python_version >= \\"3.11\\"",\n'
        "]\n"
    )
    names = parse_runtime_dep_names_from_toml(synthetic)
    assert names == {"anthropic", "langchain", "click"}, (
        f"Parser must strip version specs / extras / markers. Got: {names}"
    )
