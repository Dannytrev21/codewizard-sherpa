"""Coordinator-wiring smoke tests for ``ParsedManifestMemo`` injection — S1-07.

Pins AC-16, AC-17, AC-18: a single memo is constructed per :func:`gather`
call, threaded through ``_dispatch_one`` to ``_make_probe_context``, and
attached to every per-dispatch ``BudgetingContext`` as ``parsed_manifest``.
Two sequential gathers must build two distinct memos; within one gather
every probe must see the *same* callable identity.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from codegenie.coordinator.coordinator import gather
from codegenie.probes.base import ProbeOutput, RepoSnapshot
from tests.unit._coordinator_fixtures import FakeProbe, make_snapshot, make_task


# AC-16 — coordinator threads parsed_manifest onto every ctx
async def test_gather_threads_parsed_manifest_to_ctx(
    tmp_path: Path,
    fresh_cache: Any,
    fresh_sanitizer: Any,
    fresh_config: Any,
) -> None:
    captured: dict[str, Any] = {}

    async def _assert_ctx(_repo: RepoSnapshot, ctx: Any) -> ProbeOutput:
        captured["parsed_manifest"] = ctx.parsed_manifest
        captured["is_callable"] = callable(ctx.parsed_manifest)
        return ProbeOutput(
            schema_slice={"ok": True},
            raw_artifacts=[],
            confidence="high",
            duration_ms=1,
            warnings=[],
            errors=[],
        )

    probe = FakeProbe(name="stub-a", _run=_assert_ctx)
    await gather(
        make_snapshot(tmp_path),
        make_task(),
        [probe],
        fresh_config,
        fresh_cache,
        fresh_sanitizer,
    )
    assert captured["is_callable"] is True
    assert captured["parsed_manifest"] is not None


# AC-17 — cross-gather isolation: two sequential gathers => two distinct memos.
# We capture ``parsed_manifest.__self__`` (the underlying memo) because
# Python builds a fresh bound method on every ``memo.get`` access, making
# ``id(parsed_manifest)`` unstable in general. The *instance* identity is the
# load-bearing invariant: two distinct memo instances ⇒ two distinct caches.
async def test_cross_gather_isolation(
    tmp_path: Path,
    fresh_cache: Any,
    fresh_sanitizer: Any,
    fresh_config: Any,
) -> None:
    seen: list[Any] = []

    async def _capture(_repo: RepoSnapshot, ctx: Any) -> ProbeOutput:
        seen.append(ctx.parsed_manifest.__self__)
        return ProbeOutput(
            schema_slice={"ok": True},
            raw_artifacts=[],
            confidence="high",
            duration_ms=1,
            warnings=[],
            errors=[],
        )

    snap = make_snapshot(tmp_path)
    task = make_task()
    # Distinct probe names per gather so the per-snapshot cache key differs
    # and ``_dispatch_one`` does not short-circuit on a cache hit — the
    # invariant under test is memo-instance identity, not cache behavior.
    await gather(
        snap,
        task,
        [FakeProbe(name="stub-a-1", _run=_capture)],
        fresh_config,
        fresh_cache,
        fresh_sanitizer,
    )
    await gather(
        snap,
        task,
        [FakeProbe(name="stub-a-2", _run=_capture)],
        fresh_config,
        fresh_cache,
        fresh_sanitizer,
    )
    assert len(seen) == 2
    # Mutation: module-level memo (singleton) would make these `is`-equal.
    assert seen[0] is not seen[1]


# AC-18 — same-gather sharing: every probe in one gather sees the same memo.
# Same underlying-memo identity ⇒ shared cache state ⇒ AC-6 hit-count
# invariant holds for S2-04's warm-path test across the four
# package.json-consuming probes.
async def test_same_gather_sharing_across_probes(
    tmp_path: Path,
    fresh_cache: Any,
    fresh_sanitizer: Any,
    fresh_config: Any,
) -> None:
    seen: list[Any] = []

    async def _capture(_repo: RepoSnapshot, ctx: Any) -> ProbeOutput:
        seen.append(ctx.parsed_manifest.__self__)
        return ProbeOutput(
            schema_slice={"ok": True},
            raw_artifacts=[],
            confidence="high",
            duration_ms=1,
            warnings=[],
            errors=[],
        )

    p1 = FakeProbe(name="stub-a", tier="base", _run=_capture)
    p2 = FakeProbe(name="stub-b", tier="task_specific", _run=_capture)
    await gather(
        make_snapshot(tmp_path),
        make_task(),
        [p1, p2],
        fresh_config,
        fresh_cache,
        fresh_sanitizer,
    )
    assert len(seen) == 2
    # Mutation: rebuilding the memo per-probe would split these identities.
    assert seen[0] is seen[1]


# AC-16 — the threaded callable is the memo's ``get`` (resolves a manifest
# on disk when invoked from a probe). Closes the loop on the wiring story
# end-to-end: a probe that calls ``ctx.parsed_manifest(p)`` gets the parsed
# contents, not None.
async def test_threaded_callable_actually_parses_package_json(
    tmp_path: Path,
    fresh_cache: Any,
    fresh_sanitizer: Any,
    fresh_config: Any,
) -> None:
    import json as _json

    pkg = tmp_path / "package.json"
    pkg.write_text(_json.dumps({"name": "demo-pkg"}))

    captured: dict[str, Any] = {}

    async def _read(_repo: RepoSnapshot, ctx: Any) -> ProbeOutput:
        result = ctx.parsed_manifest(pkg)
        captured["result"] = dict(result) if result is not None else None
        return ProbeOutput(
            schema_slice={"ok": True},
            raw_artifacts=[],
            confidence="high",
            duration_ms=1,
            warnings=[],
            errors=[],
        )

    probe = FakeProbe(name="reader", _run=_read)
    await gather(
        make_snapshot(tmp_path),
        make_task(),
        [probe],
        fresh_config,
        fresh_cache,
        fresh_sanitizer,
    )
    assert captured["result"] == {"name": "demo-pkg"}


pytestmark = pytest.mark.filterwarnings(
    # FakeProbe is a non-decorated stand-in for a real probe; suppress any
    # ResourceWarnings the asyncio event-loop emits for transient subprocess
    # tracking objects unrelated to this story.
    "ignore::ResourceWarning",
)
