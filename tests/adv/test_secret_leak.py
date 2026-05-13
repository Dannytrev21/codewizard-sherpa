"""Adversarial: secret-shaped field names are rejected at TWO chokepoints.

Pass 1 — ``_ProbeOutputValidator`` at the coordinator boundary (ADR-0010).
Pass 2 — ``OutputSanitizer.scrub`` on the write path (ADR-0008, defense in
depth). The two-pass invariant is the load-bearing reason this suite exists:
pass 2 catches when pass 1 is bypassed by a future bug.

Traces to:
- ADR-0008 §Decision item 1 — same regex, two passes.
- ADR-0010 — Pydantic validator at the trust boundary; ``errors()[i]["ctx"]
  ["error"]`` surfaces the typed inner exception.
- ``phase-arch-design.md §Edge cases`` row 5 — secret-shaped field.
- ``phase-arch-design.md §Scenarios — Scenario 4`` — secret-leak path.
- S3-05 AC-13 — pinned error-string format
  ``^SecretLikelyFieldNameError: .+ at \\(.+\\)$``.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from structlog.testing import capture_logs

from codegenie.cache.store import CacheStore
from codegenie.coordinator.coordinator import Ran, gather
from codegenie.coordinator.validator import _ProbeOutputValidator
from codegenie.errors import SecretLikelyFieldNameError
from codegenie.output.sanitizer import OutputSanitizer
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot, Task
from codegenie.probes.language_detection import LanguageDetectionProbe

_SECRET_ERROR_RE = re.compile(r"^SecretLikelyFieldNameError: .+ at \(.+\)$")


def _unwrap_typed(exc: ValidationError) -> BaseException | None:
    """Pydantic v2 wraps validator exceptions; return the original typed error.

    Mirrors ``tests/unit/test_probe_output_validator.py::_unwrap_typed_error``
    (lines 168-180). Inline (not imported) — cross-test-dir helper imports
    are discouraged per the story §Notes for the implementer.
    """
    for e in exc.errors():
        ctx = e.get("ctx") or {}
        err = ctx.get("error")
        if isinstance(err, BaseException):
            return err
    return exc.__cause__


# ---------------------------------------------------------------------------
# AC-4a — top-level secret key direct-rejection by the validator
# ---------------------------------------------------------------------------


def test_secret_field_rejected_by_validator_top_level() -> None:
    """
    Pins: a secret-shaped key at the top of ``schema_slice`` raises
          ``ValidationError`` whose typed inner error (via
          ``errors()[0]['ctx']['error']``) is ``SecretLikelyFieldNameError``.
    Traces to: ADR-0010 §Decision; validator.py:108-109.
    Catches: a regression that removed the ``SECRET_FIELD_PATTERN.search(k)``
             check on dict keys — the validator would accept the secret-shaped
             field and the typed-error assertion would fail.
    """
    with pytest.raises(ValidationError) as ei:
        _ProbeOutputValidator(
            schema_slice={"github_token": "ghp_AAAAAAAAAA"},
            confidence="high",
        )
    typed = _unwrap_typed(ei.value)
    assert isinstance(typed, SecretLikelyFieldNameError), (
        f"expected SecretLikelyFieldNameError; got {type(typed).__name__}: {typed!r}"
    )


# ---------------------------------------------------------------------------
# AC-4b — secret key at depth 3 inside a list-of-dicts
# ---------------------------------------------------------------------------


def test_secret_field_rejected_by_validator_at_depth_3_via_list() -> None:
    """
    Pins: the walker descends through dicts AND lists; a secret key inside
          ``{a: {b: [{github_token: ...}]}}`` still raises. Mirrors
          ``tests/unit/test_probe_output_validator.py::
          test_secret_key_at_depth_3_via_list_rejected`` in the adversarial
          file so a reviewer doesn't have to cross-walk to /unit/ to verify
          list-traversal coverage.
    Traces to: ADR-0010; validator.py:117-125 (list branch of
          ``_walk_and_enforce``).
    Catches: a regression that narrowed the recursion to dicts only (e.g.,
             dropping the ``elif isinstance(node, list):`` branch) — the
             nested secret would slip through and the typed-error assertion
             would fail.
    """
    with pytest.raises(ValidationError) as ei:
        _ProbeOutputValidator(
            schema_slice={"a": {"b": [{"github_token": "ghp_AAAAAAAAAA"}]}},
            confidence="high",
        )
    typed = _unwrap_typed(ei.value)
    assert isinstance(typed, SecretLikelyFieldNameError)


# ---------------------------------------------------------------------------
# Shared synthetic probe — NOT @register_probe-decorated.
# ---------------------------------------------------------------------------


class _SecretLeakingProbe(Probe):
    """One-off probe that emits a secret-shaped key.

    Intentionally NOT decorated with ``@register_probe`` — registering it
    would mutate ``codegenie.probes.registry.default_registry``, polluting
    the global default for all subsequent tests in the run. Instantiated
    explicitly and passed to ``coordinator.gather(probes=[...])``.
    """

    name: str = "_secret_leak"
    version: str = "0.0.0"
    layer = "A"
    tier = "task_specific"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    declared_inputs: list[str] = []
    timeout_seconds: int = 10
    cache_strategy: str = "none"

    def applies(self, repo: RepoSnapshot, task: Task) -> bool:
        return True

    def cache_key(self, repo: RepoSnapshot, task: Task) -> str:
        return f"sha256:{self.name}"

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        return ProbeOutput(
            schema_slice={"github_token": "ghp_AAAAAAAAAA"},
            raw_artifacts=[],
            confidence="high",
            duration_ms=0,
            warnings=[],
            errors=[],
        )


def _make_snapshot(repo_root: Path) -> RepoSnapshot:
    return RepoSnapshot(
        root=repo_root.resolve(),
        git_commit=None,
        detected_languages={},
        config={},
    )


def _make_task() -> Task:
    return Task(type="__bullet_tracer__", options={})


def _make_config() -> SimpleNamespace:
    return SimpleNamespace(max_concurrent_probes=4, cache_ttl_hours=24)


# ---------------------------------------------------------------------------
# AC-4c — coordinator-boundary rejection (validator path)
# ---------------------------------------------------------------------------


def test_secret_leaking_probe_caught_at_coordinator_boundary(tmp_path: Path) -> None:
    """
    Pins: a synthetic probe emitting a secret-shaped key is caught at the
          coordinator boundary by ``_ProbeOutputValidator``; the probe is
          marked failed with confidence "low"; the gather continues (per
          ADR-0009); the cache does NOT persist the failed probe's output
          (``coordinator.py:372`` — ``if not sanitized.errors: cache.put``).
    Traces to: ADR-0010; ADR-0009; phase-arch-design.md §Edge cases row 5;
          §Scenarios — Scenario 4. Error-string regex pinned by S3-05 AC-13.
    Catches:
      - A regression that removed the validator call at
        ``coordinator.py:322`` — the synthetic probe's output would land in
        ``Ran(output=...)`` with empty ``errors`` and the regex assertion
        would fail.
      - A regression that dropped the ``at (path)`` suffix from
        ``_format_secret_error`` — the regex match would fail.
      - A regression that wrote failed probe outputs to the cache — the
        cache-side-effect assertion would catch the literal "github_token"
        in a blob.
    """
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "cache"

    snapshot = _make_snapshot(repo_root)
    task = _make_task()
    config = _make_config()
    cache = CacheStore(cache_dir=cache_root, ttl_hours=24)
    sanitizer = OutputSanitizer()
    leaker = _SecretLeakingProbe()
    prelude = LanguageDetectionProbe()

    with capture_logs() as logs:
        result = asyncio.run(gather(snapshot, task, [leaker, prelude], config, cache, sanitizer))

    # (1) The probe ran (cache miss + validator-caught failure).
    exe = result.executions["_secret_leak"]
    assert isinstance(exe, Ran), (
        f"expected Ran (validator caught at the boundary); got {type(exe).__name__}"
    )
    assert exe.output.confidence == "low"
    assert exe.output.errors, "validator must have populated errors[]"
    assert _SECRET_ERROR_RE.match(exe.output.errors[0]), (
        f"error-string format drift (S3-05 AC-13): {exe.output.errors[0]!r}"
    )

    # (2) probe.failure event emitted with regex-matching reason.
    failures = [
        e for e in logs if e.get("event") == "probe.failure" and e.get("probe") == "_secret_leak"
    ]
    assert len(failures) == 1, (
        f"expected exactly 1 probe.failure event for _secret_leak; got {failures!r}"
    )
    reason = failures[0].get("reason", "")
    assert _SECRET_ERROR_RE.match(reason), (
        f"probe.failure 'reason' drifted from _format_secret_error: {reason!r}"
    )

    # (3) Cache-side-effect invariant — failed probe is NEVER cached
    # (coordinator.py:372). Walk every blob in the cache dir and assert no
    # blob carries the literal "github_token".
    cache_blobs = list(cache_root.rglob("*.json"))
    for blob in cache_blobs:
        body = blob.read_text()
        assert "github_token" not in body, (
            f"failed probe's output leaked into cache blob: {blob}\n{body[:200]}"
        )

    # (4) Surviving prelude probe (LanguageDetectionProbe) succeeded —
    # gather returned a result, ADR-0009's "at-least-one-survived" gate held.
    assert "language_detection" in result.executions


# ---------------------------------------------------------------------------
# AC-4d — defense-in-depth: sanitizer catches when validator is bypassed
# ---------------------------------------------------------------------------


def test_secret_leak_defense_in_depth_via_sanitizer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Pins: bypassing ``_ProbeOutputValidator`` (simulating a future bug that
          routes around the trust boundary) does NOT let the secret-shaped
          key survive to disk — ``OutputSanitizer.scrub`` raises
          ``SecretLikelyFieldNameError`` and the gather aborts before any
          byte reaches the writer.
    Traces to: ADR-0008 §Decision item 1; phase-arch-design.md §Edge cases
          row 5.
    Catches: a regression that removed pass 1 from ``sanitizer.py:159`` —
             with the validator neutralized, there would be no second wall;
             the gather would complete and the secret would land in
             ``schema_slice``; the on-disk assertion would catch it.
    """
    # Neutralize the validator's pass-1 check to simulate the regression
    # scenario ADR-0008 §Decision item 1 explicitly names ("a future bug
    # routes around the validator"). ``model_validate`` is a classmethod on
    # BaseModel; replace it with a no-op classmethod for the test scope.
    monkeypatch.setattr(
        "codegenie.coordinator.validator._ProbeOutputValidator.model_validate",
        classmethod(lambda cls, *a, **kw: None),
    )

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "cache"

    snapshot = _make_snapshot(repo_root)
    task = _make_task()
    config = _make_config()
    cache = CacheStore(cache_dir=cache_root, ttl_hours=24)
    sanitizer = OutputSanitizer()
    leaker = _SecretLeakingProbe()
    prelude = LanguageDetectionProbe()

    with capture_logs() as logs:
        # The sanitizer's raise is uncaught by ``_dispatch_one`` (no
        # try/except around ``sanitizer.scrub`` at coordinator.py:354) — it
        # propagates out through ``asyncio.gather`` and out of ``gather()``.
        # If a future PR adds a try/except that downgrades to
        # ``ProbeOutput.errors``, this assertion will need to change to the
        # "catch-and-degrade" form (either is acceptable per the story —
        # the structural invariant is "the secret never reaches disk").
        with pytest.raises(SecretLikelyFieldNameError):
            asyncio.run(gather(snapshot, task, [leaker, prelude], config, cache, sanitizer))

    # (1) sanitizer.secret.rejected event was emitted with key="github_token"
    # (sanitizer.py:156 fires immediately before the raise).
    sanitizer_events = [e for e in logs if e.get("event") == "sanitizer.secret.rejected"]
    assert len(sanitizer_events) >= 1, (
        f"sanitizer pass-1 did not emit its rejection event; logs={logs!r}"
    )
    assert sanitizer_events[0].get("key") == "github_token", (
        f"event key drifted: {sanitizer_events[0]!r}"
    )

    # (2) Nothing containing "github_token" was persisted to disk anywhere
    # under tmp_path (writer didn't fire; cache.put didn't fire).
    for yaml_file in tmp_path.rglob("repo-context.yaml"):
        assert "github_token" not in yaml_file.read_text(), (
            f"secret-shaped key survived to disk: {yaml_file}"
        )
    for blob in cache_root.rglob("*.json"):
        assert "github_token" not in blob.read_text(), (
            f"secret-shaped key survived to cache blob: {blob}"
        )
