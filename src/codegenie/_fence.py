"""Fence helper — the load-bearing ADR-0002 / production-ADR-0005 enforcement.

This module is private (leading-underscore name): the only callers are
``tests/unit/test_pyproject_fence.py`` and any future CI helper that needs to
re-scan the runtime dependency closure of ``codewizard-sherpa``. Keeping the
parsing here (not in the tests) is what makes the deliberate-negative tests
mutation-resistant: both the live test and the planted-SDK tests invoke the
*same* extraction function, so any regression in the production parser kills
the canary AND the live check.

Tarball of guarantees:

* ``FORBIDDEN_LLM_SDKS`` is the exact set encoded by ADR-0002. Adding an SDK
  is a one-line PR with mandatory review.
* ``parse_runtime_dep_names_from_toml`` reads *only* ``[project].dependencies``
  — never ``[project.optional-dependencies]``. This is the scope-narrowing
  invariant from phase-arch-design.md §Edge cases #15.
* Version specifiers (``>=0.1``), extras (``[all]``), and environment markers
  (``; python_version >= "3.11"``) are normalised away via
  ``packaging.Requirement`` so the comparison is on bare distribution names.

See ``docs/phases/00-bullet-tracer-foundations/ADRs/0002-fence-ci-job-no-llm-in-gather.md``
for the why.
"""

from __future__ import annotations

import tomllib
from importlib.metadata import distribution

from packaging.requirements import InvalidRequirement, Requirement

FORBIDDEN_LLM_SDKS: frozenset[str] = frozenset(
    {"anthropic", "langgraph", "openai", "langchain", "transformers"}
)
"""The exact ADR-0002 closure. Adding an SDK requires an ADR amendment."""


def _name_of(spec: str) -> str | None:
    """Return the lowercased distribution name from a PEP 508 requirement string.

    Tolerates malformed specs (returns ``None`` instead of raising) so a single
    bad row in someone else's metadata cannot cause the fence to vanish.
    """
    try:
        name: str = Requirement(spec).name
    except InvalidRequirement:
        return None
    return name.lower()


def parse_runtime_dep_names_from_toml(toml_text: str) -> set[str]:
    """Return the bare names of ``[project].dependencies`` from ``toml_text``.

    Scope is *strictly* ``[project].dependencies`` — extras under
    ``[project.optional-dependencies]`` are intentionally ignored. The fence
    enforces ADR-0002 only against the gather-pipeline runtime closure;
    widening to extras would break ``dev`` installs across the contributor
    base. See phase-arch-design.md §Edge cases #15.
    """
    data = tomllib.loads(toml_text)
    deps = data.get("project", {}).get("dependencies", []) or []
    return {name for spec in deps if (name := _name_of(spec)) is not None}


def requires_names_from_distribution(name: str = "codewizard-sherpa") -> set[str]:
    """Return the runtime ``requires`` names of an installed distribution.

    Entries whose environment marker contains ``extra ==`` are filtered out —
    those are optional-dependency members surfaced by ``importlib.metadata``
    but they are NOT part of the runtime closure. The fence's contract is
    ``[project].dependencies`` only.
    """
    raw = distribution(name).requires or []
    names: set[str] = set()
    for spec in raw:
        if "extra ==" in spec:
            continue
        nm = _name_of(spec)
        if nm is not None:
            names.add(nm)
    return names


def scan_installed_distribution(name: str = "codewizard-sherpa") -> frozenset[str]:
    """Return the intersection of the installed runtime closure with the SDK set.

    Empty result is the green path (ADR-0002 satisfied). Any returned member
    is a load-bearing-commitment violation and the fence CI job MUST fail.
    """
    return frozenset(requires_names_from_distribution(name) & FORBIDDEN_LLM_SDKS)
