"""Deliberately-incomplete match over ConventionRule — failure target for
S2-02 AC-9 compile-time half. NEVER imported at runtime; invoked only as
input to ``python -m mypy --strict`` inside the
``tests/unit/conventions/test_apply_match_is_exhaustive_compile_time.py``.

Pin to ADR-0033 §4: every consumer of the ``ConventionRule`` discriminated
union MUST close its ``match`` with ``assert_never(rule)``. The
``warn_unreachable = true`` repo-wide setting turns this from a runtime
catch into a mypy build-failure.
"""

from __future__ import annotations

from typing import assert_never

from codegenie.conventions.model import (
    ConventionRule,
    ConventionRuleDockerfilePattern,
    ConventionRuleDockerfilePatternInverted,
    ConventionRuleFilePattern,
)


def describe(rule: ConventionRule) -> str:
    match rule:
        case ConventionRuleDockerfilePattern():
            return "dockerfile_pattern"
        case ConventionRuleDockerfilePatternInverted():
            return "dockerfile_pattern_inverted"
        case ConventionRuleFilePattern():
            return "file_pattern"
        # case ConventionRuleMissingFile(): intentionally omitted — the
        # warn_unreachable trigger.
    assert_never(rule)
