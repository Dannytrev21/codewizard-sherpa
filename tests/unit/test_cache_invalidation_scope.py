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
