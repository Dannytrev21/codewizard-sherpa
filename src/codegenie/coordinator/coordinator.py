"""Coordinator dispatch path — async-bounded probe orchestration (S3-05).

ADRs honored: ADR-0005 (async from day one + Semaphore bound + 100 ms grace),
ADR-0007 (probe contract frozen — budgets/validators live coordinator-side),
ADR-0008 (output sanitizer is the single byte path), ADR-0009 (tagged-union
``ProbeExecution`` + cache-hit short-circuit), ADR-0010 (Pydantic validator
is an internal trust boundary, lazy-imported).

Type-flow on cache miss
-----------------------
``probe.applies → cache.key_for → cache.get → probe.run → ProbeOutput →
_ProbeOutputValidator.model_validate → OutputSanitizer.scrub →
SanitizedProbeOutput → cache.put → Ran(SanitizedProbeOutput)``.

Type-flow on cache hit
----------------------
``probe.applies → cache.key_for → cache.get → ProbeOutput →
SanitizedProbeOutput(**asdict(...)) → CacheHit(SanitizedProbeOutput, key)``.
The validator and sanitizer are skipped on hit because the cached blob is
already the post-sanitize form (S3-03's ``sanitizer.py:50`` declares the
field set "mirrors ProbeOutput field-for-field").

Prelude pass (Gap 4)
--------------------
Probes are partitioned by ``tier``: every ``tier == "base"`` probe runs
first (Phase 0's :class:`LanguageDetectionProbe`, S4-01); their merged
``language_stack.counts`` lands in an enriched snapshot via
``dataclasses.replace(snapshot, detected_languages=counts)``. The remaining
probes dispatch against the enriched snapshot. If every base probe fails,
skips, or omits the ``language_stack.counts`` key, the coordinator emits a
``prelude.degraded`` structlog event and dispatches the second pass against
the original (empty-counts) snapshot — fail-loud surface per Rule 12. The
single load-bearing line is the ``dataclasses.replace`` call; resist
building a generalized DAG scheduler (phase-arch-design §Step 3 — risks).

Resource budget (Gap 3)
-----------------------
The coordinator reads ``getattr(probe, "declared_resource_budget",
DEFAULT_RESOURCE_BUDGET)``. ``wall_clock_s`` combines with
``probe.timeout_seconds`` via ``min(...)`` — the tighter window wins.
``raw_artifact_mb`` is enforced via :class:`BudgetingContext.report_bytes`
on the per-dispatch context object the probe receives. ``rss_mb`` is
**advisory** in Phase 0: a peak crossing emits ``probe.rss.warn`` but does
NOT mark the probe failed (Gap 3 hard enforcement is deferred to Phase 14).

Run-id binding
--------------
Each :func:`gather` call generates a 16-hex ``run_id`` once and binds it via
``structlog.contextvars.bind_contextvars`` so every emitted event carries
``run_id=<...>``. The binding is cleared in a ``finally`` so subsequent
event loops in the same process see fresh state.
"""

from __future__ import annotations

import asyncio
import dataclasses
import os
import secrets
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from codegenie.cache.store import CacheStore
from codegenie.coordinator.budget import (
    DEFAULT_RESOURCE_BUDGET,
    BudgetingContext,
    ResourceBudget,
)
from codegenie.coordinator.input_snapshot import (
    compute_input_snapshot,
    make_parsed_manifest_adapter,
)
from codegenie.coordinator.parsed_manifest_memo import ParsedManifestMemo
from codegenie.errors import ProbeBudgetExceeded
from codegenie.output.sanitizer import OutputSanitizer, SanitizedProbeOutput
from codegenie.probes.base import InputFingerprint, Probe, ProbeOutput, RepoSnapshot, Task

if TYPE_CHECKING:
    pass

__all__ = [
    "CacheHit",
    "GatherResult",
    "ProbeExecution",
    "Ran",
    "Skipped",
    "gather",
]

_log = structlog.get_logger(__name__)
_TIMEOUT_GRACE_S: float = 0.1


@dataclass(frozen=True)
class Ran:
    """Probe ran (success OR failure-isolated). Carries the post-sanitize output
    and the SHA-256 cache key ``CacheStore.key_for`` returned for this dispatch.

    The ``key`` field is the **audit anchor** S3-06's ``AuditWriter`` reads
    directly — re-deriving the key at audit-write time is forbidden because
    that would record *what we'd ask for now*, not *what the coordinator
    actually asked* (which may differ if upstream probe metadata drifted
    between dispatch and audit-record write). ADR-0004 §Consequences.
    """

    output: SanitizedProbeOutput
    key: str


@dataclass(frozen=True)
class CacheHit:
    """Probe was answered from the cache. ``key`` is the SHA-256 identity
    tuple :func:`CacheStore.key_for` returned (audit anchor — S3-06 reads it)."""

    output: SanitizedProbeOutput
    key: str


@dataclass(frozen=True)
class Skipped:
    """Probe was filtered out by ``applies()``. No output, no cache traffic."""

    reason: str


ProbeExecution = Ran | CacheHit | Skipped


@dataclass(frozen=True)
class GatherResult:
    """Result of one :func:`gather` call.

    ``executions`` carries one entry per dispatched probe (regardless of
    outcome); ``outputs`` carries one entry only for probes whose execution
    is :class:`Ran` or :class:`CacheHit`. ``Skipped`` probes contribute no
    ``outputs`` entry — the CLI's exit-code policy (arch line 483) reads
    ``outputs`` accordingly.
    """

    outputs: dict[str, SanitizedProbeOutput]
    executions: dict[str, ProbeExecution]


def _sample_rss_mb() -> int:
    """Return current process peak RSS in MB. Test-monkeypatchable.

    ``ru_maxrss`` is in KB on Linux and bytes on macOS — normalize both to
    MB. Windows lacks ``resource`` entirely; return ``0`` there (the RSS
    check is advisory anyway).
    """
    try:
        import resource
    except ImportError:
        return 0
    ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return int(ru / divisor)


def _kill_tracked_subprocesses() -> None:
    """SIGKILL any in-flight subprocess registered in ``exec._RUNNING_PROCS``.

    The weakref table mutates from the GC; snapshot it before iterating.
    """
    import codegenie.exec as exec_mod

    for _pid, proc in list(exec_mod._RUNNING_PROCS.items()):
        if proc.returncode is None:
            try:
                proc.kill()
            except (ProcessLookupError, AttributeError):
                pass


def _format_secret_error(exc: Exception) -> str:
    """Unwrap a Pydantic ``ValidationError`` produced by ``_ProbeOutputValidator``.

    Validator raises :class:`PydanticCustomError` with
    ``ctx={"error": SecretLikelyFieldNameError(...), "key": ..., "path": ...}``;
    Pydantic wraps in ``ValidationError``. We surface the typed inner
    exception with its tuple ``path`` for grep-friendly log scanning. The
    error-string regex ``^SecretLikelyFieldNameError: .+ at \\(.+\\)$`` is
    pinned in S3-05 AC-13.
    """
    try:
        errors_method = getattr(exc, "errors", None)
        if not callable(errors_method):
            raise AttributeError
        ctx_raw: Any = errors_method()[0].get("ctx", {})
        if not isinstance(ctx_raw, dict):
            raise TypeError
        inner = ctx_raw.get("error")
        if inner is None:
            raise KeyError
        inner_args: tuple[Any, ...] = tuple(getattr(inner, "args", ()))
        key = inner_args[0] if inner_args else "<unknown>"
        path = inner_args[1] if len(inner_args) > 1 else (key,)
        return f"SecretLikelyFieldNameError: {key} at {path}"
    except (AttributeError, IndexError, KeyError, TypeError):
        return f"SecretLikelyFieldNameError: <unwrap-failed> at ({type(exc).__name__},)"


def _build_failure_output(error_str: str, duration_ms: int) -> ProbeOutput:
    return ProbeOutput(
        schema_slice={},
        raw_artifacts=[],
        confidence="low",
        duration_ms=duration_ms,
        warnings=[],
        errors=[error_str],
    )


def _isolated_snapshot(snap: RepoSnapshot) -> RepoSnapshot:
    """Return a per-dispatch snapshot copy whose mutable fields are owned.

    AC-18 — a probe mutating ``snapshot.detected_languages`` must NOT leak
    into a sibling probe's view. ``dataclasses.replace`` alone produces a
    fresh ``RepoSnapshot`` but its mutable fields would still be shared
    references — we copy the two mutable dicts explicitly.
    """
    return dataclasses.replace(
        snap,
        detected_languages=dict(snap.detected_languages),
        config=dict(snap.config),
    )


def _make_probe_context(
    workspace: Path,
    raw_artifact_mb: int,
    *,
    parsed_manifest: Callable[[Path], Mapping[str, Any] | None] | None = None,
    input_snapshot: frozenset[InputFingerprint] | None = None,
) -> BudgetingContext:
    """Construct the per-dispatch context object the probe receives.

    Phase 0 passes the :class:`BudgetingContext` directly so a probe can
    call ``ctx.report_bytes(n)``. The ``workspace`` attribute remains a
    plain :class:`Path` (ADR-0007). S1-07 (ADR-0002) threads
    ``parsed_manifest`` — the per-gather :class:`ParsedManifestMemo`'s
    ``.get`` bound method — onto the ctx so allowlisted JSON manifests
    parse once per gather. S1-08 threads ``input_snapshot`` — the
    pre-dispatch fingerprint set computed by
    :func:`codegenie.coordinator.input_snapshot.compute_input_snapshot` —
    so the cache-key/parse coherence required by Gap 1 holds across the
    full gather.
    """
    return BudgetingContext(
        workspace=workspace,
        raw_artifact_mb=raw_artifact_mb,
        parsed_manifest=parsed_manifest,
        input_snapshot=input_snapshot,
    )


def _extract_language_counts(schema_slice: dict[str, Any]) -> dict[str, int] | None:
    """Return the ``language_stack.counts`` slice if a prelude probe produced
    one, else ``None``. Empty dicts and absent keys both yield ``None`` so
    the prelude-degraded path triggers consistently (AC-17)."""
    lang_stack = schema_slice.get("language_stack", {})
    if not isinstance(lang_stack, dict):
        return None
    counts = lang_stack.get("counts")
    if not isinstance(counts, dict) or not counts:
        return None
    return {str(k): int(v) for k, v in counts.items()}


async def _dispatch_one(
    probe: Probe,
    snapshot: RepoSnapshot,
    task: Task,
    sem: asyncio.Semaphore,
    cache: CacheStore,
    sanitizer: OutputSanitizer,
    memo: ParsedManifestMemo,
) -> tuple[str, SanitizedProbeOutput | None, ProbeExecution]:
    """Run a single probe end-to-end. Returns ``(name, output_or_none, execution)``.

    Order: ``applies → cache.key_for → cache.get → run → validate → scrub →
    cache.put``. Cache hit short-circuits at step 3.
    """
    async with sem:
        run_id = structlog.contextvars.get_contextvars().get("run_id")
        per_probe_snap = _isolated_snapshot(snapshot)
        name = probe.name

        # 1) applies() filter — runs BEFORE any cache traffic.
        if not probe.applies(per_probe_snap, task):
            reason = "applies() returned False"
            _log.info("probe.skip", probe=name, reason=reason, run_id=run_id)
            return name, None, Skipped(reason=reason)

        # 2) cache lookup. The Probe ABC doesn't declare ``version`` (ADR-0007
        # freezes the contract; ``version`` is a *convention* per
        # ``probes/registry.py``). ``CacheStore.key_for`` reads it via the
        # ``_ProbeLike`` Protocol — runtime is structural, mypy needs help.
        from typing import cast

        from codegenie.cache.keys import _ProbeLike

        key = cache.key_for(cast(_ProbeLike, probe), per_probe_snap, task)
        cached: ProbeOutput | None = cache.get(key)
        if cached is not None:
            sanitized = SanitizedProbeOutput(**asdict(cached))
            _log.info("probe.cache_hit", probe=name, cache_key=key, run_id=run_id)
            return name, sanitized, CacheHit(output=sanitized, key=key)

        # 3) dispatch. Pin the per-probe input snapshot BEFORE constructing
        #    the runtime ctx — Gap 1 (TOCTOU) closure: the adapter keys the
        #    memo by ``content_hash`` from the snapshot rather than by live
        #    ``os.stat``. ``parsed_manifest`` falls back to the memo's own
        #    ``get`` for non-snapshotted paths (defensive — the adapter
        #    already routes through ``memo.get`` for both branches).
        budget: ResourceBudget = getattr(probe, "declared_resource_budget", DEFAULT_RESOURCE_BUDGET)
        timeout = min(probe.timeout_seconds, budget.wall_clock_s)
        input_snapshot = compute_input_snapshot(probe, per_probe_snap.root)
        adapter = make_parsed_manifest_adapter(input_snapshot, memo)
        ctx = _make_probe_context(
            workspace=per_probe_snap.root,
            raw_artifact_mb=budget.raw_artifact_mb,
            parsed_manifest=adapter,
            input_snapshot=input_snapshot,
        )

        _log.info("probe.start", probe=name, run_id=run_id)
        t0 = time.monotonic()
        po, error_event = await _run_probe_with_isolation(probe, per_probe_snap, ctx, timeout)
        duration_ms = int((time.monotonic() - t0) * 1000)
        if po is None:
            # Failure-path synthetic output — error_event guaranteed non-None
            assert error_event is not None
            po = _build_failure_output(error_event["error_str"], duration_ms)
            _log.info(
                error_event["event"],
                probe=name,
                duration_ms=duration_ms,
                run_id=run_id,
                reason=error_event["error_str"],
            )
        else:
            po = dataclasses.replace(po, duration_ms=duration_ms)
            # 4) validator (lazy import — coordinator must not pay pydantic cost at module load).
            try:
                from codegenie.coordinator.validator import _ProbeOutputValidator

                _ProbeOutputValidator.model_validate(
                    {"schema_slice": po.schema_slice, "confidence": po.confidence}
                )
            except Exception as exc:
                if _is_pydantic_validation_error(exc):
                    err = _format_secret_error(exc)
                    po = _build_failure_output(err, duration_ms)
                    _log.info(
                        "probe.failure",
                        probe=name,
                        duration_ms=duration_ms,
                        run_id=run_id,
                        reason=err,
                    )
                else:
                    raise
            else:
                # ``cache_key`` is part of the coordinator's ``probe.success``
                # payload so the warm-run / cold-run comparison in S4-04's
                # metamorphic cache pair can pin byte-equality across runs.
                # The probe-internal ``probe.success`` event (S4-01) carries
                # ``count_total`` / ``confidence`` instead — downstream filters
                # disambiguate by ``cache_key in event``.
                _log.info(
                    "probe.success",
                    probe=name,
                    duration_ms=duration_ms,
                    cache_key=key,
                    run_id=run_id,
                )

        # 5) sanitizer.
        sanitized = sanitizer.scrub(po, repo_root=per_probe_snap.root)

        # 6) advisory RSS check.
        peak = _sample_rss_mb()
        if peak > budget.rss_mb:
            _log.warning(
                "probe.rss.warn",
                probe=name,
                peak_rss_mb=peak,
                budget_mb=budget.rss_mb,
                run_id=run_id,
            )

        # 7) cache.put — only for clean successes (no errors). ``SanitizedProbeOutput``
        # mirrors ``ProbeOutput`` field-for-field (see ``output/sanitizer.py:50``);
        # ``cache.put`` reads them duck-typed, but its typed signature wants
        # ``ProbeOutput`` so cast at the boundary. Story Validation-notes
        # follow-up #2 tracks widening the signature in a separate PR.
        if not sanitized.errors:
            cache.put(key, cast(ProbeOutput, sanitized))

        return name, sanitized, Ran(output=sanitized, key=key)


def _is_pydantic_validation_error(exc: BaseException) -> bool:
    return type(exc).__name__ == "ValidationError" and hasattr(exc, "errors")


async def _run_probe_with_isolation(
    probe: Probe,
    snapshot: RepoSnapshot,
    ctx: Any,
    timeout: float,
) -> tuple[ProbeOutput | None, dict[str, str] | None]:
    """Run ``probe.run`` with timeout + failure isolation.

    Returns ``(output, None)`` on success or ``(None, error_event)`` on a
    handled failure. ``CancelledError``/``KeyboardInterrupt``/``SystemExit``
    propagate out (AC-7/AC-8).
    """
    try:
        po: ProbeOutput = await asyncio.wait_for(probe.run(snapshot, ctx), timeout=timeout)
        return po, None
    except TimeoutError:
        await asyncio.sleep(_TIMEOUT_GRACE_S)
        _kill_tracked_subprocesses()
        return None, {
            "event": "probe.timeout",
            "error_str": f"timeout: {timeout}s",
        }
    except ProbeBudgetExceeded as exc:
        return None, {
            "event": "probe.failure",
            "error_str": f"raw_artifact_mb exceeded: {exc}",
        }
    except (KeyboardInterrupt, SystemExit):
        raise
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return None, {
            "event": "probe.failure",
            "error_str": f"{type(exc).__name__}: {exc}",
        }


async def gather(
    snapshot: RepoSnapshot,
    task: Task,
    probes: Sequence[Probe],
    config: Any,
    cache: CacheStore,
    sanitizer: OutputSanitizer,
) -> GatherResult:
    """Dispatch ``probes`` against ``snapshot`` under a bounded concurrency budget.

    The prelude partition (tier == "base") runs first; downstream probes
    dispatch against the snapshot enriched with the merged
    ``language_stack.counts`` (Gap 4). On any prelude-degraded path, the
    second pass uses the original snapshot and a ``prelude.degraded`` event
    fires.
    """
    run_id = secrets.token_hex(8)
    structlog.contextvars.bind_contextvars(run_id=run_id)
    try:
        if not probes:
            return GatherResult(outputs={}, executions={})

        # One memo per gather() (S1-07 / ADR-0002). Default allowlist =
        # frozenset({"package.json"}); Phase 2 widens by construction.
        memo = ParsedManifestMemo()

        cpu = os.cpu_count() or 1
        bound = min(cpu, config.max_concurrent_probes, 8)
        sem = asyncio.Semaphore(bound)

        base = [p for p in probes if getattr(p, "tier", "task_specific") == "base"]
        rest = [p for p in probes if getattr(p, "tier", "task_specific") != "base"]

        outputs: dict[str, SanitizedProbeOutput] = {}
        executions: dict[str, ProbeExecution] = {}

        prelude_results = await asyncio.gather(
            *(_dispatch_one(p, snapshot, task, sem, cache, sanitizer, memo) for p in base)
        )
        prelude_errors: list[str] = []
        prelude_skipped: list[str] = []
        merged_counts: dict[str, int] = {}
        for name, out, exe in prelude_results:
            executions[name] = exe
            if out is not None:
                outputs[name] = out
            if isinstance(exe, Ran):
                if out is not None and out.errors:
                    prelude_errors.append(name)
                elif out is not None:
                    counts = _extract_language_counts(out.schema_slice)
                    if counts is not None:
                        merged_counts.update(counts)
            elif isinstance(exe, Skipped):
                prelude_skipped.append(name)

        if base and not merged_counts:
            _log.warning(
                "prelude.degraded",
                prelude_errors=prelude_errors,
                prelude_skipped=prelude_skipped,
                run_id=run_id,
            )

        enriched_snapshot = dataclasses.replace(snapshot, detected_languages=dict(merged_counts))

        rest_results = await asyncio.gather(
            *(_dispatch_one(p, enriched_snapshot, task, sem, cache, sanitizer, memo) for p in rest)
        )
        for name, out, exe in rest_results:
            executions[name] = exe
            if out is not None:
                outputs[name] = out

        return GatherResult(outputs=outputs, executions=executions)
    finally:
        structlog.contextvars.clear_contextvars()
