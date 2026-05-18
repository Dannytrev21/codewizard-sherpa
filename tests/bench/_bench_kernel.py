"""Shared bench kernel for S8-03's three bench scripts (AC-8, AC-9, AC-10b).

Three bench scripts (``bench_portfolio_walltime``, ``bench_index_health_overhead``,
``bench_portfolio_walltime_hosted_runner``) duplicated:

  * baseline-JSON load
  * ratio-vs-baseline compute
  * threshold decision (comment-only vs. fail)
  * ``gh pr comment`` invocation
  * ``sys.exit`` based on the verdict

Three is the rule-of-three threshold for extraction (CLAUDE.md / S8-03 Note 17).
This module owns the pure decision (``compare_to_baseline``) and the impure
shell (``post_comment_if`` + ``exit_with_verdict``). Adding a fourth bench in
Phase 3+ requires zero edits to the kernel — compose a new ``Threshold``
instance and call ``compare_to_baseline``.

The pure / impure split mirrors the project-wide functional-core /
imperative-shell discipline (CLAUDE.md "Conventions").
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, TypeAlias


@dataclass(frozen=True, kw_only=True, slots=True)
class Threshold:
    """Threshold knobs for one bench script.

    ``comment_pct``  — ``>= comment_pct`` regression triggers a PR comment.
    ``fail_pct``     — ``>= fail_pct`` regression triggers ``Verdict.Fail``
                       (None = comment-only bench).
    ``fail_p95_s``   — ``> fail_p95_s`` p95 walltime in seconds triggers
                       ``Verdict.Fail`` independent of the regression ratio
                       (None = no absolute ceiling).

    Inclusivity: comment uses ``>= comment_pct``; regression-fail uses
    ``>= fail_pct``; p95-fail uses ``> fail_p95_s`` (strict). This matches
    ``phase-arch-design.md §Gap 2``: "≥ 100 %" and "> 360 s".
    """

    comment_pct: float
    fail_pct: float | None = None
    fail_p95_s: float | None = None


@dataclass(frozen=True, slots=True)
class Ok:
    """Verdict: no comment, no fail. Within tolerance."""

    kind: Literal["ok"] = "ok"


@dataclass(frozen=True, kw_only=True, slots=True)
class CommentOnly:
    """Verdict: post a PR comment, but do not fail the build."""

    regressions: tuple[str, ...]
    summary: str
    kind: Literal["comment_only"] = "comment_only"


@dataclass(frozen=True, kw_only=True, slots=True)
class Fail:
    """Verdict: post a PR comment AND fail the build (sys.exit(2))."""

    regressions: tuple[str, ...]
    summary: str
    kind: Literal["fail"] = "fail"


Verdict: TypeAlias = Ok | CommentOnly | Fail

# Exit codes the impure shell uses. ``2`` because bench wrappers conventionally
# reserve ``1`` for "harness error" and ``2`` for "regression threshold breached".
EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 2


def _regression_pct(measurement: float, baseline: float) -> float:
    """Return ``(measurement / baseline - 1) * 100`` as a percentage.

    Returns ``0.0`` when the baseline is zero (avoids ``ZeroDivisionError``).
    A measurement smaller than the baseline yields a negative percentage —
    callers check ``>= comment_pct`` so improvements never trigger.
    """
    if baseline == 0:
        return 0.0
    return (measurement / baseline - 1.0) * 100.0


def compare_to_baseline(
    measurements: dict[str, float],
    baseline: dict[str, float],
    thresholds: Threshold,
    *,
    p95_seconds: float | None = None,
) -> Verdict:
    """Pure decision: classify ``measurements`` vs ``baseline`` into a Verdict.

    ``measurements`` and ``baseline`` are name → seconds (or fraction) maps.
    Missing-key handling: a measurement key absent from baseline is silently
    skipped (the baseline-refresh ritual is the operator's correction).

    The function NEVER calls ``gh``, NEVER calls ``sys.exit``, NEVER touches
    the network. Composition order: regression-fail ⇒ p95-fail ⇒ comment ⇒ ok.
    """
    regressed: list[tuple[str, float]] = []
    for name, value in measurements.items():
        if name not in baseline:
            continue
        pct = _regression_pct(value, baseline[name])
        if pct >= thresholds.comment_pct:
            regressed.append((name, pct))

    fail_regression = thresholds.fail_pct is not None and any(
        p >= thresholds.fail_pct for _, p in regressed
    )
    fail_p95 = (
        thresholds.fail_p95_s is not None
        and p95_seconds is not None
        and p95_seconds > thresholds.fail_p95_s
    )

    if fail_regression or fail_p95:
        reasons = []
        if fail_regression:
            assert thresholds.fail_pct is not None
            worst = max((p for _, p in regressed), default=0.0)
            reasons.append(f"regression ≥ {thresholds.fail_pct}% (worst: {worst:.1f}%)")
        if fail_p95:
            reasons.append(f"p95 > {thresholds.fail_p95_s}s (got: {p95_seconds:.1f}s)")
        return Fail(
            regressions=tuple(f"{n}: +{p:.1f}%" for n, p in regressed),
            summary="; ".join(reasons) or "fail",
        )

    if regressed:
        return CommentOnly(
            regressions=tuple(f"{n}: +{p:.1f}%" for n, p in regressed),
            summary=f"{len(regressed)} fixture(s) regressed ≥ {thresholds.comment_pct}%",
        )

    return Ok()


def load_baseline(path: Path) -> dict[str, float]:
    """Read the measurements section of a baseline JSON.

    Baselines store ``{refreshed_at, refreshed_by, reason, measurements: {...}}``.
    The metadata header is enforced by ``test_baseline_has_metadata``; this loader
    extracts just the ``measurements`` map for the kernel's pure decision.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    measurements = raw.get("measurements")
    if not isinstance(measurements, dict):
        raise ValueError(
            f"baseline {path} missing top-level 'measurements' map; "
            "regenerate via the baseline-refresh ritual"
        )
    return {str(k): float(v) for k, v in measurements.items()}


def _is_fork_pr() -> bool:
    """Return True iff the current GH Actions context is a fork PR.

    The ``GITHUB_EVENT_PATH`` payload is the source of truth; we read it lazily
    so non-CI callers (local dev runs) get False.
    """
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    if not event_path or not Path(event_path).exists():
        return False
    try:
        payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    pr = payload.get("pull_request") or {}
    head = pr.get("head") or {}
    repo = head.get("repo") or {}
    return bool(repo.get("fork"))


def post_comment_if(verdict: Verdict, *, pr_number: str | None = None) -> bool:
    """Post a PR comment iff the verdict warrants one and we have ``gh``.

    Returns True iff a comment was actually posted. Silently no-ops on:
      * ``Verdict.Ok`` (nothing to say)
      * fork-PR detection (``pull_request.head.repo.fork == True``) — prints
        a loud ``::warning::`` so the operator sees it in the log
      * ``gh`` not on PATH (local dev)
      * absent ``pr_number`` AND missing ``GITHUB_REF`` shape — we cannot
        derive the PR

    The bench script's measurement artifact upload still runs; the operator
    can inspect ``bench-results.json`` manually for fork PRs.
    """
    if isinstance(verdict, Ok):
        return False
    if _is_fork_pr():
        sys.stderr.write(
            "::warning::Fork PR detected; bench comment skipped; "
            "measurement artifact still uploaded\n"
        )
        return False
    if shutil.which("gh") is None:
        sys.stderr.write("::warning::gh not on PATH; bench comment skipped\n")
        return False
    pr = pr_number or os.environ.get("PR_NUMBER", "")
    if not pr:
        sys.stderr.write("::warning::PR number unknown; bench comment skipped\n")
        return False
    body = _format_comment_body(verdict)
    try:
        subprocess.run(
            ["gh", "pr", "comment", pr, "--body", body],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        sys.stderr.write(f"::warning::gh pr comment failed: {exc}\n")
        return False
    return True


def _format_comment_body(verdict: Verdict) -> str:
    if isinstance(verdict, Ok):
        return ""
    prefix = "🔴 Bench FAIL" if isinstance(verdict, Fail) else "🟡 Bench regression"
    regressions = "\n".join(f"  - {r}" for r in verdict.regressions)
    return f"{prefix}: {verdict.summary}\n\n{regressions}\n"


def exit_with_verdict(verdict: Verdict) -> int:
    """Translate a verdict into a POSIX exit code.

    Returns the exit code (does NOT call ``sys.exit``; callers in tests want
    the integer to assert on). Bench scripts call ``sys.exit(exit_with_verdict(v))``
    at module-level after running the kernel.

    ``Verdict.Fail`` → ``EXIT_FAIL`` (2). ``Verdict.Ok`` and ``Verdict.CommentOnly``
    → ``EXIT_OK`` (0) (advisory — comment-only never blocks merge).
    """
    if isinstance(verdict, Fail):
        return EXIT_FAIL
    return EXIT_OK
