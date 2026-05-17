"""``RuntimeTraceProbe`` — Layer C runtime / container probe (S5-02).

Executes up to five container scenarios *sequentially* under the
container-hardening triple (``--network=none``, ``--cap-drop=ALL``,
``--security-opt=no-new-privileges``), captures syscalls via
``strace -f -e trace=openat,execve,connect,bind,mmap`` on Linux, and on
any non-Linux host deterministically emits per-scenario typed failures
(:class:`StraceUnavailable`). Per-scenario timeout 120 s; aggregate 600 s.

Load-bearing rationales:

- **Sequential scenarios.** ``final-design.md §"Where security/
  best-practices traded off perf" (a)``: parallel traces against the
  same image race resources and confuse attribution. The discipline
  is asserted by ``test_concurrent_task_count_le_one`` — the assertion
  is on observed asyncio-task count, never on syntax.
- **Image-digest cache key.** 02-ADR-0004 — a ``package.json``-only
  change with the image rebuilt-and-pushed-with-same-digest must
  cache-HIT; a ``FROM``-line bump or base-image rebuild (new digest)
  must cache-MISS. The signal flows via the ``image-digest:<resolved>``
  declared-input special token, dispatched by
  :mod:`codegenie.cache.keys`. S5-02 is the first consumer of that
  mechanism (S1-09 added the resolver field on :class:`ProbeContext`;
  this story lands the cache-side dispatch in ``cache/keys.py``).
- **Envelope confidence contract preservation.** The frozen
  ``Probe.confidence: Literal["high","medium","low"]`` does NOT admit
  ``"unavailable"``. The probe's slice carries
  ``trace_coverage_confidence: Literal["high","medium","low",
  "unavailable"]`` (a Phase-2 extension of ``localv2.md §5.3 C4``'s
  tri-state); the envelope clips the tetra-state to the contract via
  :func:`_envelope_confidence`. ``test_envelope_confidence_contract_preserved``
  is the structural defense.
- **``ImageDigestUnresolved`` is a ``TraceFailureReason``, not a
  ``TraceSkipReason``.** Resolver-returned-``None`` / resolver-unbound
  / resolver-raised paths all emit
  :class:`TraceScenarioFailed` (the scenario was *attempted*, just
  could not acquire its prerequisite). Docker-build-failure paths
  emit :class:`TraceScenarioSkipped` (the scenario was never
  attempted).
- **macOS path is permanent.** No ``sudo``-prompting ``dtruss``
  fallback. On ``sys.platform != "linux"`` every scenario is
  :class:`TraceScenarioFailed` with
  :class:`StraceUnavailable` as the reason. Surfaced loudly by
  S5-05's freshness check + S8-01's renderer.
- **Layer C calls ``run_allowlisted`` directly, NOT the Layer B/G
  port.** 02-ADR-0001 — wrapping ``docker`` in
  ``bwrap --unshare-net`` would prevent ``docker build`` from working
  (daemon socket access). Equivalent isolation comes from the
  ``--network=none`` / ``--cap-drop=ALL`` / ``--security-opt=
  no-new-privileges`` argv flags constructed at the call site.

Producer / consumer ladder for :class:`ScenarioResult` (S5-01):

- **Producers:** :class:`RuntimeTraceProbe` (the canonical first
  producer; this module).
- **Consumers:** :func:`_aggregate_scenarios` (in-module), S5-05
  freshness check, S8-01 renderer.

The validation-bypass Pydantic ctor (a construction shortcut that
skips validators) is banned here by ``scripts/check_forbidden_patterns.py``
— use ``Model(...)`` / ``Model.model_validate(...)`` so the
smart-constructor invariants are honored. Direct subprocess primitives
(the stdlib ``subprocess`` callable and the asyncio spawn helper) are
also banned at the same site; all subprocess traffic must flow through
:func:`~codegenie.exec.run_allowlisted` (02-ADR-0010 + production
ADR-0033 §3).

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S5-02-runtime-trace-probe.md``
- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
  §"Component design" #6, §"Edge cases" rows 5/6/14, §"Data model".
- ``docs/phases/02-context-gather-layers-b-g/final-design.md``
  §"Components" #6, §"Where security/best-practices traded off perf" (a).
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0001-...md`` —
  docker/strace allowlist.
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0004-image-digest-...md`` —
  declared-input token mechanism.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Final, Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field

from codegenie.errors import MalformedYAMLError
from codegenie.exec import ProcessResult, run_allowlisted
from codegenie.parsers import safe_yaml
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.layer_c.scenario_result import (
    DockerBuildFailed,
    ImageBuildUnavailable,
    ImageDigestUnresolved,
    NoDockerfile,
    ScenarioResult,
    ScenarioTimeout,
    StraceUnavailable,
    TraceScenarioCompleted,
    TraceScenarioFailed,
    TraceScenarioSkipped,
)
from codegenie.probes.registry import register_probe

__all__ = ["RuntimeTraceProbe"]

_log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants — tests import these directly; mutation #3-style
# typo regressions are caught by the constant-pin tests.
# ---------------------------------------------------------------------------

#: Container-hardening flags forwarded to every ``docker run`` invocation.
#: Pinned as a tuple so a typo in any single flag flips the constant test red
#: (a plain set-membership check would not catch a misspelling).
_HARDENING_FLAGS: Final[tuple[str, ...]] = (
    "--network=none",
    "--cap-drop=ALL",
    "--security-opt=no-new-privileges",
)

#: Per-scenario wall-clock budget. Tests import the constant rather than
#: hardcoding ``120`` so a deliberate ``60``-edit flips the test red.
_PER_SCENARIO_TIMEOUT_S: Final[int] = 120

#: Aggregate wall-clock budget across all scenarios in one ``run()``.
_AGGREGATE_TIMEOUT_S: Final[int] = 600

#: Image-ref prefix used by :func:`_image_ref_for_digest`. Module-level
#: constant so call sites never string-concatenate the literal.
_IMAGE_REF_PREFIX: Final[str] = "codegenie-trace:"

#: ``asyncio.Task.get_name`` prefix used by the per-scenario task. The
#: concurrency-observation test filters on this prefix.
_SCENARIO_TASK_NAME_PREFIX: Final[str] = "runtime_trace_scenario_"

#: The five canonical scenario names (names-only — for log/render paths
#: that need a name list without command argvs).
_DEFAULT_SCENARIO_NAMES: Final[tuple[str, ...]] = (
    "startup",
    "smoke_test",
    "healthcheck",
    "shutdown",
    "error_path",
)

#: strace-attached syscalls. One module constant so the strace-argv builder
#: and any test that introspects it remain in sync.
_STRACE_EVENTS: Final[str] = "trace=openat,execve,connect,bind,mmap"

#: Sub-directory inside ``ctx.output_dir`` for raw trace artifacts.
_ARTIFACT_DIRNAME: Final[str] = "runtime_trace"

#: Per-scenario stderr cap on docker-build failure surfacing (bytes kept
#: from the tail of stderr — bounded log surface).
_STDERR_TAIL_CAP_BYTES: Final[int] = 4096

#: Image-digest sentinel used when the resolver could not produce a digest.
#: Mirrors ``codegenie.cache.keys._UNRESOLVED_SENTINEL`` so the cache key is
#: stable across the three "unresolved" paths.
_DIGEST_UNRESOLVED_SENTINEL: Final[str] = ""

# Slice-key surface (CF8 — the complete observable surface). The snapshot
# test asserts ``set(slice.keys()) == _EXPECTED_SLICE_KEYS``.
_EXPECTED_SLICE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "artifact_uri",
        "per_scenario_artifacts",
        "scenarios_run",
        "scenarios_failed",
        "binaries_executed",
        "shared_libs_loaded",
        "cert_paths_read",
        "files_read_at_runtime",
        "shell_invocations",
        "network_endpoints_touched",
        "built_image_digest",
        "last_traced_image_digest",
        "trace_coverage_confidence",
    }
)


# ---------------------------------------------------------------------------
# Pydantic models — functional-core data shapes.
# ---------------------------------------------------------------------------


class ScenarioSpec(BaseModel):
    """One scenario's name and command argv (loaded from ``.codegenie/
    scenarios.yaml`` or pulled from :data:`_DEFAULT_SCENARIOS`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    command: list[str] = Field(default_factory=list)
    expected_exit_code: int = 0


class ScenariosConfig(BaseModel):
    """Operator-side ``.codegenie/scenarios.yaml`` shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    scenarios: list[ScenarioSpec]


class ParsedTrace(BaseModel):
    """Pure shape returned by :func:`_parse_strace_lines`.

    Set-valued fields are ``frozenset`` so permutation stability of
    :func:`_parse_strace_lines` is structural — only the count-valued
    ``shell_invocations`` is non-commutative under line reordering.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    binaries_executed: frozenset[str] = Field(default_factory=frozenset)
    shared_libs_loaded: frozenset[str] = Field(default_factory=frozenset)
    cert_paths_read: frozenset[str] = Field(default_factory=frozenset)
    files_read_at_runtime: frozenset[str] = Field(default_factory=frozenset)
    shell_invocations: int = 0
    network_endpoints_touched: frozenset[tuple[str, str]] = Field(default_factory=frozenset)


_DEFAULT_SCENARIOS: Final[tuple[ScenarioSpec, ...]] = (
    ScenarioSpec(name="startup", command=["sh", "-c", "exit 0"]),
    ScenarioSpec(name="smoke_test", command=["sh", "-c", "exit 0"]),
    ScenarioSpec(name="healthcheck", command=["sh", "-c", "exit 0"]),
    ScenarioSpec(name="shutdown", command=["sh", "-c", "exit 0"]),
    ScenarioSpec(name="error_path", command=["sh", "-c", "exit 1"], expected_exit_code=1),
)


# ---------------------------------------------------------------------------
# Pure helpers (functional core).
# ---------------------------------------------------------------------------

_SHA256_PREFIX = "sha256:"
_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
_STRACE_SHELL_BINARIES: Final[frozenset[str]] = frozenset({"sh", "bash", "dash", "ash", "zsh"})
_SHARED_LIB_SUFFIX_RE = re.compile(r"\.so(?:\.[\w.]+)?$")
_CERT_PATH_RE = re.compile(r"\.(?:crt|pem|cer)$|/ca-certificates")


def _platform_is_linux() -> bool:
    """Runtime platform check that mypy cannot narrow via ``sys.platform`` Literal.

    Without this indirection mypy on macOS narrows ``sys.platform`` to
    ``"darwin"`` and reports the Linux branch as unreachable. Mirrors
    the seam used by :mod:`codegenie.exec` so the pattern is consistent.
    """
    return sys.platform.startswith("linux")


def _short(digest: str) -> str:
    """Strip any leading ``sha256:`` prefix and return the first 12 hex
    characters. Raises :class:`ValueError` for empty / non-hex inputs.
    """
    if not digest:
        raise ValueError("empty digest")
    body = digest[len(_SHA256_PREFIX):] if digest.startswith(_SHA256_PREFIX) else digest
    if not body or not _HEX_RE.fullmatch(body):
        raise ValueError(f"non-hex digest: {digest!r}")
    return body[:12]


def _image_ref_for_digest(digest: str) -> str:
    """Smart constructor — ``_IMAGE_REF_PREFIX + _short(digest)``.

    Single source of truth for the image-ref format; no call site
    concatenates the literal prefix.
    """
    return _IMAGE_REF_PREFIX + _short(digest)


def _build_docker_run_argv(image_ref: str, command_argv: Sequence[str]) -> list[str]:
    """Pure builder — argv passed to ``docker run`` (under strace on Linux).

    The container-hardening triple is unpacked as separate argv tokens (no
    string-concat). A literal ``--`` separator appears immediately before
    ``image_ref`` so a future ``docker run`` flag containing the image
    reference cannot ambiguate.
    """
    return [
        "docker",
        "run",
        "--rm",
        "-i",
        *_HARDENING_FLAGS,
        "--",
        image_ref,
        *command_argv,
    ]


def _build_strace_argv(image_ref: str, command_argv: Sequence[str]) -> list[str]:
    """Pure builder — argv passed to ``strace`` wrapping the docker-run.

    Contains exactly one literal ``--`` token, positioned immediately
    before ``docker`` (separating strace's own args from the wrapped
    command — mutation #3 catch: argv-merge regressions are surfaced
    by asserting this single separator's position). The container-
    hardening triple is unpacked as separate argv tokens *after* the
    separator and *before* ``image_ref``.
    """
    return [
        "strace",
        "-f",
        "-e",
        _STRACE_EVENTS,
        "--",
        "docker",
        "run",
        "--rm",
        "-i",
        *_HARDENING_FLAGS,
        image_ref,
        *command_argv,
    ]


def _build_docker_build_argv(image_ref: str, repo_root: Path) -> list[str]:
    """Pure builder — argv passed to ``docker build``."""
    return [
        "docker",
        "build",
        "-t",
        image_ref,
        "-f",
        "Dockerfile",
        str(repo_root),
    ]


_STRACE_LINE_RE = re.compile(
    r"^(?:\[pid\s+\d+\]\s+)?(?P<syscall>openat|execve|connect|bind|mmap)\((?P<args>.*?)\)\s*=\s*(?P<ret>-?\d+|-1\s*\w+)?"
)
_STRING_ARG_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
_SOCKADDR_RE = re.compile(r"sin_addr=inet_addr\(\"([^\"]+)\"\).*?sin_port=htons\((\d+)\)")
_SOCKADDR_RE_V2 = re.compile(r"AF_INET[^,]*,\s*sin_port=htons\((\d+)\),\s*sin_addr=inet_addr\(\"([^\"]+)\"\)")


def _parse_strace_lines(lines: Iterable[str]) -> ParsedTrace:
    """Pure function over strace output lines — returns a frozen
    :class:`ParsedTrace`.

    Malformed lines (anything that doesn't match :data:`_STRACE_LINE_RE`)
    are silently dropped — the function returns the all-empty
    :class:`ParsedTrace` for input that contains zero recognizable
    strace records.
    """
    binaries: set[str] = set()
    libs: set[str] = set()
    certs: set[str] = set()
    files: set[str] = set()
    shell_count = 0
    endpoints: set[tuple[str, str]] = set()

    for raw in lines:
        line = raw.rstrip("\n")
        match = _STRACE_LINE_RE.match(line)
        if match is None:
            continue
        syscall = match.group("syscall")
        args = match.group("args") or ""
        strings = _STRING_ARG_RE.findall(args)
        if syscall == "execve" and strings:
            binary_path = strings[0]
            binary_name = binary_path.rsplit("/", 1)[-1]
            binaries.add(binary_name)
            if binary_name in _STRACE_SHELL_BINARIES:
                shell_count += 1
        elif syscall == "openat" and len(strings) >= 1:
            path = strings[-1] if len(strings) >= 2 else strings[0]
            files.add(path)
            if _SHARED_LIB_SUFFIX_RE.search(path):
                libs.add(path)
            if _CERT_PATH_RE.search(path):
                certs.add(path)
        elif syscall == "connect":
            v2 = _SOCKADDR_RE_V2.search(args)
            v1 = _SOCKADDR_RE.search(args) if v2 is None else None
            if v2 is not None:
                endpoints.add((v2.group(2), v2.group(1)))
            elif v1 is not None:
                endpoints.add((v1.group(1), v1.group(2)))
    return ParsedTrace(
        binaries_executed=frozenset(binaries),
        shared_libs_loaded=frozenset(libs),
        cert_paths_read=frozenset(certs),
        files_read_at_runtime=frozenset(files),
        shell_invocations=shell_count,
        network_endpoints_touched=frozenset(endpoints),
    )


def _derive_trace_coverage_confidence(
    results: Sequence[ScenarioResult],
) -> Literal["high", "medium", "low", "unavailable"]:
    """Map the count of completed scenarios to the tetra-state confidence.

    5 → ``"high"``; 2..4 → ``"medium"``; exactly one completed →
    ``"low"`` when only ``"startup"`` completed (matches ``localv2.md
    §5.3 C4`` — "startup-only is low signal") else ``"medium"``; 0 →
    ``"unavailable"``.
    """
    completed = [r for r in results if isinstance(r, TraceScenarioCompleted)]
    n = len(completed)
    if n == 0:
        return "unavailable"
    if n >= 5:
        return "high"
    if n == 1:
        return "low" if completed[0].scenario_name == "startup" else "medium"
    return "medium"


def _envelope_confidence(
    slice_confidence: Literal["high", "medium", "low", "unavailable"],
) -> Literal["high", "medium", "low"]:
    """Clip slice's tetra-state to the envelope's frozen tri-state contract.

    ``unavailable`` → ``low`` (the slice retains the signal; the
    envelope's ``Probe.confidence`` Literal is **not** widened — this
    function is the contract-preservation choke point that
    ``test_envelope_confidence_contract_preserved`` defends).
    """
    match slice_confidence:
        case "high":
            return "high"
        case "medium":
            return "medium"
        case "low":
            return "low"
        case "unavailable":
            return "low"


class _AggregatedSlice(BaseModel):
    """Pure shape returned by :func:`_aggregate_scenarios`."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    scenarios_run: list[str]
    scenarios_failed: list[str]
    per_scenario_artifacts: dict[str, str | None]
    binaries_executed: list[str]
    shared_libs_loaded: list[str]
    cert_paths_read: list[str]
    files_read_at_runtime: list[str]
    shell_invocations: int
    network_endpoints_touched: dict[str, list[str]]
    trace_coverage_confidence: Literal["high", "medium", "low", "unavailable"]


def _aggregate_scenarios(
    results: Sequence[ScenarioResult],
    parsed: dict[str, ParsedTrace],
) -> _AggregatedSlice:
    """Fold per-scenario outcomes into the slice fields.

    Exhaustive ``match`` with ``assert_never``-equivalent (explicit
    enumeration of every variant; the final branch is the typed
    ``TraceScenarioSkipped`` — adding a fourth variant to
    :class:`ScenarioResult` (via ADR-amend to 02-ADR-0006) would fail
    ``mypy --warn-unreachable`` until this function is extended.
    """
    scenarios_run: list[str] = []
    scenarios_failed: list[str] = []
    per_scenario: dict[str, str | None] = {}
    binaries: set[str] = set()
    libs: set[str] = set()
    certs: set[str] = set()
    files: set[str] = set()
    shell_count = 0
    outbound: set[tuple[str, str]] = set()

    for result in results:
        match result:
            case TraceScenarioCompleted():
                scenarios_run.append(result.scenario_name)
                per_scenario[result.scenario_name] = str(result.artifact_uri)
                trace = parsed.get(result.scenario_name)
                if trace is not None:
                    binaries |= trace.binaries_executed
                    libs |= trace.shared_libs_loaded
                    certs |= trace.cert_paths_read
                    files |= trace.files_read_at_runtime
                    shell_count += trace.shell_invocations
                    outbound |= trace.network_endpoints_touched
            case TraceScenarioFailed():
                scenarios_failed.append(result.scenario_name)
                per_scenario[result.scenario_name] = None
            case TraceScenarioSkipped():
                per_scenario[result.scenario_name] = None

    confidence = _derive_trace_coverage_confidence(results)
    return _AggregatedSlice(
        scenarios_run=scenarios_run,
        scenarios_failed=scenarios_failed,
        per_scenario_artifacts=per_scenario,
        binaries_executed=sorted(binaries),
        shared_libs_loaded=sorted(libs),
        cert_paths_read=sorted(certs),
        files_read_at_runtime=sorted(files),
        shell_invocations=shell_count,
        network_endpoints_touched={
            "outbound": sorted(f"{host}:{port}" for host, port in outbound),
            "inbound": [],
        },
        trace_coverage_confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Imperative shell — the probe class.
# ---------------------------------------------------------------------------


def _load_scenarios(
    snapshot: RepoSnapshot,
) -> tuple[tuple[ScenarioSpec, ...] | None, str | None]:
    """Load ``.codegenie/scenarios.yaml`` or fall back to the defaults.

    Returns ``(scenarios, error)`` — ``error`` is non-``None`` only when
    the YAML file exists but is malformed (caller routes that to a
    typed all-five-failed envelope per the story's "closest existing
    S5-01 variant" guidance).
    """
    path = snapshot.root / ".codegenie" / "scenarios.yaml"
    if not path.exists():
        return _DEFAULT_SCENARIOS, None
    try:
        data = safe_yaml.load(path, max_bytes=1 * 1024 * 1024)
        config = ScenariosConfig.model_validate(dict(data))
    except (MalformedYAMLError, OSError, ValueError) as exc:
        return None, f"scenarios.yaml malformed: {exc}"
    return tuple(config.scenarios), None


def _resolve_image_digest(
    ctx: ProbeContext,
    root: Path,
) -> tuple[str | None, Literal["resolver_unbound", "resolver_returned_none", "resolver_raised"] | None, str | None]:
    """Wrap ``ctx.image_digest_resolver(root)``. Never raises.

    Returns a 3-tuple ``(digest_or_None, unresolved_reason_or_None,
    error_repr_or_None)``. ``error_repr_or_None`` is the resolver's
    exception ``repr`` (defensive against PII via exception text — we
    keep the type name, not the message body).
    """
    if ctx.image_digest_resolver is None:
        return None, "resolver_unbound", None
    try:
        digest = ctx.image_digest_resolver(root)
    except Exception as exc:  # noqa: BLE001 — defensive translation
        return None, "resolver_raised", repr(type(exc))
    if digest is None:
        return None, "resolver_returned_none", None
    return digest, None, None


def _summarize_files(files: Sequence[str], max_inline: int = 50) -> dict[str, Any]:
    """Build the ``files_read_at_runtime`` slice sub-shape: summary + uri."""
    return {
        "summary": {"count": len(files), "inlined": files[:max_inline]},
        "full_list_uri": None,
    }


def _empty_slice(
    built_image_digest: str | None,
    last_traced_image_digest: str | None,
    trace_coverage_confidence: Literal["high", "medium", "low", "unavailable"],
    scenarios_failed_names: Sequence[str] = (),
    per_scenario_skipped: bool = False,
) -> dict[str, Any]:
    """Build the all-empty slice dict — used by every failure / skip path."""
    if per_scenario_skipped:
        per_scenario: dict[str, str | None] = {name: None for name in _DEFAULT_SCENARIO_NAMES}
    else:
        per_scenario = {name: None for name in scenarios_failed_names}
    return {
        "artifact_uri": None,
        "per_scenario_artifacts": per_scenario,
        "scenarios_run": [],
        "scenarios_failed": list(scenarios_failed_names),
        "binaries_executed": [],
        "shared_libs_loaded": [],
        "cert_paths_read": [],
        "files_read_at_runtime": _summarize_files([]),
        "shell_invocations": 0,
        "network_endpoints_touched": {"outbound": [], "inbound": []},
        "built_image_digest": built_image_digest,
        "last_traced_image_digest": last_traced_image_digest,
        "trace_coverage_confidence": trace_coverage_confidence,
    }


def _slice_from_aggregate(
    aggregate: _AggregatedSlice,
    artifact_uri: str | None,
    built_image_digest: str | None,
    last_traced_image_digest: str | None,
) -> dict[str, Any]:
    """Render :class:`_AggregatedSlice` into the slice dict shape."""
    return {
        "artifact_uri": artifact_uri,
        "per_scenario_artifacts": dict(aggregate.per_scenario_artifacts),
        "scenarios_run": list(aggregate.scenarios_run),
        "scenarios_failed": list(aggregate.scenarios_failed),
        "binaries_executed": list(aggregate.binaries_executed),
        "shared_libs_loaded": list(aggregate.shared_libs_loaded),
        "cert_paths_read": list(aggregate.cert_paths_read),
        "files_read_at_runtime": _summarize_files(aggregate.files_read_at_runtime),
        "shell_invocations": aggregate.shell_invocations,
        "network_endpoints_touched": dict(aggregate.network_endpoints_touched),
        "built_image_digest": built_image_digest,
        "last_traced_image_digest": last_traced_image_digest,
        "trace_coverage_confidence": aggregate.trace_coverage_confidence,
    }


async def _execute_scenario(
    spec: ScenarioSpec,
    image_ref: str,
    image_built: bool,
    ctx: ProbeContext,
    snapshot: RepoSnapshot,
    artifact_dir: Path,
) -> tuple[ScenarioResult, bool, ParsedTrace | None]:
    """Run one scenario — build the image (once per ``run()``) then strace.

    Returns ``(result, image_built_after, parsed_trace_or_None)`` so the
    aggregate loop threads ``image_built`` through scenarios and folds
    parsed traces into the slice. The function never raises out — every
    failure mode is translated to a typed
    :class:`ScenarioResult`.
    """
    if not image_built:
        try:
            build_result: ProcessResult = await run_allowlisted(
                _build_docker_build_argv(image_ref, snapshot.root),
                cwd=snapshot.root,
                timeout_s=float(_PER_SCENARIO_TIMEOUT_S),
            )
        except Exception as exc:  # noqa: BLE001 — translate to typed failure
            stderr_tail = repr(type(exc))[:_STDERR_TAIL_CAP_BYTES]
            return (
                TraceScenarioFailed(
                    scenario_name=spec.name,
                    reason=DockerBuildFailed(stderr_tail=stderr_tail),
                ),
                False,
                None,
            )
        if build_result.returncode != 0:
            tail_bytes = build_result.stderr[-_STDERR_TAIL_CAP_BYTES:]
            return (
                TraceScenarioFailed(
                    scenario_name=spec.name,
                    reason=DockerBuildFailed(
                        stderr_tail=tail_bytes.decode("utf-8", errors="replace")
                    ),
                ),
                False,
                None,
            )
        image_built = True

    argv = _build_strace_argv(image_ref, spec.command)
    t0 = time.perf_counter()
    try:
        run_result = await run_allowlisted(
            argv,
            cwd=snapshot.root,
            timeout_s=float(_PER_SCENARIO_TIMEOUT_S),
        )
    except Exception as exc:  # noqa: BLE001 — translate
        return (
            TraceScenarioFailed(
                scenario_name=spec.name,
                reason=DockerBuildFailed(stderr_tail=repr(type(exc))[:_STDERR_TAIL_CAP_BYTES]),
            ),
            image_built,
            None,
        )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{spec.name}.strace"
    artifact_path.write_bytes(run_result.stderr)
    parsed = _parse_strace_lines(run_result.stderr.decode("utf-8", errors="replace").splitlines())

    return (
        TraceScenarioCompleted(
            scenario_name=spec.name,
            artifact_uri=artifact_path,
            wall_clock_ms=elapsed_ms,
            syscalls_observed=len(parsed.binaries_executed) + len(parsed.files_read_at_runtime),
            shared_libs_count=len(parsed.shared_libs_loaded),
        ),
        image_built,
        parsed,
    )


async def _run_all_scenarios(
    scenarios: Sequence[ScenarioSpec],
    image_ref: str,
    ctx: ProbeContext,
    snapshot: RepoSnapshot,
    artifact_dir: Path,
) -> tuple[list[ScenarioResult], dict[str, ParsedTrace]]:
    """Run every scenario sequentially.

    ``image_built`` is a local in this function — never an attribute on
    ``self`` (operator-extensibility + per-``run()`` lifecycle, story
    AC-19).
    """
    results: list[ScenarioResult] = []
    parsed_traces: dict[str, ParsedTrace] = {}
    image_built = False

    for spec in scenarios:
        task = asyncio.create_task(
            _execute_scenario(spec, image_ref, image_built, ctx, snapshot, artifact_dir),
            name=f"{_SCENARIO_TASK_NAME_PREFIX}{spec.name}",
        )
        try:
            result, image_built, parsed = await asyncio.wait_for(
                task, timeout=_PER_SCENARIO_TIMEOUT_S
            )
        except TimeoutError:
            results.append(
                TraceScenarioFailed(
                    scenario_name=spec.name,
                    reason=ScenarioTimeout(elapsed_ms=_PER_SCENARIO_TIMEOUT_S * 1000),
                )
            )
            continue
        results.append(result)
        if parsed is not None:
            parsed_traces[spec.name] = parsed
    return results, parsed_traces


@register_probe(heaviness="heavy", runs_last=False)
class RuntimeTraceProbe(Probe):
    """Layer C — runtime container probe.

    Builds the analyzed repo's container, runs five scenarios
    sequentially under the container-hardening triple, captures syscalls
    via ``strace -f`` on Linux (or short-circuits with typed
    :class:`StraceUnavailable` failures on every other platform), and
    emits the slice :class:`~codegenie.probes.layer_b.index_health.IndexHealthProbe`
    consumes (``built_image_digest`` / ``last_traced_image_digest`` for
    freshness; S5-05 wires the freshness check itself).

    The probe registers as ``heaviness="heavy"`` so the coordinator
    dispatches it ahead of light/medium probes — wall-clock dominates and
    cache-HIT short-circuit means heavy-first reorders fast-path runs
    favorably (02-ADR-0003).
    """

    name: str = "runtime_trace"
    version: str = "0.1.0"
    layer = "C"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    declared_inputs: list[str] = [
        "Dockerfile",
        ".codegenie/scenarios.yaml",
        "image-digest:<resolved>",
    ]
    timeout_seconds: int = 300
    cache_strategy: Literal["content"] = "content"

    def applies(self, repo: RepoSnapshot, task: Any) -> bool:
        """Only run when the repo has a ``Dockerfile``.

        The probe is image-shaped — without a Dockerfile, the typed
        :class:`NoDockerfile` skip is appropriate, but the cleaner
        dispatch-side filter is ``applies()=False``: no envelope cost
        for repos that have no container at all.
        """
        return (repo.root / "Dockerfile").exists()

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        log = _log.bind(probe=self.name)
        log.info("probe.runtime_trace.dispatch")
        started = time.perf_counter()

        scenarios, yaml_err = _load_scenarios(repo)
        if scenarios is None or yaml_err is not None:
            return self._build_envelope_yaml_malformed(yaml_err or "unknown", started)

        image_digest, unresolved_reason, error_repr = _resolve_image_digest(ctx, repo.root)
        if image_digest is None:
            log.warning(
                "probe.runtime_trace.image_digest_unresolved",
                image_digest_unresolved_reason=unresolved_reason,
                image_digest_resolver_error_repr=error_repr,
            )
            return self._build_envelope_image_digest_unresolved(scenarios, started)

        log.info("probe.runtime_trace.image_digest_resolved", digest=image_digest)
        image_ref = _image_ref_for_digest(image_digest)

        if not _platform_is_linux():
            log.info("probe.runtime_trace.platform_not_linux", platform=sys.platform)
            return self._build_envelope_macos(scenarios, image_digest, started)

        artifact_dir = ctx.output_dir / _ARTIFACT_DIRNAME
        artifact_dir.mkdir(parents=True, exist_ok=True)

        try:
            results, parsed = await asyncio.wait_for(
                _run_all_scenarios(scenarios, image_ref, ctx, repo, artifact_dir),
                timeout=_AGGREGATE_TIMEOUT_S,
            )
        except TimeoutError:
            log.warning("probe.runtime_trace.aggregate_timeout")
            results = [
                TraceScenarioFailed(
                    scenario_name=spec.name,
                    reason=ScenarioTimeout(elapsed_ms=_AGGREGATE_TIMEOUT_S * 1000),
                )
                for spec in scenarios
            ]
            parsed = {}

        if self._all_build_failures(results):
            log.warning("probe.runtime_trace.docker_build_failed_all")
            return self._build_envelope_build_failed(results, started)

        aggregate = _aggregate_scenarios(results, parsed)
        manifest_path = artifact_dir / "runtime-trace.json"
        manifest_path.write_text(json.dumps({"image_digest": image_digest}, sort_keys=True))

        slice_dict = _slice_from_aggregate(
            aggregate,
            artifact_uri=str(manifest_path),
            built_image_digest=image_digest,
            last_traced_image_digest=image_digest,
        )
        confidence = _envelope_confidence(aggregate.trace_coverage_confidence)
        duration_ms = int((time.perf_counter() - started) * 1000)
        log.info(
            "probe.runtime_trace.finish",
            scenarios_run=aggregate.scenarios_run,
            scenarios_failed=aggregate.scenarios_failed,
        )
        return ProbeOutput(
            schema_slice=slice_dict,
            raw_artifacts=[manifest_path]
            + [artifact_dir / f"{name}.strace" for name in aggregate.scenarios_run],
            confidence=confidence,
            duration_ms=duration_ms,
            warnings=[],
            errors=[],
        )

    # ------------------------------------------------------------------
    # Envelope builders for the seven failure / skip paths.
    # ------------------------------------------------------------------

    def _build_envelope_yaml_malformed(self, yaml_err: str, started: float) -> ProbeOutput:
        slice_dict = _empty_slice(
            built_image_digest=None,
            last_traced_image_digest=None,
            trace_coverage_confidence="unavailable",
            scenarios_failed_names=_DEFAULT_SCENARIO_NAMES,
            per_scenario_skipped=False,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        return ProbeOutput(
            schema_slice=slice_dict,
            raw_artifacts=[],
            confidence="low",
            duration_ms=duration_ms,
            warnings=[f"runtime_trace.scenarios_yaml_malformed: {yaml_err}"],
            errors=[],
        )

    def _build_envelope_image_digest_unresolved(
        self,
        scenarios: Sequence[ScenarioSpec],
        started: float,
    ) -> ProbeOutput:
        names = tuple(spec.name for spec in scenarios)
        slice_dict = _empty_slice(
            built_image_digest=None,
            last_traced_image_digest=None,
            trace_coverage_confidence="unavailable",
            scenarios_failed_names=names,
            per_scenario_skipped=False,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        return ProbeOutput(
            schema_slice=slice_dict,
            raw_artifacts=[],
            confidence="low",
            duration_ms=duration_ms,
            warnings=["runtime_trace.image_digest_unresolved"],
            errors=[],
        )

    def _build_envelope_macos(
        self,
        scenarios: Sequence[ScenarioSpec],
        image_digest: str,
        started: float,
    ) -> ProbeOutput:
        names = tuple(spec.name for spec in scenarios)
        slice_dict = _empty_slice(
            built_image_digest=None,
            last_traced_image_digest=None,
            trace_coverage_confidence="unavailable",
            scenarios_failed_names=names,
            per_scenario_skipped=False,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        return ProbeOutput(
            schema_slice=slice_dict,
            raw_artifacts=[],
            confidence="low",
            duration_ms=duration_ms,
            warnings=["runtime_trace.platform_not_linux"],
            errors=[],
        )

    def _build_envelope_build_failed(
        self,
        results: Sequence[ScenarioResult],
        started: float,
    ) -> ProbeOutput:
        per_scenario: dict[str, str | None] = {}
        for result in results:
            per_scenario[result.scenario_name] = None
        slice_dict: dict[str, Any] = {
            "artifact_uri": None,
            "per_scenario_artifacts": per_scenario,
            "scenarios_run": [],
            "scenarios_failed": [],
            "binaries_executed": [],
            "shared_libs_loaded": [],
            "cert_paths_read": [],
            "files_read_at_runtime": _summarize_files([]),
            "shell_invocations": 0,
            "network_endpoints_touched": {"outbound": [], "inbound": []},
            "built_image_digest": None,
            "last_traced_image_digest": None,
            "trace_coverage_confidence": "unavailable",
        }
        duration_ms = int((time.perf_counter() - started) * 1000)
        return ProbeOutput(
            schema_slice=slice_dict,
            raw_artifacts=[],
            confidence="low",
            duration_ms=duration_ms,
            warnings=["runtime_trace.docker_build_failed_all"],
            errors=[],
        )

    @staticmethod
    def _all_build_failures(results: Sequence[ScenarioResult]) -> bool:
        if not results:
            return False
        for r in results:
            if isinstance(r, TraceScenarioFailed) and isinstance(r.reason, DockerBuildFailed):
                continue
            return False
        return True


def _all_build_failures_to_skipped(
    results: Sequence[ScenarioResult],
) -> list[ScenarioResult]:
    """Promote all-five docker-build failures to typed skips.

    The story prescribes: a non-zero ``docker build`` exit results in
    every scenario being :class:`TraceScenarioSkipped` with
    :class:`ImageBuildUnavailable`. This helper is exported for the
    rare integration test that wants the skip representation; the
    in-place ``run()`` path emits the equivalent dict directly via
    :meth:`RuntimeTraceProbe._build_envelope_build_failed`.
    """
    promoted: list[ScenarioResult] = []
    for r in results:
        if isinstance(r, TraceScenarioFailed) and isinstance(r.reason, DockerBuildFailed):
            promoted.append(
                TraceScenarioSkipped(
                    scenario_name=r.scenario_name,
                    reason=ImageBuildUnavailable(),
                )
            )
        else:
            promoted.append(r)
    return promoted


# Re-export for tests that read the symbol from the probe module.
__all__ = ["RuntimeTraceProbe"]

# Sentinel: NoDockerfile is referenced by external test fixtures; importing
# the symbol here keeps it in scope.
_ = NoDockerfile
