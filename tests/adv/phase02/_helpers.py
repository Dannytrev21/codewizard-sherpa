"""Shared helpers for the Phase 2 ``tests/adv/phase02/`` corpus.

Provides three groups of utilities used by the adversarial Phase 2 tests:

1. **S5-05 drift helpers** — :func:`build_drift_slice` plus the
   ``forbid_real_subprocess`` / ``clean_freshness_registry`` fixtures used by
   :mod:`tests.adv.phase02.test_image_digest_drift`.

2. **S5-06 fixture-image helpers** — :data:`_FIXTURE_TO_HARDENING_DIMENSION`
   (the mutation-resistance manifest), :func:`build_fixture_image`,
   :func:`make_resolver`, :func:`_make_probe_context`, and
   :func:`_snapshot_process_count`. All paths route subprocess traffic through
   :func:`codegenie.exec.run_allowlisted` (02-ADR-0001 chokepoint).

3. **Coordinator-continuation helper** — :class:`_NoOpLightProbe` plus the
   :func:`noop_light_probe_fixture` pytest fixture. The probe is **not**
   globally registered: the Phase 2 :mod:`codegenie.probes.registry`
   intentionally lacks an ``unregister`` operation (registry mutation across
   tests is a known source of pollution). The coordinator's ``gather()``
   accepts ``Sequence[Probe]`` directly, so the integration test constructs
   the probe instances in-test and passes them straight to ``gather`` — no
   ``@register_probe`` decoration is required. If a future story does need
   global registration with teardown, escalate to S1-08 (do NOT workaround
   with ``del``).

Rule-of-three trigger noted in S5-05's "Notes for the implementer": this file
is the second adversarial helper module (after ``tests/adv/_helpers``); the
seam shape for kernel extraction is a ``_FIXTURE_SPEC`` dataclass +
parametrized runner, deferred to the 6th fixture (likely a ``--read-only`` or
microVM-equivalent addition).
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any, Final

import pytest

from codegenie.exec import run_allowlisted
from codegenie.indices.registry import default_freshness_registry
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot

# ---------------------------------------------------------------------------
# S5-05 drift-slice helpers (unchanged surface).
# ---------------------------------------------------------------------------


def build_drift_slice(
    built: str | None,
    last_traced: str | None,
    *,
    last_traced_at: str = "2026-05-17T00:00:00+00:00",
    trace_coverage_confidence: str = "high",
) -> dict[str, object]:
    """Synthetic ``runtime_trace`` slice for drift / clean / absent tests."""
    return {
        "built_image_digest": built,
        "last_traced_image_digest": last_traced,
        "last_traced_at": last_traced_at,
        "trace_coverage_confidence": trace_coverage_confidence,
    }


@pytest.fixture
def forbid_real_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch every subprocess seam to raise on any escape.

    Acts as a structural defense: a future "let's quickly add a real
    end-to-end check" contributor cannot silently un-mock the subprocess
    layer; the stubs raise ``AssertionError`` on every code path that would
    spawn a child process.
    """

    def _refuse(*_a: Any, **_kw: Any) -> Any:
        raise AssertionError(
            "real subprocess forbidden in adversarial layer; "
            "see tests/adv/phase02/_helpers.py::forbid_real_subprocess"
        )

    monkeypatch.setattr(subprocess, "run", _refuse)
    monkeypatch.setattr(subprocess, "check_output", _refuse)
    monkeypatch.setattr(subprocess, "check_call", _refuse)
    monkeypatch.setattr(subprocess.Popen, "__init__", _refuse)

    async def _refuse_async(*_a: Any, **_kw: Any) -> Any:
        _refuse()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _refuse_async)
    monkeypatch.setattr(asyncio, "create_subprocess_shell", _refuse_async)


@pytest.fixture
def clean_freshness_registry() -> Iterator[Any]:
    """Snapshot + restore the singleton freshness registry per test."""
    saved_checks = dict(default_freshness_registry._checks)
    saved_origins = dict(default_freshness_registry._origins)
    try:
        yield default_freshness_registry
    finally:
        default_freshness_registry._checks.clear()
        default_freshness_registry._origins.clear()
        default_freshness_registry._checks.update(saved_checks)
        default_freshness_registry._origins.update(saved_origins)


# ---------------------------------------------------------------------------
# S5-06 fixture-image helpers.
# ---------------------------------------------------------------------------

#: Map from adversarial fixture directory name to the hardening flag /
#: dimension it stresses. Mutation-resistance manifest: the parametrized
#: ``test_fixture_to_hardening_dimension_manifest_pins_all_flags`` test asserts
#: every flag substring in S5-02's ``_HARDENING_FLAGS`` is named by at least
#: one entry's value. Deleting a flag from the probe flips the test red;
#: deleting an entry from this manifest flips it red. The mapping is the
#: load-bearing structural defense that replaces the S5-04 / S5-05
#: developer-runnable mutation ritual.
_FIXTURE_TO_HARDENING_DIMENSION: Final[Mapping[str, str]] = {
    "dockerfile-forkbomb": "cap-drop+timeout",
    "dockerfile-infinite-loop": "timeout",
    "dockerfile-network-touch": "network-none",
    "dockerfile-cap-chown": "cap-drop",
    "dockerfile-setuid": "no-new-privileges",
}


#: Maximum bytes returned in a build-failure ``pytest.fail`` message.
_STDERR_TAIL_CAP_BYTES: Final[int] = 4096

#: Per-image build wall-clock cap. Alpine-base images build quickly even on
#: cold cache; 180 s is generous and matches the per-scenario budget envelope.
_BUILD_TIMEOUT_S: Final[float] = 180.0


def _fixture_root() -> Path:
    """Resolve ``tests/fixtures/adversarial/`` from this helper module."""
    return Path(__file__).resolve().parent.parent.parent / "fixtures" / "adversarial"


def fixture_path(name: str) -> Path:
    """Return the absolute path to fixture ``name``.

    Public sibling of :func:`_fixture_root`; tests import this rather than
    rebuilding the path each call.
    """
    return _fixture_root() / name


def _image_tag(name: str) -> str:
    """Stable docker image tag for fixture ``name`` (e.g.
    ``codegenie-adv:dockerfile-forkbomb``).
    """
    return f"codegenie-adv:{name}"


def build_fixture_image(name: str) -> str:
    """Build fixture ``name`` via ``docker build`` and return its image digest.

    Routes both the build and the digest lookup through
    :func:`codegenie.exec.run_allowlisted` (02-ADR-0001 chokepoint). On a
    non-zero build exit, raises ``pytest.fail`` with the trailing stderr so
    the loud-failure path is distinct from a container-containment failure
    (Rule 12 — fail loud). Idempotent: the second call returns the same
    digest from the docker daemon's image cache.
    """
    fixture_dir = fixture_path(name)
    if not fixture_dir.is_dir():
        pytest.fail(f"adversarial fixture missing: {fixture_dir}")
    tag = _image_tag(name)

    build_argv: list[str] = ["docker", "build", "-t", tag, str(fixture_dir)]
    inspect_argv: list[str] = [
        "docker",
        "image",
        "inspect",
        tag,
        "--format={{.Id}}",
    ]

    build_result = asyncio.run(
        run_allowlisted(build_argv, cwd=fixture_dir, timeout_s=_BUILD_TIMEOUT_S)
    )
    if build_result.returncode != 0:
        tail = build_result.stderr[-_STDERR_TAIL_CAP_BYTES:].decode("utf-8", errors="replace")
        pytest.fail(f"docker build failed for fixture {name}: {tail!r}")

    inspect_result = asyncio.run(run_allowlisted(inspect_argv, cwd=fixture_dir, timeout_s=30.0))
    if inspect_result.returncode != 0:
        tail = inspect_result.stderr[-_STDERR_TAIL_CAP_BYTES:].decode("utf-8", errors="replace")
        pytest.fail(f"docker image inspect failed for fixture {name}: {tail!r}")
    digest = inspect_result.stdout.decode("utf-8", errors="replace").strip()
    if not digest:
        pytest.fail(f"docker image inspect returned empty digest for fixture {name}")
    return digest


def make_resolver(digest: str) -> Callable[[Path], str | None]:
    """Return a callable suitable for :attr:`ProbeContext.image_digest_resolver`.

    Centralizes the lambda construction so tests pin the signature exactly
    once. Future ``image_digest_resolver`` signature drift surfaces here.
    """

    def _resolver(_root: Path) -> str | None:
        return digest

    return _resolver


def _make_probe_context(
    image_digest: str,
    *,
    tmp_path: Path,
) -> ProbeContext:
    """Construct a :class:`ProbeContext` with all required fields explicit.

    Future :class:`ProbeContext` signature additions surface as a type error
    here rather than a runtime ``TypeError`` deep in a test. Each per-fixture
    test passes its own ``tmp_path`` so artifact paths do not collide across
    test functions.
    """
    return ProbeContext(
        cache_dir=tmp_path / "_cache",
        output_dir=tmp_path / "_out",
        workspace=tmp_path / "_ws",
        logger=logging.getLogger("adv.phase02.dockerfile"),
        config={},
        image_digest_resolver=make_resolver(image_digest),
    )


def _snapshot_process_count() -> int:
    """Return the count of subprocess descendants of the running test process.

    Uses ``psutil.Process(os.getpid()).children(recursive=True)`` — the
    runner's subprocess tree, NOT the system-wide process count
    (``psutil.process_iter()``) which is too noisy on busy CI runners. The
    delta this number produces across a per-fixture test is bounded by
    psutil's brief zombie-process retention (±1-2).
    """
    import psutil  # local import — keeps the helper import-light when unused

    return len(psutil.Process(os.getpid()).children(recursive=True))


def docker_reachable() -> bool:
    """Return True when ``docker`` is on PATH and ``docker info`` succeeds.

    Used by the per-fixture tests to ``pytest.skip`` cleanly on local dev
    boxes without Docker. CI's ``adv-phase02`` job must NOT skip — S8-03
    fails loudly when Docker is unreachable on CI (see the test module
    docstring's CI-vs-local note).
    """
    if sys.platform != "linux":
        return False
    try:
        result = asyncio.run(run_allowlisted(["docker", "info"], cwd=Path.cwd(), timeout_s=10.0))
    except Exception:  # noqa: BLE001 — any failure means "not reachable"
        return False
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Coordinator-continuation helper.
# ---------------------------------------------------------------------------


class _NoOpLightProbe(Probe):
    """Trivial probe whose ``run()`` returns a fixed slice in well under 1 s.

    Not registered with ``@register_probe``: the integration test passes a
    direct instance to the coordinator's ``gather()`` (which accepts a
    probe list) so we avoid global-registry mutation. Coordinator-side
    behavior under cancellation is the target of the test, not the
    registry contract.

    ``name="noop_light"`` chosen to avoid clashing with any production
    probe; ``layer="A"`` / ``tier="base"`` placement makes the probe
    eligible for the prelude wave alongside ``RuntimeTraceProbe`` (which
    is ``tier="base"`` itself).
    """

    name: str = "noop_light"
    version: str = "0.1.0"
    layer = "A"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    declared_inputs: list[str] = []
    timeout_seconds: int = 5

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:  # noqa: ARG002 — Probe ABC signature
        return ProbeOutput(
            schema_slice={"noop_light": {"completed": True}},
            raw_artifacts=[],
            confidence="high",
            duration_ms=0,
            warnings=[],
            errors=[],
        )


@pytest.fixture
def noop_light_probe_fixture() -> Iterator[type[Probe]]:
    """Yield :class:`_NoOpLightProbe` (the class, not an instance).

    Naming preserved per AC; semantics changed to instance-construction over
    global registration (no ``@register_probe``, no teardown unregister
    dance). Documented in the module docstring + S5-06 attempt log.
    """
    yield _NoOpLightProbe
