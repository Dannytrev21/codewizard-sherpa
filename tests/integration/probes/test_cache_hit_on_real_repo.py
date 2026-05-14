"""S2-05 — two-probe warm-path cache-hit metamorphic pair.

Two test functions exercise the load-bearing Phase 1 exit criterion #2 in
its two-probe form (S5-05 extends to all six probes by adding entries to
:data:`WARM_PATH_CACHE_HIT_PROBES` in
:mod:`tests.integration.probes.conftest` — **zero** edits to this file
are required):

- :func:`test_two_probes_cache_hit_on_second_run` — runs
  ``codegenie gather`` twice against the same fixture and asserts the
  warm-run cache invariant holds across :class:`LanguageDetectionProbe`
  (S2-01) and :class:`NodeBuildSystemProbe` (S2-02). Four redundant
  signals pin the invariant:

  1. ``calls["count"] == 0`` — module-local
     :func:`tests.smoke.conftest._install_scandir_counter` shim on
     :mod:`codegenie.probes.language_detection` records zero
     ``os.scandir`` invocations on the warm run.
  2. Exactly one ``probe.cache_hit`` event for each probe in
     :data:`WARM_PATH_CACHE_HIT_PROBES`.
  3. **Zero** ``probe.success`` events carrying ``cache_key`` on the
     warm run for either probe (pins the variant as ``CacheHit``,
     not ``Ran``; a buggy impl that fired both events would slip past
     signal 2 alone).
  4. ``cache_key`` byte-equality across cold and warm for each probe —
     proves the cache-key invariance directly, not just that *some* hit
     blob was found.

  Plus slice-content invariance (a buggy cache that replays a degraded
  slice — empty ``framework_hints``, ``warnings`` populated,
  ``confidence != "high"`` — would still satisfy the cache-hit
  signals; the slice-content ACs catch silent corruption) and schema
  validity (the cached envelope must still validate under
  :func:`codegenie.schema.validator.validate`).

- :func:`test_two_probes_cache_miss_on_tracked_input_edit` — metamorphic
  partner. Edits ``package.json`` (a tracked input for **both** probes'
  ``declared_inputs``) between cold and warm runs and asserts the
  symmetric inverse: cache misses for both probes, ``probe.success``
  carries a *different* ``cache_key`` than cold, scandir count > 0,
  no ``probe.cache_hit`` event. Without this test, an
  ``always-return-CacheHit`` mutant passes every clause of the hit test.

The metamorphic pair is non-negotiable (Phase 0 S4-04 §"Notes for the
implementer" — "Don't drop any of the three when simplifying"; this
story has four signals, same principle).

``node_build_system`` does **not** call ``os.scandir`` (lockfile-precedence
+ tsconfig walks use ``Path.exists()`` + ``jsonc.load``). The scandir
counter is therefore a proxy for ``language_detection``'s walk only;
``probe.cache_hit`` event count is the load-bearing signal for
``node_build_system``. The redundancy is asymmetric but adequate.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from structlog.testing import capture_logs

from codegenie.cli import cli
from codegenie.schema.validator import validate
from tests.integration.probes.conftest import (
    WARM_PATH_CACHE_HIT_PROBES,
    _copy_tree,
    _install_scandir_counter,
    _load_envelope,
    _stat_snapshot,
    _stub_node_version_check,
)

FIXTURE = Path(__file__).resolve().parent.parent.parent / "fixtures" / "node_typescript_helm"


def _invoke_gather(repo: Path) -> Any:
    """``--no-gitignore`` is the documented Phase 0 override that avoids
    coupling integration tests to TTY-prompt behavior. Global flags
    BEFORE the subcommand (click left-to-right option binding); mirrors
    ``tests/smoke/test_cli_end_to_end.py``'s ``_invoke_gather``."""
    return CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])


def _coordinator_success_keys(events: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Return ``{probe_name: cache_key}`` extracted from coordinator-emitted
    ``probe.success`` events that carry ``cache_key`` for probes in
    :data:`WARM_PATH_CACHE_HIT_PROBES`.

    The coordinator emits ``probe.success`` with ``cache_key`` after a
    cache miss + successful run (``coordinator.py:377``). The probe-internal
    ``probe.success`` event (e.g., ``language_detection.py:480``) does *not*
    carry ``cache_key`` — filtering on ``"cache_key" in e`` disambiguates.

    Iterating over :data:`WARM_PATH_CACHE_HIT_PROBES` (not naming probes
    individually) makes S5-05's extension a one-line frozenset edit.
    """
    return {
        e["probe"]: e["cache_key"]
        for e in events
        if e.get("event") == "probe.success"
        and "cache_key" in e
        and e.get("probe") in WARM_PATH_CACHE_HIT_PROBES
    }


def _stat_diff(
    pre: dict[str, tuple[int, int]], post: dict[str, tuple[int, int]]
) -> dict[str, tuple[tuple[int, int] | None, tuple[int, int] | None]]:
    """Named-key diff between two ``_stat_snapshot`` dicts. Empty when equal."""
    only: dict[str, tuple[tuple[int, int] | None, tuple[int, int] | None]] = {
        k: (pre.get(k), post.get(k)) for k in set(pre) ^ set(post)
    }
    changed: dict[str, tuple[tuple[int, int] | None, tuple[int, int] | None]] = {
        k: (pre[k], post[k]) for k in pre.keys() & post.keys() if pre[k] != post[k]
    }
    return {**only, **changed}


def test_two_probes_cache_hit_on_second_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario 2 from ``phase-arch-design.md §Scenarios`` — the load-bearing
    Phase 1 exit criterion #2 in its two-probe form.

    Four redundant signals collectively pin the warm-path cache
    invariant (see module docstring). Dropping any one would let a
    class of buggy implementations through.
    """
    # Stub node --version so the env-dependent disagree warning never fires.
    _stub_node_version_check(monkeypatch)

    import codegenie.probes.language_detection as ld_mod

    repo = _copy_tree(FIXTURE, tmp_path / "repo")
    pre = _stat_snapshot(repo)

    # Cold gather — populates the cache; capture cold cache_keys.
    with capture_logs() as cold_logs:
        result_cold = _invoke_gather(repo)
    assert result_cold.exit_code == 0, result_cold.output

    # AC-6 — fixture immutability invariant (belt-and-suspenders, ADR-0002).
    post = _stat_snapshot(repo)
    assert post == pre, f"fixture drifted during cold gather; diff={_stat_diff(pre, post)}"

    # AC-8 — both probes emitted coordinator-side probe.success(cache_key) on cold.
    cold_keys = _coordinator_success_keys(list(cold_logs))
    assert set(cold_keys) == WARM_PATH_CACHE_HIT_PROBES, (
        f"cold-run probe.success(cache_key) coverage; got={set(cold_keys)}, events={cold_logs}"
    )

    # AC-5 — module-local scandir counter shim. NEVER monkeypatch.setattr(ld_mod.os, ...).
    calls = _install_scandir_counter(monkeypatch, ld_mod)

    # Warm gather — must hit the cache for BOTH probes.
    with capture_logs() as warm_logs:
        result_warm = _invoke_gather(repo)
    assert result_warm.exit_code == 0, result_warm.output

    # AC-10 — zero scandir invocations on warm path.
    assert calls["count"] == 0, (
        f"warm-run scandir count={calls['count']} (expected 0); warm_logs={warm_logs}"
    )

    # AC-11 — exactly one probe.cache_hit per probe on warm.
    warm_hits = {
        e["probe"]: e
        for e in warm_logs
        if e.get("event") == "probe.cache_hit" and e.get("probe") in WARM_PATH_CACHE_HIT_PROBES
    }
    assert set(warm_hits) == WARM_PATH_CACHE_HIT_PROBES, (
        f"warm-run probe.cache_hit coverage; got={set(warm_hits)}, events={warm_logs}"
    )

    # AC-12 — variant pin: NO coordinator probe.success(cache_key) on warm for either probe.
    rogue_successes = [
        e
        for e in warm_logs
        if e.get("event") == "probe.success"
        and "cache_key" in e
        and e.get("probe") in WARM_PATH_CACHE_HIT_PROBES
    ]
    assert not rogue_successes, (
        f"probe.success(cache_key) must NOT fire on cache-hit warm run; got={rogue_successes}"
    )

    # AC-13 — cache_key byte-equality across cold and warm for each probe.
    for probe in WARM_PATH_CACHE_HIT_PROBES:
        assert warm_hits[probe].get("cache_key") == cold_keys[probe], (
            f"{probe}: cache_key invariance broken; "
            f"cold={cold_keys[probe]!r} warm={warm_hits[probe].get('cache_key')!r}"
        )

    # AC-14 / AC-15 — slice content invariance (fail-loud, Rule 12).
    #
    # The envelope only carries each probe's ``schema_slice`` keys — not
    # top-level ``errors`` / ``warnings`` / ``confidence`` (S2-04
    # deviation L-25 / L-21; only ``schema_slice`` is shallow-merged
    # into ``envelope.probes.<name>`` by the writer). The fail-loud
    # integrity signals therefore split across (a) in-slice fields and
    # (b) captured structlog events.
    envelope = _load_envelope(repo)
    lang = envelope["probes"]["language_detection"]
    nbs = envelope["probes"]["node_build_system"]

    assert lang["language_stack"]["framework_hints"] == ["express"], lang
    assert lang["language_stack"]["monorepo"] is None, lang

    nbs_slice = nbs["build_system"]
    assert nbs_slice["package_manager"] == "pnpm", nbs_slice
    assert nbs_slice["warnings"] == [], nbs_slice

    # No probe.failure events on warm for either probe (fail-loud:
    # a silently-degraded cache replay must not emit failures).
    warm_failures = [
        e
        for e in warm_logs
        if e.get("event") == "probe.failure" and e.get("probe") in WARM_PATH_CACHE_HIT_PROBES
    ]
    assert warm_failures == [], f"unexpected warm-run probe.failure events: {warm_failures}"

    # On the cache-hit path the probe never runs, so probe-internal
    # ``probe.success`` events (those *without* ``cache_key`` —
    # disambiguates the coordinator-emitted twin) must NOT fire on
    # warm for either probe. Confidence is pinned by the cold run +
    # the existing S2-04 warm-path memo test; we pin the variant here.
    warm_probe_internal_success = [
        e
        for e in warm_logs
        if e.get("event") == "probe.success"
        and e.get("probe") in WARM_PATH_CACHE_HIT_PROBES
        and "cache_key" not in e
    ]
    assert warm_probe_internal_success == [], (
        "probe-internal probe.success events must NOT fire on warm cache hit; "
        f"got={warm_probe_internal_success}"
    )

    # AC-16 — envelope schema validation: warm-run YAML still validates.
    validate(envelope)  # raises SchemaValidationError on bad shape


def test_two_probes_cache_miss_on_tracked_input_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Metamorphic partner of :func:`test_two_probes_cache_hit_on_second_run`.

    Edits ``package.json`` (a tracked input for **both** probes'
    ``declared_inputs``). Without this test, an ``always-return-CacheHit``
    mutant passes every clause of the hit test. Phase 0 S4-04 carries
    the same metamorphic pattern for one probe; this is the two-probe
    extension.
    """
    _stub_node_version_check(monkeypatch)

    import codegenie.probes.language_detection as ld_mod

    repo = _copy_tree(FIXTURE, tmp_path / "repo")

    with capture_logs() as cold_logs:
        result_cold = _invoke_gather(repo)
    assert result_cold.exit_code == 0, result_cold.output

    cold_keys = _coordinator_success_keys(list(cold_logs))
    assert set(cold_keys) == WARM_PATH_CACHE_HIT_PROBES, cold_logs

    # Edit package.json — tracked input for BOTH probes.
    pkg = repo / "package.json"
    data = json.loads(pkg.read_text())
    data["_test_edit"] = True
    pkg.write_text(json.dumps(data, indent=2) + "\n")

    calls = _install_scandir_counter(monkeypatch, ld_mod)

    with capture_logs() as warm_logs:
        result_warm = _invoke_gather(repo)
    assert result_warm.exit_code == 0, result_warm.output

    # AC-17 — probe re-walked because the cache missed.
    assert calls["count"] > 0, (
        f"expected scandir > 0 on tracked-input change; got 0; warm_logs={warm_logs}"
    )

    # No cache_hit for either probe.
    warm_hits = [
        e
        for e in warm_logs
        if e.get("event") == "probe.cache_hit" and e.get("probe") in WARM_PATH_CACHE_HIT_PROBES
    ]
    assert not warm_hits, f"cache must NOT hit on tracked-input change; got={warm_hits}"

    # Exactly one coordinator probe.success(cache_key) per probe.
    warm_keys = _coordinator_success_keys(list(warm_logs))
    assert set(warm_keys) == WARM_PATH_CACHE_HIT_PROBES, (
        f"warm-run probe.success(cache_key) coverage on miss; got={set(warm_keys)}, "
        f"events={warm_logs}"
    )

    # Cache key changed for each probe (re-derived from new content_hash).
    for probe in WARM_PATH_CACHE_HIT_PROBES:
        assert warm_keys[probe] != cold_keys[probe], (
            f"{probe}: cache_key must change when tracked inputs change; "
            f"cold={cold_keys[probe]!r} warm={warm_keys[probe]!r}"
        )
