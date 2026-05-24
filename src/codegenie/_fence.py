"""Fence helper — the load-bearing ADR-0002 / production-ADR-0005 enforcement.

This module is private (leading-underscore name): the only callers are
``tests/unit/test_pyproject_fence.py`` and any future CI helper that needs to
re-scan the runtime dependency closure of ``codewizard-sherpa``. Keeping the
parsing here (not in the tests) is what makes the deliberate-negative tests
mutation-resistant: both the live test and the planted-SDK tests invoke the
*same* extraction function, so any regression in the production parser kills
the canary AND the live check.

Phase-4 amendment (ADR-0003): the original five-member ``FORBIDDEN_LLM_SDKS``
set *narrows honestly* — ``anthropic`` moves out (it is a runtime dep at the
single callsite ``src/codegenie/fallback/leaf/anthropic_adapter.py``, fenced
by path-scope at ``tests/fence/test_pyproject_fence_phase4.py``) and
``sentence-transformers`` + ``torch`` are added (so the deny-set does not
leave a hole for an alternative embeddings backend after ``fastembed`` becomes
a runtime dep). Net: the closure-scoped fence is *stricter* (six denied
SDKs, not five), not relaxed. See ``phase-arch-design.md §Gap 5`` for the
authoritative correction of the (stale) "the set is not edited" claim in
ADR-0003 §Decision and ``final-design.md §2.1``.

Tarball of guarantees:

* ``FORBIDDEN_LLM_SDKS`` is the exact six-member set encoded by Phase-0
  ADR-0002 (narrowed) + Phase-4 ADR-0003 (path-scope amendment). Adding an
  SDK or further narrowing is a one-line PR with mandatory review.
* ``parse_runtime_dep_names_from_toml`` reads *only* ``[project].dependencies``
  — never ``[project.optional-dependencies]``. This is the scope-narrowing
  invariant from phase-arch-design.md §Edge cases #15.
* Version specifiers (``>=0.1``), extras (``[all]``), and environment markers
  (``; python_version >= "3.11"``) are normalised away via
  ``packaging.Requirement`` so the comparison is on bare distribution names.
* ``_name_of`` canonicalises via :func:`packaging.utils.canonicalize_name`
  (PEP 503) so ``sentence-transformers`` / ``sentence_transformers`` /
  ``Sentence.Transformers`` all resolve to the one canonical form.

See ``docs/phases/00-bullet-tracer-foundations/ADRs/0002-fence-ci-job-no-llm-in-gather.md``
and ``docs/phases/04-vuln-llm-fallback-rag/ADRs/0003-path-scoped-fence-amendment.md``
for the why.
"""

from __future__ import annotations

import tomllib
from importlib.metadata import distribution

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

FORBIDDEN_LLM_SDKS: frozenset[str] = frozenset(
    {
        "langgraph",
        "openai",
        "langchain",
        "transformers",
        "sentence-transformers",
        "torch",
    }
)
"""The exact ADR-0002 (narrowed) + ADR-0003 (admitted-via-path-scope) closure.

Six PyPI distribution names. ``anthropic`` is intentionally absent — it is a
runtime dep under the path-scoped fence at
``tests/fence/test_pyproject_fence_phase4.py`` (single callsite:
``src/codegenie/fallback/leaf/anthropic_adapter.py``). ``sentence-transformers``
and ``torch`` are added so we do not leave a hole for an alternative
embeddings backend after ``fastembed`` becomes a runtime dep.
"""


def _name_of(spec: str) -> str | None:
    """Return the canonical PyPI distribution name from a PEP 508 requirement string.

    Canonicalises via :func:`packaging.utils.canonicalize_name` (PEP 503) so a
    contributor writing ``sentence_transformers`` (underscore) or
    ``Sentence-Transformers`` in ``[project.dependencies]`` is still caught by
    a deny-set keyed on the canonical ``sentence-transformers``.

    Tolerates malformed specs (returns ``None`` instead of raising) so a single
    bad row in someone else's metadata cannot cause the fence to vanish.
    """
    try:
        name: str = Requirement(spec).name
    except InvalidRequirement:
        return None
    return canonicalize_name(name)


def parse_runtime_dep_names_from_toml(toml_text: str) -> set[str]:
    """Return the canonical names of ``[project].dependencies`` from ``toml_text``.

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
    """Return the canonical runtime ``requires`` names of an installed distribution.

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
