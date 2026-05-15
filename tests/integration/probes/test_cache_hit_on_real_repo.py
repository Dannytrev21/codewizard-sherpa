"""S2-05 + S5-05 — warm-path cache-hit metamorphic pair (all Phase-1 probes).

Two test functions exercise the load-bearing Phase 1 exit criterion #2 in
its all-six-probe form. The set of warm-path probes is read from
:data:`WARM_PATH_CACHE_HIT_PROBES` in
:mod:`tests.integration.probes.conftest` — adding a Phase-2 probe is one
frozenset insertion + one :data:`PHASE_1_PROBE_TO_SLICE` entry; zero
edits to either function body (the seam is the Open/Closed-at-the-file-
boundary the conftest established for S5-05 specifically):

- :func:`test_warm_path_probes_cache_hit_on_second_run` — runs
  ``codegenie gather`` twice against the same fixture and asserts the
  warm-run cache invariant holds across every probe in
  :data:`WARM_PATH_CACHE_HIT_PROBES` (Phase 1: all six Layer A probes).
  Four redundant signals pin the invariant:

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

- :func:`test_warm_path_probes_cache_miss_on_tracked_input_edit` — metamorphic
  partner. Edits ``package.json`` (a tracked input for the Node-shaped
  probes' ``declared_inputs``) between cold and warm runs and asserts the
  symmetric inverse: cache misses on the probes that read it,
  ``probe.success`` carries a *different* ``cache_key`` than cold,
  scandir count > 0, no ``probe.cache_hit`` event. Without this test, an
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
from structlog.testing import capture_logs

from codegenie.schema.validator import validate
from tests.integration.probes.conftest import (
    WARM_PATH_CACHE_HIT_PROBES,
    _copy_tree,
    _install_scandir_counter,
    _invoke_gather,
    _load_envelope,
    _stat_snapshot,
    _stub_node_version_check,
)

FIXTURE = Path(__file__).resolve().parent.parent.parent / "fixtures" / "node_typescript_helm"


# Subset of :data:`WARM_PATH_CACHE_HIT_PROBES` whose ``declared_inputs``
# include ``package.json`` — i.e., probes whose cache key is content-
# dependent on package.json edits. ``ci`` and ``deployment`` declare
# orthogonal inputs (CI workflows, Helm/Kustomize/Terraform manifests)
# and stay cache-hit under a package.json mutation, so the cache-miss
# metamorphic partner asserts only this subset (any probe added to
# :data:`WARM_PATH_CACHE_HIT_PROBES` whose inputs also include
# ``package.json`` must be added here too — one-line frozenset edit).
_PACKAGE_JSON_DEPENDENT_PROBES: frozenset[str] = frozenset(
    {"language_detection", "node_build_system", "node_manifest", "test_inventory"}
)


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


def test_warm_path_probes_cache_hit_on_second_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario 2 from ``phase-arch-design.md §Scenarios`` — the load-bearing
    Phase 1 exit criterion #2 in its all-Phase-1 form.

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

    # AC-14 / AC-15 / S5-05 AC-CH-5 — slice content invariance (fail-loud,
    # Rule 12).  The envelope only carries each probe's ``schema_slice``
    # keys — not top-level ``errors`` / ``warnings`` / ``confidence``
    # (S2-04 deviation L-25 / L-21). The fail-loud integrity signals
    # therefore split across (a) in-slice fields and (b) captured
    # structlog events. One load-bearing value pin per slice — mutation-
    # killing per Rule 9 (a buggy cache replay that drops a field would
    # still satisfy the cache-hit signals; the slice pins catch silent
    # corruption).
    envelope = _load_envelope(repo)

    lang = envelope["probes"]["language_detection"]
    assert lang["language_stack"]["framework_hints"] == ["express"], lang
    assert lang["language_stack"]["monorepo"] is None, lang

    nbs_slice = envelope["probes"]["node_build_system"]["build_system"]
    assert nbs_slice["package_manager"] == "pnpm", nbs_slice
    assert nbs_slice["warnings"] == [], nbs_slice

    nm_slice = envelope["probes"]["node_manifest"]["manifests"]
    assert nm_slice["primary"]["path"] == "package.json", nm_slice

    ci_slice = envelope["probes"]["ci"]["ci"]
    assert ci_slice["provider"] == "github_actions", ci_slice

    dp_slice = envelope["probes"]["deployment"]["deployment"]
    # The S2-03 fixture lays Helm at deploy/chart/; current deployment
    # probe only auto-detects Chart.yaml at repo root (S4-02 design).
    # Slice exists and has a type field — that's the load-bearing
    # invariance: a buggy cache replay would drop the field entirely.
    assert "type" in dp_slice, dp_slice

    ti_slice = envelope["probes"]["test_inventory"]["test_inventory"]
    assert ti_slice["framework"] == "vitest", ti_slice
    assert ti_slice["unit_test_count_is_file_count"] is True, ti_slice

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


def test_warm_path_probes_cache_miss_on_tracked_input_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Metamorphic partner of :func:`test_warm_path_probes_cache_hit_on_second_run`.

    Edits ``package.json`` (a tracked input for the Node-shaped probes'
    ``declared_inputs``). Without this test, an
    ``always-return-CacheHit`` mutant passes every clause of the hit
    test. Phase 0 S4-04 carries the same metamorphic pattern for one
    probe; this is the all-Phase-1 extension via
    :data:`WARM_PATH_CACHE_HIT_PROBES`.
    """
    _stub_node_version_check(monkeypatch)

    import codegenie.probes.language_detection as ld_mod

    repo = _copy_tree(FIXTURE, tmp_path / "repo")

    with capture_logs() as cold_logs:
        result_cold = _invoke_gather(repo)
    assert result_cold.exit_code == 0, result_cold.output

    cold_keys = _coordinator_success_keys(list(cold_logs))
    assert set(cold_keys) == WARM_PATH_CACHE_HIT_PROBES, cold_logs

    # Edit package.json — tracked input for the package.json-dependent
    # probes (``ci``/``deployment`` declare orthogonal inputs and stay
    # cache-hit; see ``_PACKAGE_JSON_DEPENDENT_PROBES`` rationale).
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

    # No cache_hit for any package.json-dependent probe.
    warm_hits = [
        e
        for e in warm_logs
        if e.get("event") == "probe.cache_hit" and e.get("probe") in _PACKAGE_JSON_DEPENDENT_PROBES
    ]
    assert not warm_hits, (
        f"cache must NOT hit on tracked-input change for package.json-dependent "
        f"probes; got={warm_hits}"
    )

    # Exactly one coordinator probe.success(cache_key) per package.json-dependent probe.
    warm_keys = _coordinator_success_keys(list(warm_logs))
    miss_keys = {k: v for k, v in warm_keys.items() if k in _PACKAGE_JSON_DEPENDENT_PROBES}
    assert set(miss_keys) == _PACKAGE_JSON_DEPENDENT_PROBES, (
        f"warm-run probe.success(cache_key) coverage on miss; got={set(miss_keys)}, "
        f"events={warm_logs}"
    )

    # Cache key changed for each package.json-dependent probe.
    for probe in _PACKAGE_JSON_DEPENDENT_PROBES:
        assert miss_keys[probe] != cold_keys[probe], (
            f"{probe}: cache_key must change when tracked inputs change; "
            f"cold={cold_keys[probe]!r} warm={warm_keys[probe]!r}"
        )
