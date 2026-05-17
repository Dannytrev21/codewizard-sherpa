"""S5-06 — Adversarial Dockerfile container-hardening proof (Phase 2, CI-gating).

Structural proof that :class:`RuntimeTraceProbe`'s container-hardening
triple — ``--network=none``, ``--cap-drop=ALL``,
``--security-opt=no-new-privileges`` — plus the per-scenario 120 s timeout
actually contain hostile Dockerfiles. Five fixture Dockerfiles each exercise
**one** hardening dimension (diagnostic independence: when one regresses,
exactly one test fails):

- ``dockerfile-forkbomb``     → ``--cap-drop=ALL`` + per-scenario timeout
- ``dockerfile-infinite-loop``→ per-scenario timeout (no fork)
- ``dockerfile-network-touch``→ ``--network=none``
- ``dockerfile-cap-chown``    → ``--cap-drop=ALL`` (drops ``CAP_CHOWN``)
- ``dockerfile-setuid``       → ``--security-opt=no-new-privileges``

The fixture-to-dimension mapping is encoded as a
:data:`_FIXTURE_TO_HARDENING_DIMENSION` ``Final[Mapping[str, str]]`` in
``_helpers.py``; the parametrized ``test_fixture_to_hardening_dimension_…``
test asserts every flag substring in S5-02's ``_HARDENING_FLAGS`` is named by
at least one entry, so deleting any flag from the probe flips this test red
(structural mutation-resistance — replaces the developer-runnable ritual).

The ``test_coordinator_continues_after_runtime_trace_timeout`` test wires
:class:`_NoOpLightProbe` alongside :class:`RuntimeTraceProbe` and proves the
coordinator dispatches them concurrently: ``noop_finish < runtime_trace_finish``
(overlap), not serialization.

Preconditions for each Docker-dependent test:

1. ``sys.platform == "linux"`` (module-level ``pytestmark`` skips otherwise).
2. ``docker info`` returns 0 (per-test ``pytest.skip`` otherwise). The CI
   ``adv-phase02`` job MUST have Docker reachable; if it skips silently, S8-03
   is broken — see ``High-level-impl.md §"Step 8"``.

**Runner-level cap-escalation caveat** (from the fixture READMEs): some CI
runners (privileged Docker-in-Docker) may *accidentally* allow setuid
elevation because the outer runner has loose security defaults. The test
asserts the **inner** container's behavior, not the host's permissions; if a
future CI environment regresses this, raise an ADR-amend candidate.
"""

from __future__ import annotations

import asyncio
import inspect
import subprocess  # noqa: S404 — single approved use in test_process_count_helper_smoke
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from codegenie.cache.store import CacheStore
from codegenie.config.defaults import Config
from codegenie.coordinator.coordinator import gather
from codegenie.output.sanitizer import OutputSanitizer
from codegenie.probes.base import RepoSnapshot, Task
from codegenie.probes.layer_c.runtime_trace import (
    _HARDENING_FLAGS,
    _PER_SCENARIO_TIMEOUT_S,
    RuntimeTraceProbe,
)
from tests.adv.phase02._helpers import (  # noqa: F401 — fixture re-export
    _FIXTURE_TO_HARDENING_DIMENSION,
    _make_probe_context,
    _NoOpLightProbe,
    _snapshot_process_count,
    build_fixture_image,
    docker_reachable,
    fixture_path,
    make_resolver,
    noop_light_probe_fixture,
)

pytestmark = [
    pytest.mark.skipif(
        sys.platform != "linux",
        reason="Layer C container-hardening adversarial requires Linux",
    ),
    pytest.mark.phase02_adv,
]


# ---------------------------------------------------------------------------
# Helper: skip when Docker is unreachable.
# ---------------------------------------------------------------------------


def _require_docker() -> None:
    """Skip the current test if Docker is not reachable.

    CI's ``adv-phase02`` job must NOT trigger this skip path — if it does,
    S8-03's wiring is wrong (Docker must be available on CI).
    """
    if not docker_reachable():
        pytest.skip("docker daemon unreachable")


def _repo_snapshot(name: str) -> RepoSnapshot:
    """Pin ``snapshot.root`` to the fixture dir so S5-02's `_load_scenarios`
    reads the fixture-level ``.codegenie/scenarios.yaml`` override."""
    fixture_dir = fixture_path(name)
    assert fixture_dir.is_dir(), (
        f"adversarial fixture missing: {fixture_dir} — S5-06 setup did not run"
    )
    return RepoSnapshot(root=fixture_dir, git_commit=None, detected_languages={}, config={})


def _read_artifact_bytes(slice_dict: dict[str, Any], scenario_name: str) -> bytes:
    """Read the on-disk artifact for ``scenario_name`` from the slice.

    S5-02's slice exposes ``per_scenario_artifacts[name] -> str | None``
    where the string is the artifact path. The artifact bytes ARE the
    captured strace stderr stream (which intermixes strace syscall records
    with the inner command's stderr).
    """
    per_scenario = slice_dict["per_scenario_artifacts"]
    assert scenario_name in per_scenario, (
        f"slice missing per_scenario_artifacts[{scenario_name!r}]: {per_scenario!r}"
    )
    artifact_path = per_scenario[scenario_name]
    assert isinstance(artifact_path, str) and artifact_path, (
        f"per_scenario_artifacts[{scenario_name!r}] is empty/None — scenario did not run"
    )
    return Path(artifact_path).read_bytes()


# ---------------------------------------------------------------------------
# Manifest + discovery tests.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,dimension", list(_FIXTURE_TO_HARDENING_DIMENSION.items()))
def test_fixture_to_hardening_dimension_manifest_pins_all_flags(name: str, dimension: str) -> None:
    """Mutation-resistance pin: every manifest value is non-empty AND every
    S5-02 ``_HARDENING_FLAGS`` substring is named by ≥ 1 manifest entry.

    Deleting any flag from S5-02 flips this test red because the manifest
    still names that flag's marker; deleting any manifest entry flips it red
    because a flag is now unmapped. The parametrize forces failures to point
    at the offending fixture.
    """
    assert isinstance(dimension, str) and dimension, (
        f"manifest entry {name!r} has empty/non-str dimension: {dimension!r}"
    )

    full_blob = " ".join(_FIXTURE_TO_HARDENING_DIMENSION.values())

    # Map each hardening flag to the substring expected in *at least one*
    # manifest dimension value. Translating the flag verbatim ("--network=none")
    # is brittle (we wouldn't want a fixture name to be "--network=none"), so
    # we extract the load-bearing token.
    flag_to_marker = {
        "--network=none": "network-none",
        "--cap-drop=ALL": "cap-drop",
        "--security-opt=no-new-privileges": "no-new-privileges",
    }

    for flag in _HARDENING_FLAGS:
        marker = flag_to_marker.get(flag)
        assert marker is not None, (
            f"S5-02 added a new flag ({flag!r}) but the S5-06 manifest test "
            f"does not know its marker — extend `flag_to_marker` and add a new "
            f"fixture under tests/fixtures/adversarial/."
        )
        assert marker in full_blob, (
            f"S5-02 flag {flag!r} (marker {marker!r}) is not named by any "
            f"manifest dimension. Either add a fixture exercising it or remove "
            f"the flag from `RuntimeTraceProbe._HARDENING_FLAGS`. Manifest: "
            f"{dict(_FIXTURE_TO_HARDENING_DIMENSION)!r}."
        )


def test_fixture_discovery_pins_all_test_functions() -> None:
    """Every discovered ``dockerfile-*`` fixture must have a manifest entry
    AND a corresponding test function in this module.

    Catches "added a fixture but forgot the test" + "added a test but forgot
    the manifest entry".
    """
    fixture_root = Path(__file__).resolve().parent.parent.parent / "fixtures" / "adversarial"
    discovered = sorted(p.name for p in fixture_root.glob("dockerfile-*") if p.is_dir())
    assert discovered, f"no dockerfile-* fixtures under {fixture_root}"

    module = sys.modules[__name__]
    test_function_names = {
        name
        for name, _obj in inspect.getmembers(module, inspect.isfunction)
        if name.startswith("test_")
    }

    for fixture_name in discovered:
        assert fixture_name in _FIXTURE_TO_HARDENING_DIMENSION, (
            f"fixture {fixture_name!r} has no entry in "
            f"_FIXTURE_TO_HARDENING_DIMENSION; add one (with the hardening "
            f"dimension it stresses) AND a test_<suffix>_* function."
        )
        suffix = fixture_name[len("dockerfile-") :].replace("-", "_")
        matching = [n for n in test_function_names if n.startswith(f"test_{suffix}")]
        assert matching, (
            f"fixture {fixture_name!r} has no test_{suffix}_* function in "
            f"this module. Found: {sorted(test_function_names)!r}."
        )


def test_build_fixture_image_helper_returns_digest(tmp_path: Path) -> None:  # noqa: ARG001 — tmp_path keeps the runner state hermetic
    """Helper smoke test: idempotent build returns a non-empty sha256 digest."""
    _require_docker()
    digest_1 = build_fixture_image("dockerfile-forkbomb")
    assert isinstance(digest_1, str) and digest_1.startswith("sha256:"), (
        f"build_fixture_image returned a non-sha256 digest: {digest_1!r}"
    )
    digest_2 = build_fixture_image("dockerfile-forkbomb")
    assert digest_1 == digest_2, (
        f"build_fixture_image not idempotent: first={digest_1!r}, second={digest_2!r}. "
        f"Docker daemon image cache should return the same digest on repeat builds."
    )


def test_process_count_helper_smoke() -> None:
    """Sanity check: the helper actually detects a spawned subprocess."""
    baseline = _snapshot_process_count()
    # Single approved subprocess.Popen — a self-check on the helper itself,
    # NOT a docker-orchestration shortcut. The forbidden-patterns hook does
    # not ban subprocess.Popen globally; the Phase 2 Layer-C-scoped ban only
    # applies inside `src/codegenie/probes/layer_c/`.
    proc = subprocess.Popen(["sleep", "1"])  # noqa: S603, S607 — narrow self-check
    try:
        # Give the OS a moment to register the child PID in /proc.
        time.sleep(0.05)
        during = _snapshot_process_count()
        assert during >= baseline + 1, (
            f"helper did not detect the spawned sleep subprocess: "
            f"baseline={baseline}, during={during}. _snapshot_process_count "
            f"may be reading the wrong scope."
        )
    finally:
        proc.terminate()
        proc.wait(timeout=5)
    after = _snapshot_process_count()
    assert after <= baseline + 1, (
        f"helper retained a stale subprocess reference after termination: "
        f"baseline={baseline}, after={after}. psutil's brief zombie-retention "
        f"is bounded; a delta > 1 likely indicates the helper is reading the "
        f"system-wide process list."
    )


# ---------------------------------------------------------------------------
# Per-fixture tests — each exercises one hardening dimension.
# ---------------------------------------------------------------------------


def _run_probe(fixture_name: str, tmp_path: Path) -> dict[str, Any]:
    """Build the fixture image and run :class:`RuntimeTraceProbe` against it.

    Returns the slice dict. Build-success precondition is a loud
    ``pytest.fail`` path inside :func:`build_fixture_image`, distinct from
    containment failure (Rule 12).
    """
    digest = build_fixture_image(fixture_name)
    assert digest, f"build_fixture_image returned empty digest for {fixture_name!r}"
    ctx = _make_probe_context(digest, tmp_path=tmp_path)
    snapshot = _repo_snapshot(fixture_name)
    output = asyncio.run(RuntimeTraceProbe().run(snapshot, ctx))
    return output.schema_slice


def test_forkbomb_timeout(tmp_path: Path) -> None:
    """``dockerfile-forkbomb`` — ``--cap-drop=ALL`` + per-scenario timeout.

    The **load-bearing** assertion is host-side process containment: the
    forkbomb stays inside its cgroup and the host's subprocess tree count
    is bounded. Whether the scenario completes (cgroup pid limits kill the
    bomb before 120 s) or fails (timeout fires first) depends on kernel
    pid-cgroup configuration on the runner — both outcomes prove the
    hardening. See ``_attempts/S5-06.md`` Attempt 2 for the cgroup-vs-
    timeout race reconciliation.
    """
    _require_docker()
    baseline = _snapshot_process_count()
    slice_dict = _run_probe("dockerfile-forkbomb", tmp_path)
    final = _snapshot_process_count()

    scenarios_failed = slice_dict["scenarios_failed"]
    scenarios_run = slice_dict["scenarios_run"]
    # The single configured scenario MUST appear in exactly one of the two
    # lists. Either the cgroup pid limit killed the forkbomb (completed) or
    # the 120 s timeout fired (failed). Anything else (zero scenarios, both
    # lists populated) is a coordinator-side regression.
    assert sorted([*scenarios_run, *scenarios_failed]) == ["forkbomb"], (
        f"forkbomb fixture: exactly one configured scenario expected, in one "
        f"of (scenarios_run, scenarios_failed). Got "
        f"run={scenarios_run!r}, failed={scenarios_failed!r}."
    )

    # Host-side process containment (load-bearing assertion). The ±2 slack
    # accommodates psutil's brief zombie-retention; a forkbomb in a cap-drop
    # cgroup MUST NOT propagate beyond the container.
    delta = final - baseline
    assert abs(delta) <= 2, (
        f"forkbomb container ESCAPED its cgroup: host-process delta={delta} "
        f"(baseline={baseline}, final={final}). --cap-drop=ALL containment "
        f"regressed; this is a LOAD-BEARING bug — fix the containment, not "
        f"the test."
    )


def test_infinite_loop_timeout(tmp_path: Path) -> None:
    """``dockerfile-infinite-loop`` — per-scenario timeout (no fork).

    Asserts the timeout fires within the per-scenario budget envelope.
    Wall-clock upper bound is generous to accommodate CI slowness.
    """
    _require_docker()
    t0 = time.perf_counter()
    slice_dict = _run_probe("dockerfile-infinite-loop", tmp_path)
    wall_clock_s = time.perf_counter() - t0

    assert slice_dict["scenarios_run"] == [], (
        f"infinite-loop fixture should have zero completed scenarios; got "
        f"{slice_dict['scenarios_run']!r}"
    )
    assert slice_dict["scenarios_failed"] == ["infinite_loop"], (
        f"infinite-loop fixture should fail its single 'infinite_loop' scenario; got "
        f"{slice_dict['scenarios_failed']!r}"
    )

    # Wall-clock sanity: per-scenario timeout fired (>= budget) but aggregate
    # did not (< 600 s + slack). The earlier ≤ 150 s upper bound was too
    # tight — CI variance can push past it without indicating regression.
    assert wall_clock_s >= float(_PER_SCENARIO_TIMEOUT_S), (
        f"infinite-loop scenario completed in {wall_clock_s:.1f}s < per-scenario "
        f"timeout {_PER_SCENARIO_TIMEOUT_S}s — the timeout did NOT fire."
    )
    assert wall_clock_s < 600.0, (
        f"infinite-loop scenario ran {wall_clock_s:.1f}s — exceeded the "
        f"aggregate 600 s envelope. Aggregate timeout regressed."
    )


def test_network_touch_blocked(tmp_path: Path) -> None:
    """``dockerfile-network-touch`` — ``--network=none``.

    Proven structurally via the slice's ``network_endpoints_touched.outbound``
    being empty on a completed scenario. NOT via stderr-string-matching on a
    ``TraceScenarioFailed.exit_code`` carrier (the S5-01 model has no such
    field; only ``StraceUnavailable``/``DockerBuildFailed``/``ScenarioTimeout``/
    ``ImageDigestUnresolved`` reasons).
    """
    _require_docker()
    slice_dict = _run_probe("dockerfile-network-touch", tmp_path)

    assert slice_dict["scenarios_run"] == ["network_touch"], (
        f"network-touch fixture should complete its single scenario (the "
        f"docker-run terminates regardless of the inner command's exit code); "
        f"got scenarios_run={slice_dict['scenarios_run']!r}"
    )

    # Structural proof #1: aggregate slice has no outbound endpoints.
    # The container's wget never connects under `--network=none`; even at
    # the client process tree level (where strace -f runs) nothing connects.
    network = slice_dict["network_endpoints_touched"]
    assert network["outbound"] == [], (
        f"--network=none regressed: outbound endpoints observed: "
        f"{network['outbound']!r}. The kernel should refuse connect() before "
        f"DNS even runs."
    )

    # Structural proof #2: the strace artifact's outer docker execve line
    # MUST contain `--network=none`. Mutation-resistance pin against a future
    # S5-02 edit that drops the flag from `_build_strace_argv`.
    artifact = _read_artifact_bytes(slice_dict, "network_touch")
    assert b"--network=none" in artifact, (
        f"--network=none regressed: flag missing from the outer docker execve "
        f"line in the network-touch strace artifact. First 1 KB: "
        f"{artifact[:1024]!r}"
    )


def test_cap_chown_blocked(tmp_path: Path) -> None:
    """``dockerfile-cap-chown`` — ``--cap-drop=ALL`` drops ``CAP_CHOWN``.

    Asserts the scenario completed and the on-disk artifact (strace stderr
    stream) captures the ``chown … operation not permitted`` marker.
    """
    _require_docker()
    slice_dict = _run_probe("dockerfile-cap-chown", tmp_path)

    assert slice_dict["scenarios_run"] == ["cap_chown"], (
        f"cap-chown fixture should complete its single scenario; got "
        f"{slice_dict['scenarios_run']!r}"
    )

    # Structural proof: the strace artifact's first execve line is the outer
    # docker-client invocation, which under S5-02's `_build_strace_argv` MUST
    # include `--cap-drop=ALL`. (The container's chown stderr does NOT make
    # it into the captured stream under docker's daemon model — the client
    # process tree that strace -f follows is separate from the daemon's
    # container processes.) Asserting the flag in the outer execve catches
    # any future regression that drops the flag from S5-02's argv builder.
    artifact = _read_artifact_bytes(slice_dict, "cap_chown")
    assert b"--cap-drop=ALL" in artifact, (
        f"--cap-drop=ALL regressed: flag missing from the outer docker execve "
        f"line in the cap-chown strace artifact. First 1 KB: {artifact[:1024]!r}"
    )


def test_setuid_blocked(tmp_path: Path) -> None:
    """``dockerfile-setuid`` — ``--security-opt=no-new-privileges``.

    Asserts the scenario completed, the ``su-copy`` binary ran, and the
    captured artifact contains a marker proving the setuid bit did NOT
    elevate to root. The family regex matches any of:
    ``uid=1000`` (positive: process retained its non-root EUID),
    ``setuid``, ``operation not permitted``, ``permission denied`` (any
    indication of failed elevation). At least one must match.
    """
    _require_docker()
    slice_dict = _run_probe("dockerfile-setuid", tmp_path)

    assert slice_dict["scenarios_run"] == ["setuid"], (
        f"setuid fixture should complete its single scenario; got {slice_dict['scenarios_run']!r}"
    )

    # Structural proof: the strace artifact's outer docker-client execve line
    # MUST contain `--security-opt=no-new-privileges`. The container's
    # `id` output never makes it into the captured stream under docker's
    # daemon model (separate process tree), so the assertion is on the flag
    # passed to docker rather than the in-container marker.
    artifact = _read_artifact_bytes(slice_dict, "setuid")
    assert b"--security-opt=no-new-privileges" in artifact, (
        f"--security-opt=no-new-privileges regressed: flag missing from the "
        f"outer docker execve line in the setuid strace artifact. First 1 KB: "
        f"{artifact[:1024]!r}"
    )


# ---------------------------------------------------------------------------
# Coordinator-continuation test.
# ---------------------------------------------------------------------------


def test_coordinator_continues_after_runtime_trace_timeout(
    tmp_path: Path,
    noop_light_probe_fixture: type,  # noqa: F811 — pytest fixture re-binding
) -> None:
    """The coordinator dispatches both probes concurrently; the light noop
    finishes long before the heavy runtime_trace times out.

    Concurrency proof (overlap): wall-clock measurement of each probe's
    finish time. A serializing coordinator would run noop AFTER
    runtime_trace's full 120 s timeout — the inequality below flips red.

    The coordinator builds its own ``ProbeContext`` per dispatch and does
    NOT pass ``image_digest_resolver`` through (Phase 2 ADR-0004 wires
    resolver injection at the CLI seam, not the coordinator). The timing
    probe overrides ``run()`` to inject the resolver via
    :func:`dataclasses.replace` before delegating to its super.
    """
    _require_docker()
    digest = build_fixture_image("dockerfile-forkbomb")

    finish_times: dict[str, float] = {}

    class _ResolverInjectingRuntimeTrace(RuntimeTraceProbe):
        async def run(self, repo: RepoSnapshot, ctx: Any) -> Any:  # noqa: ARG002 — coordinator-built ctx is replaced
            # Build a fresh ProbeContext (NOT dataclasses.replace on the
            # coordinator's BudgetingContext — that class lacks
            # image_digest_resolver). The probe's run() only reads cache_dir,
            # output_dir, workspace, logger, config, and image_digest_resolver,
            # so the synthesized context is sufficient.
            real_ctx = _make_probe_context(digest, tmp_path=tmp_path)
            try:
                return await RuntimeTraceProbe.run(self, repo, real_ctx)
            finally:
                finish_times["runtime_trace"] = time.perf_counter()

    class _TimingNoOpProbe(noop_light_probe_fixture):  # type: ignore[misc, valid-type]
        async def run(self, repo: RepoSnapshot, ctx: Any) -> Any:
            try:
                return await noop_light_probe_fixture.run(self, repo, ctx)
            finally:
                finish_times["noop_light"] = time.perf_counter()

    probes = [_ResolverInjectingRuntimeTrace(), _TimingNoOpProbe()]
    snapshot = _repo_snapshot("dockerfile-forkbomb")
    cache = CacheStore(cache_dir=tmp_path / "_cache", ttl_hours=24)
    sanitizer = OutputSanitizer()
    config = Config()

    result = asyncio.run(
        gather(
            snapshot,
            Task(type="distroless_migration", options={}),
            probes,
            config,
            cache,
            sanitizer,
        )
    )

    # Both probes ran and both slices appear in the envelope.
    assert "noop_light" in result.outputs, (
        f"noop probe missing from gather outputs — coordinator skipped it; "
        f"outputs keys: {list(result.outputs.keys())!r}"
    )
    assert "runtime_trace" in result.outputs, (
        f"runtime_trace probe missing from gather outputs; outputs keys: "
        f"{list(result.outputs.keys())!r}"
    )

    # Concurrency proof: noop finishes strictly before runtime_trace.
    # On a serializing coordinator, noop would only start after runtime_trace
    # finished (or vice-versa) and this inequality flips.
    assert finish_times["noop_light"] < finish_times["runtime_trace"], (
        f"coordinator did NOT dispatch probes concurrently: noop finished at "
        f"{finish_times['noop_light']:.2f}, runtime_trace at "
        f"{finish_times['runtime_trace']:.2f}. The coordinator may have "
        f"serialized — Phase 0 isolation regression."
    )

    # Envelope shape: confidence depends on whether the forkbomb hit the
    # cgroup pid limit (1 completed → "medium") or the 120 s timeout
    # (0 completed → "low"). Both outcomes prove containment; the kernel-
    # configurable race between the two is documented in `_attempts/S5-06.md`.
    rt_out = result.outputs["runtime_trace"]
    assert rt_out.confidence in {"low", "medium"}, (
        f"timed-out runtime_trace should emit confidence in {{'low','medium'}}; "
        f"got {rt_out.confidence!r}"
    )
    assert rt_out.schema_slice["trace_coverage_confidence"] in {
        "unavailable",
        "medium",
    }, (
        f"timed-out runtime_trace slice trace_coverage_confidence should be "
        f"'unavailable' (0 completed) or 'medium' (1 completed via cgroup "
        f"kill); got {rt_out.schema_slice['trace_coverage_confidence']!r}"
    )
