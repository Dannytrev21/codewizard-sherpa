"""Tests for the ``cache/keys.py`` special-token dispatch (S5-02 Step 0).

S5-02 is the first consumer of the ``image-digest:<resolved>`` mechanism
S1-09 introduced on :class:`ProbeContext`; this story lands the cache-side
dispatch (``_resolve_special_token`` + ``CacheKeyError``).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from codegenie.cache import keys as cache_keys
from codegenie.cache.keys import CacheKeyError, key_for
from codegenie.probes.base import ProbeContext, RepoSnapshot, Task


class _SyntheticProbe:
    name = "synth_special_token"
    version = "0.0.1"
    declared_inputs: list[str] = []


def _seed_schema(schema_dir: Path) -> None:
    (schema_dir / "probes").mkdir(parents=True, exist_ok=True)
    envelope = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://codewizard-sherpa.dev/schemas/repo_context/v0.1.0.json",
    }
    (schema_dir / "repo_context.schema.json").write_text(json.dumps(envelope))


def _make_ctx(resolver: Any = None) -> ProbeContext:
    return ProbeContext(
        cache_dir=Path("/tmp/cache"),
        output_dir=Path("/tmp/out"),
        workspace=Path("/tmp/ws"),
        logger=logging.getLogger("test"),
        config={},
        image_digest_resolver=resolver,
    )


def _make_snapshot(root: Path) -> RepoSnapshot:
    return RepoSnapshot(root=root, git_commit=None, detected_languages={}, config={})


@pytest.fixture()
def schema_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    sd = tmp_path / "schema"
    _seed_schema(sd)
    monkeypatch.setattr(cache_keys, "_SCHEMA_DIR", sd)
    return sd


@pytest.fixture()
def snapshot(tmp_path: Path) -> RepoSnapshot:
    root = tmp_path / "repo"
    root.mkdir()
    return _make_snapshot(root)


# ---------------------------------------------------------------------------
# Dispatch — image-digest token recognition + key sensitivity
# ---------------------------------------------------------------------------


def test_image_digest_resolver_changes_cache_key(schema_dir: Path, snapshot: RepoSnapshot) -> None:
    """Two resolvers returning distinct digests produce distinct cache keys."""

    class _Probe(_SyntheticProbe):
        declared_inputs = ["image-digest:<resolved>"]

    probe = _Probe()
    task = Task(type="t", options={})
    ctx_a = _make_ctx(resolver=lambda _root: "sha256:aaaa")
    ctx_b = _make_ctx(resolver=lambda _root: "sha256:bbbb")

    key_a = key_for(probe, snapshot, task, ctx=ctx_a)
    key_b = key_for(probe, snapshot, task, ctx=ctx_b)
    assert key_a != key_b


def test_same_resolver_produces_byte_identical_key(
    schema_dir: Path, snapshot: RepoSnapshot
) -> None:
    class _Probe(_SyntheticProbe):
        declared_inputs = ["image-digest:<resolved>"]

    probe = _Probe()
    task = Task(type="t", options={})
    ctx = _make_ctx(resolver=lambda _root: "sha256:cafef00ddead")
    assert key_for(probe, snapshot, task, ctx=ctx) == key_for(probe, snapshot, task, ctx=ctx)


def test_three_unresolved_paths_collapse_to_same_key(
    schema_dir: Path, snapshot: RepoSnapshot
) -> None:
    """``ctx is None`` / resolver unbound / resolver-returns-None / resolver-raises
    all fold to the same unresolved-sentinel cache key."""

    class _Probe(_SyntheticProbe):
        declared_inputs = ["image-digest:<resolved>"]

    probe = _Probe()
    task = Task(type="t", options={})
    ctx_none = None
    ctx_unbound = _make_ctx(resolver=None)
    ctx_returns_none = _make_ctx(resolver=lambda _root: None)

    def _raises(_root: Path) -> str:
        raise RuntimeError("boom")

    ctx_raises = _make_ctx(resolver=_raises)

    k_none = key_for(probe, snapshot, task, ctx=ctx_none)
    k_unbound = key_for(probe, snapshot, task, ctx=ctx_unbound)
    k_returns = key_for(probe, snapshot, task, ctx=ctx_returns_none)
    k_raises = key_for(probe, snapshot, task, ctx=ctx_raises)

    assert k_none == k_unbound == k_returns == k_raises


# ---------------------------------------------------------------------------
# Unknown special token — fail loud
# ---------------------------------------------------------------------------


def test_unknown_special_token_raises_cache_key_error(
    schema_dir: Path, snapshot: RepoSnapshot
) -> None:
    class _Probe(_SyntheticProbe):
        declared_inputs = ["bogus:<resolved>"]

    probe = _Probe()
    task = Task(type="t", options={})

    with pytest.raises(CacheKeyError) as exc_info:
        key_for(probe, snapshot, task, ctx=_make_ctx())

    msg = str(exc_info.value)
    assert "unknown_special_token" in msg
    assert "bogus:<resolved>" in msg


# ---------------------------------------------------------------------------
# Recognition syntax — entries lacking the literal placeholder still rglob
# ---------------------------------------------------------------------------


def test_non_token_entry_still_rglobs_unchanged(schema_dir: Path, snapshot: RepoSnapshot) -> None:
    """``Dockerfile`` is a glob, not a token — still resolved via rglob."""
    (snapshot.root / "Dockerfile").write_text("FROM scratch\n")

    class _Probe(_SyntheticProbe):
        declared_inputs = ["Dockerfile"]

    probe = _Probe()
    task = Task(type="t", options={})
    key_a = key_for(probe, snapshot, task, ctx=_make_ctx())
    # Changing the file size invalidates the key (path/size hash).
    (snapshot.root / "Dockerfile").write_text("FROM alpine:latest\nRUN echo hi\n")
    key_b = key_for(probe, snapshot, task, ctx=_make_ctx())
    assert key_a != key_b


def test_no_ctx_means_unresolved_sentinel(schema_dir: Path, snapshot: RepoSnapshot) -> None:
    """``key_for(..., ctx=None)`` is well-defined and stable."""

    class _Probe(_SyntheticProbe):
        declared_inputs = ["image-digest:<resolved>"]

    probe = _Probe()
    task = Task(type="t", options={})
    k1 = key_for(probe, snapshot, task)  # default ctx=None
    k2 = key_for(probe, snapshot, task)
    assert k1 == k2
