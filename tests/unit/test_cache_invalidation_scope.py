"""Tests for the Gap-1 anchor — per-probe-only schema versioning (ADR-0003).

The story names this file as the load-bearing regression test for
``phase-arch-design.md §Gap analysis Gap 1``: bumping one probe's sub-schema
``$id`` must NOT invalidate any other probe's cache entry, and bumping the
envelope's ``$id`` must NOT invalidate ANY probe's cache entry.

The mutation killers, named:

- A ``key_for`` that includes ``envelope_schema_version()`` in the tuple
  (alongside or instead of the per-probe version) fails the envelope-bump
  invariant.
- A ``key_for`` that swaps per-probe for envelope fails the per-probe
  invariant.
- A ``per_probe_schema_version`` that raises ``FileNotFoundError`` or
  returns ``""`` for unknown probes fails the fallback test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codegenie.probes.base import RepoSnapshot, Task


class _ProbeA:
    name: str = "probe_a"
    version: str = "1.0"
    declared_inputs: list[str] = ["**/*.txt"]


class _ProbeB:
    name: str = "probe_b"
    version: str = "1.0"
    declared_inputs: list[str] = ["**/*.txt"]


class _NoSubschemaProbe:
    name: str = "no_subschema"
    version: str = "1.0"
    declared_inputs: list[str] = ["**/*.txt"]


def _seed_schema_dir(schema_dir: Path) -> None:
    """Lay out a minimal envelope + ``probes/`` subdir under ``schema_dir``."""
    (schema_dir / "probes").mkdir(parents=True, exist_ok=True)
    envelope = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://codewizard-sherpa.dev/schemas/repo_context/v0.1.0.json",
    }
    (schema_dir / "repo_context.schema.json").write_text(json.dumps(envelope))


def _write_probe_schema(schema_dir: Path, name: str, version: str) -> None:
    sub = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://codewizard-sherpa.dev/schemas/probes/{name}/{version}.json",
    }
    (schema_dir / "probes" / f"{name}.schema.json").write_text(json.dumps(sub))


def _make_snapshot(tmp_path: Path) -> RepoSnapshot:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.txt").write_bytes(b"alpha")
    return RepoSnapshot(root=root, git_commit=None, detected_languages={}, config={})


# ---------------------------------------------------------------------------
# Gap-1 anchor: per-probe sub-schema bump does NOT invalidate sibling probes
# ---------------------------------------------------------------------------


def test_cache_invalidation_scope_is_per_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0003 §Decision: bumping probe B's sub-schema MUST NOT change
    probe A's cache key.

    Mutation killer: any ``key_for`` that swaps per-probe for envelope (or
    that includes the envelope version alongside the per-probe version)
    regresses here — A's key would move when B's sub-schema bumps, because
    the envelope version stays constant but A's tuple wouldn't contain
    enough disambiguating data."""
    from codegenie.cache import keys as keys_mod

    schema_dir = tmp_path / "schema"
    _seed_schema_dir(schema_dir)
    _write_probe_schema(schema_dir, "probe_a", "v0.1.0")
    _write_probe_schema(schema_dir, "probe_b", "v0.1.0")
    monkeypatch.setattr(keys_mod, "_SCHEMA_DIR", schema_dir)

    snapshot = _make_snapshot(tmp_path)
    task = Task(type="t", options={})

    key_a_before = keys_mod.key_for(_ProbeA, snapshot, task)  # type: ignore[arg-type]
    key_b_before = keys_mod.key_for(_ProbeB, snapshot, task)  # type: ignore[arg-type]

    # bump B's sub-schema $id only
    _write_probe_schema(schema_dir, "probe_b", "v0.2.0")

    key_a_after = keys_mod.key_for(_ProbeA, snapshot, task)  # type: ignore[arg-type]
    key_b_after = keys_mod.key_for(_ProbeB, snapshot, task)  # type: ignore[arg-type]

    assert key_a_before == key_a_after, "probe A's key drifted on probe B's schema bump"
    assert key_b_before != key_b_after, "probe B's key did NOT change on its own schema bump"


def test_envelope_version_bump_does_not_invalidate_any_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0003 §Decision: the envelope ``$id`` is metadata; bumping it must
    not touch any probe key. A ``key_for`` that includes envelope version in
    the tuple fails here."""
    from codegenie.cache import keys as keys_mod

    schema_dir = tmp_path / "schema"
    _seed_schema_dir(schema_dir)
    _write_probe_schema(schema_dir, "probe_a", "v0.1.0")
    monkeypatch.setattr(keys_mod, "_SCHEMA_DIR", schema_dir)

    snapshot = _make_snapshot(tmp_path)
    task = Task(type="t", options={})

    key_before = keys_mod.key_for(_ProbeA, snapshot, task)  # type: ignore[arg-type]

    # bump envelope $id only
    envelope_path = schema_dir / "repo_context.schema.json"
    envelope = json.loads(envelope_path.read_text())
    envelope["$id"] = "https://codewizard-sherpa.dev/schemas/repo_context/v0.2.0.json"
    envelope_path.write_text(json.dumps(envelope))

    key_after = keys_mod.key_for(_ProbeA, snapshot, task)  # type: ignore[arg-type]
    assert key_before == key_after, "probe A's key drifted on envelope bump"


def test_per_probe_schema_version_falls_back_to_envelope_on_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC: a probe with no sub-schema file uses ``envelope_schema_version()``.

    Mutation killer: a fallback that raises ``FileNotFoundError`` (no
    try/except) or returns ``""`` (silent default) fails the equality
    assertion."""
    from codegenie.cache import keys as keys_mod

    schema_dir = tmp_path / "schema"
    _seed_schema_dir(schema_dir)
    monkeypatch.setattr(keys_mod, "_SCHEMA_DIR", schema_dir)

    envelope_version = keys_mod.envelope_schema_version()
    assert keys_mod.per_probe_schema_version(_NoSubschemaProbe) == envelope_version  # type: ignore[arg-type]


def test_envelope_version_is_not_in_the_key_tuple(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Direct invariant: the envelope version is computed and exposed, but
    ``key_for`` must not include it. A test that exercises this by inspecting
    the key after independently varying envelope vs per-probe is the strongest
    behavioral pin we can write without exposing internal tuple construction."""
    from codegenie.cache import keys as keys_mod
    from codegenie.hashing import (
        content_hash_of_inputs,
        identity_hash,
    )

    schema_dir = tmp_path / "schema"
    _seed_schema_dir(schema_dir)
    _write_probe_schema(schema_dir, "probe_a", "v0.1.0")
    monkeypatch.setattr(keys_mod, "_SCHEMA_DIR", schema_dir)

    snapshot = _make_snapshot(tmp_path)
    task = Task(type="t", options={})

    expected = identity_hash(
        _ProbeA.name,
        _ProbeA.version,
        keys_mod.per_probe_schema_version(_ProbeA),  # type: ignore[arg-type]
        content_hash_of_inputs(keys_mod.declared_inputs_for(_ProbeA, snapshot)),  # type: ignore[arg-type]
    )
    assert keys_mod.key_for(_ProbeA, snapshot, task) == expected  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# declared_inputs_for — resolver shape (AC-14)
# ---------------------------------------------------------------------------


def test_declared_inputs_for_sorted_dedup_existing_only(tmp_path: Path) -> None:
    """AC: ``declared_inputs_for`` returns the sorted, deduplicated set of
    existing paths matching ``probe.declared_inputs`` globs. Missing paths
    are silently skipped (the cache-miss layer is the right place to surface
    that)."""
    from codegenie.cache.keys import declared_inputs_for

    class TwoGlobProbe:
        name: str = "two_glob"
        version: str = "1.0"
        declared_inputs: list[str] = ["*.txt", "*.txt"]  # duplicate on purpose

    root = tmp_path / "repo"
    root.mkdir()
    (root / "b.txt").write_bytes(b"")
    (root / "a.txt").write_bytes(b"")
    (root / "c.txt").write_bytes(b"")
    snapshot = RepoSnapshot(root=root, git_commit=None, detected_languages={}, config={})

    result = declared_inputs_for(TwoGlobProbe, snapshot)  # type: ignore[arg-type]
    assert [p.name for p in result] == ["a.txt", "b.txt", "c.txt"]
    # determinism: two calls return the same ordering
    assert declared_inputs_for(TwoGlobProbe, snapshot) == result  # type: ignore[arg-type]


def test_declared_inputs_for_does_not_raise_on_missing_paths(tmp_path: Path) -> None:
    """AC-14: missing files are silently dropped, not raised — the
    cache-miss boundary catches that.

    Mutation killer: a resolver that raises ``FileNotFoundError`` here
    leaks the miss into the coordinator boundary."""
    from codegenie.cache.keys import declared_inputs_for

    class NoMatchProbe:
        name: str = "no_match"
        version: str = "1.0"
        declared_inputs: list[str] = ["*.nonesuch"]

    root = tmp_path / "repo"
    root.mkdir()
    snapshot = RepoSnapshot(root=root, git_commit=None, detected_languages={}, config={})
    assert declared_inputs_for(NoMatchProbe, snapshot) == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# S3-06 AC-7 — Catalog-edit invalidates `node_manifest` AND ONLY `node_manifest`
# ---------------------------------------------------------------------------


def _cache_state_from_logs(events: list[dict[str, object]]) -> dict[str, str]:
    """Reduce captured structlog events to ``{probe_name: "hit"|"miss"}``.

    A probe emits exactly one of:

    - ``probe.cache_hit`` (warm path) → ``"hit"``
    - ``probe.success`` with a ``cache_key`` (coordinator-side, after a
      miss + successful run) → ``"miss"``

    The probe-internal ``probe.success`` (without ``cache_key``) is the
    pre-coordinator event from the probe body — filter it out by the
    ``"cache_key" in event`` discriminator (S2-05 pattern of record).
    """
    state: dict[str, str] = {}
    for event in events:
        kind = event.get("event")
        probe = event.get("probe")
        if not isinstance(probe, str):
            continue
        if kind == "probe.cache_hit":
            state[probe] = "hit"
        elif kind == "probe.success" and "cache_key" in event:
            state.setdefault(probe, "miss")
    return state


def _gather_with_logs(repo: Path) -> tuple[int, list[dict[str, object]]]:
    """Run ``codegenie gather`` once under structlog capture; return
    ``(exit_code, captured_events)``.
    """
    import structlog
    from click.testing import CliRunner

    from codegenie.cli import cli

    with structlog.testing.capture_logs() as logs:
        result = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])
    return result.exit_code, list(logs)


@pytest.fixture
def _disable_cli_configure_logging_unit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mirror of ``tests/integration/probes/conftest.py``'s autouse seam
    disablement — needed here because this unit test invokes the CLI for
    the S3-06 AC-7 catalog-invalidation-scope assertion. Without this,
    ``CliRunner.invoke`` re-runs :func:`codegenie.logging.configure_logging`
    which replaces structlog's active processor chain and silently drops
    every captured event (S2-05 burned this).
    """
    import codegenie.cli

    monkeypatch.setattr(codegenie.cli, "_seam_configure_logging", lambda verbose: None)


def _seed_pnpm_native_repo(tmp_path: Path, *, with_catalog: bool = True) -> Path:
    """Lay out a minimal pnpm-native repo plus the catalog file at the
    relative path ``NodeManifestProbe.declared_inputs`` references.

    ``with_catalog`` controls whether the catalog file is dropped; the
    invalidation test needs it present from the cold run so the catalog
    contributes to ``node_manifest``'s ``content_hash``.
    """
    fixture_src = Path(__file__).parent.parent / "fixtures" / "node_pnpm_native"
    repo = tmp_path / "repo"
    import shutil

    shutil.copytree(fixture_src, repo)
    if with_catalog:
        catalog_src = (
            Path(__file__).parent.parent.parent
            / "src"
            / "codegenie"
            / "catalogs"
            / "native_modules.yaml"
        )
        catalog_dst = repo / "src" / "codegenie" / "catalogs" / "native_modules.yaml"
        catalog_dst.parent.mkdir(parents=True, exist_ok=True)
        catalog_dst.write_bytes(catalog_src.read_bytes())
    return repo


@pytest.mark.parametrize("sibling", ["language_detection", "node_build_system"])
def test_catalog_edit_invalidates_only_node_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sibling: str,
    _disable_cli_configure_logging_unit: None,
) -> None:
    """S3-06 AC-7 — ADR-0006 cache-scope invariant.

    Editing ``native_modules.yaml`` MUST invalidate ``node_manifest``
    (the catalog is in its ``declared_inputs``) and MUST NOT invalidate
    any sibling probe (their ``declared_inputs`` do not include the
    catalog). Both directions are pinned by the aggregate assertion
    ``{p: s in cache_state if s == "miss"} == {"node_manifest"}``; a
    surgical-flush mutant (e.g., a buggy invalidation that flushed
    everything except ``ci``) would be caught.

    The parametrize covers each currently-registered Phase 0 / Phase 1
    sibling. As Phase 1 lands ``ci`` / ``deployment`` / ``test_inventory``
    probes (S4-01..S4-03), the parametrize set grows by listing them
    here — zero edits to the test body.
    """
    repo = _seed_pnpm_native_repo(tmp_path)
    catalog_path = repo / "src" / "codegenie" / "catalogs" / "native_modules.yaml"
    original_size = catalog_path.stat().st_size

    cold_exit, cold_logs = _gather_with_logs(repo)
    assert cold_exit == 0, f"cold gather failed: events={cold_logs}"
    cold_state = _cache_state_from_logs(cold_logs)
    # On cold, every probe should miss (no prior cache entries).
    assert "node_manifest" in cold_state, cold_logs
    assert cold_state["node_manifest"] == "miss"

    # Size-changing catalog edit: bump catalog_version: 1 → 10 (+1 byte).
    # ADR-0006 §Tradeoffs row 4 — the (path, size) cache key requires a
    # size change; a same-size YAML edit does NOT invalidate (pinned by
    # the companion xfail test below).
    text = catalog_path.read_text(encoding="utf-8")
    bumped = text.replace("catalog_version: 1", "catalog_version: 10")
    catalog_path.write_text(bumped, encoding="utf-8")
    new_size = catalog_path.stat().st_size
    assert new_size != original_size, (
        "ADR-0006 (path, size) cache key requires a size change; bump "
        "1→2 is forbidden (same byte count). Got original_size="
        f"{original_size}, new_size={new_size}."
    )

    warm_exit, warm_logs = _gather_with_logs(repo)
    assert warm_exit == 0, f"warm gather failed: events={warm_logs}"
    warm_state = _cache_state_from_logs(warm_logs)

    # Aggregate assertion — pins BOTH directions:
    #   - under-invalidation: node_manifest MUST be a miss (the catalog
    #     change must propagate to the cache key)
    #   - over-invalidation: only probes whose declared_inputs *legitimately*
    #     contain the catalog file glob are misses. node_manifest reads the
    #     catalog directly; ``gitleaks`` (S6-07) declares ``**/*.yaml`` so
    #     it scans every yaml — including this catalog — for secret leakage,
    #     and a catalog yaml-bytes edit is a legitimate cache-key change for
    #     it. A surgical-flush mutant that touched a non-yaml-consuming
    #     probe (e.g., ``adrs`` / ``conventions``) still fails this.
    misses = {p for p, s in warm_state.items() if s == "miss"}
    _expected_subset = {"node_manifest", "gitleaks"}
    assert "node_manifest" in misses, (
        f"S3-06 AC-7 — catalog edit must invalidate node_manifest; "
        f"got misses={misses}, warm_state={warm_state}"
    )
    assert misses <= _expected_subset, (
        f"S3-06 AC-7 — catalog edit invalidated unexpected probes "
        f"(over-flush). Expected misses ⊆ {_expected_subset}; got "
        f"misses={misses}, warm_state={warm_state}"
    )

    # Per-sibling pinning (parametrize): each sibling must be a hit.
    assert warm_state.get(sibling) == "hit", (
        f"sibling {sibling} cache state: expected 'hit', got "
        f"{warm_state.get(sibling)!r}; warm_state={warm_state}"
    )


@pytest.mark.xfail(
    reason="ADR-0006 §Tradeoffs row 4: same-size YAML edit does NOT "
    "invalidate (accepted Phase 1 limitation; cache key is (path, size)). "
    "xfail pins this as a regression-tracked invariant rather than docs.",
    strict=True,
)
def test_same_size_catalog_edit_does_not_invalidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _disable_cli_configure_logging_unit: None,
) -> None:
    """ADR-0006 §Tradeoffs row 4 — companion invariant: a same-size
    YAML edit (e.g., ``catalog_version: 1`` → ``catalog_version: 2``)
    does NOT change the (path, size) cache key and therefore does NOT
    invalidate ``node_manifest``. This is the documented limitation;
    the xfail pins it so a future cache-key-strengthening change (e.g.,
    including content hash in addition to size) surfaces here as an
    unexpected pass.
    """
    repo = _seed_pnpm_native_repo(tmp_path)
    catalog_path = repo / "src" / "codegenie" / "catalogs" / "native_modules.yaml"
    original_size = catalog_path.stat().st_size

    cold_exit, _ = _gather_with_logs(repo)
    assert cold_exit == 0

    # Same-size edit: 1 → 2 keeps byte count unchanged.
    text = catalog_path.read_text(encoding="utf-8")
    bumped = text.replace("catalog_version: 1", "catalog_version: 2")
    catalog_path.write_text(bumped, encoding="utf-8")
    assert catalog_path.stat().st_size == original_size, (
        "same-size edit precondition failed; bytes drifted"
    )

    warm_exit, warm_logs = _gather_with_logs(repo)
    assert warm_exit == 0
    warm_state = _cache_state_from_logs(warm_logs)
    # The xfail expectation: under the current cache-key shape, the
    # catalog change is invisible — node_manifest WILL hit. When the
    # cache key is strengthened (Phase 2 amendment), this test starts
    # passing as a "miss" and the xfail decorator must be dropped.
    assert warm_state.get("node_manifest") == "miss", (
        f"expected ADR-0006 limitation: same-size edit invalidates node_manifest; got {warm_state}"
    )
