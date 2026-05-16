"""``Catalog`` + module-level ``_apply_*`` helpers — Phase 2 S2-02.

``Catalog`` is the validated bag of :data:`ConventionRule` records.
``Catalog.apply(repo)`` is a thin list comprehension over module-level
:func:`_apply_one`, which dispatches via an exhaustive ``match`` over the
discriminator with ``assert_never`` on the impossible branch.

The four ``_apply_<kind>`` helpers are independent module-level functions —
NOT methods on :class:`Catalog`, NOT a shared ``ScannerRunner`` (final-design
row 7 explicitly rejects the abstraction at the four-helper count). Each
helper reads the ``RepoSnapshot`` at ``repo.root / relpath`` via the local
:mod:`codegenie.conventions._io` capped reader; the snapshot is the I/O
boundary so ``apply`` is pure once the snapshot is fixed.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
  §"Component design" #10, §"Design patterns applied" rows 5, 8.
- ``docs/production/adrs/0033-domain-modeling-discipline.md`` §3, §4 —
  exhaustive ``match`` with ``assert_never``.
- ``docs/phases/00-bullet-tracer-foundations/ADRs/0007-frozen-probe-contract.md``
  — ``RepoSnapshot`` frozen; helpers read at boundary, not through a new
  method on the contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import assert_never

from pydantic import BaseModel, ConfigDict, PrivateAttr

from codegenie.conventions._io import read_capped_text
from codegenie.conventions.model import (
    ConventionResult,
    ConventionRule,
    ConventionRuleDockerfilePattern,
    ConventionRuleDockerfilePatternInverted,
    ConventionRuleFilePattern,
    ConventionRuleMissingFile,
    Fail,
    NotApplicable,
    Pass,
)
from codegenie.probes.base import RepoSnapshot

__all__ = ["Catalog"]


_DOCKERFILE = "Dockerfile"
_REASON_NO_DOCKERFILE = "no_dockerfile_present"
_REASON_GLOB_EMPTY = "file_glob_no_matches"


class Catalog(BaseModel):
    """Validated bag of convention rules.

    ``apply`` is pure given a fixed :class:`RepoSnapshot`: the first call
    against a given snapshot reads the repo files; subsequent calls against
    the *same* snapshot instance return the cached result list and perform
    zero repo I/O (story §"Goal" Invariant 7, AC-12). The cache keys on
    ``id(repo)`` — handing :meth:`apply` a fresh snapshot wires a fresh
    evaluation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rules: list[ConventionRule]
    # Memo keyed by ``id(repo)`` so two consecutive calls with the same
    # snapshot reuse the first call's results (zero repo I/O on second).
    # ``PrivateAttr`` is excluded from serialization, equality, and the
    # ``frozen=True`` write-block.
    _memo: dict[int, list[ConventionResult]] = PrivateAttr(default_factory=dict)

    def apply(self, repo: RepoSnapshot) -> list[ConventionResult]:
        key = id(repo)
        cached = self._memo.get(key)
        if cached is not None:
            return cached
        results = [_apply_one(rule, repo) for rule in self.rules]
        self._memo[key] = results
        return results


# ---------------------------------------------------------------------------
# Module-level dispatcher — exhaustive ``match`` with ``assert_never``.
# Module-level (NOT a method on ``Catalog``) so tests can call it with an
# imposter without constructing a synthetic rule Pydantic would reject.
# ---------------------------------------------------------------------------


def _apply_one(rule: ConventionRule, repo: RepoSnapshot) -> ConventionResult:
    match rule:
        case ConventionRuleDockerfilePattern():
            return _apply_dockerfile_pattern(rule, repo)
        case ConventionRuleDockerfilePatternInverted():
            return _apply_dockerfile_pattern_inverted(rule, repo)
        case ConventionRuleFilePattern():
            return _apply_file_pattern(rule, repo)
        case ConventionRuleMissingFile():
            return _apply_missing_file(rule, repo)
        case _ as unreachable:
            assert_never(unreachable)


# ---------------------------------------------------------------------------
# Per-kind helpers. Independent bodies — NOT wrappers over each other (the
# inverted variant in particular MUST NOT call into the non-inverted helper;
# AC-5a AST source-scan enforces this).
# ---------------------------------------------------------------------------


def _apply_dockerfile_pattern(
    rule: ConventionRuleDockerfilePattern, repo: RepoSnapshot
) -> ConventionResult:
    dockerfile = repo.root / _DOCKERFILE
    if not dockerfile.is_file():
        return NotApplicable(rule_id=rule.id, reason=_REASON_NO_DOCKERFILE)
    contents = read_capped_text(dockerfile)
    if contents is None:
        return NotApplicable(rule_id=rule.id, reason=_REASON_NO_DOCKERFILE)
    if rule._compiled_pattern.search(contents) is not None:
        return Pass(rule_id=rule.id)
    return Fail(rule_id=rule.id, evidence="pattern not found in Dockerfile")


def _apply_dockerfile_pattern_inverted(
    rule: ConventionRuleDockerfilePatternInverted, repo: RepoSnapshot
) -> ConventionResult:
    # Independent body — must NOT delegate to ``_apply_dockerfile_pattern``
    # (AC-5a). Negation lives here, not as a wrapper that flips Pass/Fail.
    dockerfile = repo.root / _DOCKERFILE
    if not dockerfile.is_file():
        return NotApplicable(rule_id=rule.id, reason=_REASON_NO_DOCKERFILE)
    contents = read_capped_text(dockerfile)
    if contents is None:
        return NotApplicable(rule_id=rule.id, reason=_REASON_NO_DOCKERFILE)
    if rule._compiled_pattern.search(contents) is not None:
        return Fail(rule_id=rule.id, evidence="forbidden pattern present in Dockerfile")
    return Pass(rule_id=rule.id)


def _apply_file_pattern(rule: ConventionRuleFilePattern, repo: RepoSnapshot) -> ConventionResult:
    matches = _sorted_glob(repo.root, rule.file_glob)
    if not matches:
        return NotApplicable(rule_id=rule.id, reason=_REASON_GLOB_EMPTY)
    for path in matches:
        contents = read_capped_text(path)
        if contents is None or rule._compiled_pattern.search(contents) is None:
            relpath = path.relative_to(repo.root).as_posix()
            return Fail(
                rule_id=rule.id,
                evidence=f"{relpath}: pattern not found",
            )
    return Pass(rule_id=rule.id)


def _apply_missing_file(rule: ConventionRuleMissingFile, repo: RepoSnapshot) -> ConventionResult:
    # ``missing_file`` names the assertion: the rule PASSES when no file
    # matches the glob, and FAILS when a file is present.
    matches = _sorted_glob(repo.root, rule.file_glob)
    if not matches:
        return Pass(rule_id=rule.id)
    relpath = matches[0].relative_to(repo.root).as_posix()
    return Fail(
        rule_id=rule.id,
        evidence=f"unexpected file present: {relpath}",
    )


# ---------------------------------------------------------------------------
# Pure helper.
# ---------------------------------------------------------------------------


def _sorted_glob(root: Path, file_glob: str) -> list[Path]:
    """Deterministic glob over ``root`` excluding only regular files.

    Sorted by ``relative_to(root).as_posix()`` so iteration order is
    deterministic across xfs / ext4 / APFS.
    """
    return sorted(
        (p for p in root.glob(file_glob) if p.is_file()),
        key=lambda p: p.relative_to(root).as_posix(),
    )
