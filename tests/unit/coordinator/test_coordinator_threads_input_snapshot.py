"""Coordinator-wiring tests for S1-08 input-snapshot pass.

Pins AC-16 (per-probe snapshot computation), AC-17 (_make_probe_context
signature extension), AC-18 (_dispatch_one threads snapshot + adapter onto
the runtime ctx) and AC-19 (Gap-1 closure across concurrent edit).
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from codegenie.coordinator.coordinator import _make_probe_context, gather
from codegenie.coordinator.input_snapshot import (
    compute_input_snapshot,
    make_parsed_manifest_adapter,
)
from codegenie.coordinator.parsed_manifest_memo import ParsedManifestMemo
from codegenie.probes.base import InputFingerprint, ProbeOutput, RepoSnapshot
from tests.unit._coordinator_fixtures import FakeProbe, make_snapshot, make_task


# ---------------------------------------------------------------------------
# T-14 — AC-16 + AC-17 + AC-18: gather() threads snapshot + adapter onto ctx
# ---------------------------------------------------------------------------
async def test_gather_threads_input_snapshot_and_adapter_to_ctx(
    tmp_path: Path,
    fresh_cache: Any,
    fresh_sanitizer: Any,
    fresh_config: Any,
) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"name": "x"}))
    captured: dict[str, Any] = {}

    async def _capture(_repo: RepoSnapshot, ctx: Any) -> ProbeOutput:
        captured["input_snapshot"] = ctx.input_snapshot
        captured["parsed_manifest"] = ctx.parsed_manifest
        return ProbeOutput(
            schema_slice={"ok": True},
            raw_artifacts=[],
            confidence="high",
            duration_ms=1,
            warnings=[],
            errors=[],
        )

    probe = FakeProbe(
        name="stub-input-snapshot",
        declared_inputs=["package.json"],
        _run=_capture,
    )
    await gather(
        make_snapshot(tmp_path),
        make_task(),
        [probe],
        fresh_config,
        fresh_cache,
        fresh_sanitizer,
    )

    snap = captured["input_snapshot"]
    adapter = captured["parsed_manifest"]
    assert isinstance(snap, frozenset)
    assert any(isinstance(fp, InputFingerprint) and fp.path.endswith("package.json") for fp in snap)
    assert callable(adapter)
    parsed = adapter(tmp_path / "package.json")
    assert parsed is not None and parsed["name"] == "x"


# ---------------------------------------------------------------------------
# T-15 — AC-16: per-probe snapshot independence
# ---------------------------------------------------------------------------
async def test_two_probes_in_one_gather_see_independent_snapshots(
    tmp_path: Path,
    fresh_cache: Any,
    fresh_sanitizer: Any,
    fresh_config: Any,
) -> None:
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
    seen: dict[str, set[str]] = {}

    def _make_capture(probe_name: str) -> Any:
        async def _capture(_repo: RepoSnapshot, ctx: Any) -> ProbeOutput:
            seen[probe_name] = {Path(fp.path).name for fp in ctx.input_snapshot}
            return ProbeOutput(
                schema_slice={"ok": True},
                raw_artifacts=[],
                confidence="high",
                duration_ms=1,
                warnings=[],
                errors=[],
            )

        return _capture

    probe_a = FakeProbe(
        name="probe-a", declared_inputs=["package.json"], _run=_make_capture("probe-a")
    )
    probe_b = FakeProbe(
        name="probe-b", declared_inputs=["pnpm-lock.yaml"], _run=_make_capture("probe-b")
    )
    await gather(
        make_snapshot(tmp_path),
        make_task(),
        [probe_a, probe_b],
        fresh_config,
        fresh_cache,
        fresh_sanitizer,
    )
    # Each probe's snapshot must cover only its own declared_inputs.
    # Mutation: union across probes would put both filenames in both sets.
    assert seen == {"probe-a": {"package.json"}, "probe-b": {"pnpm-lock.yaml"}}


# ---------------------------------------------------------------------------
# T-16 — AC-19: Gap-1 closure across a mid-gather byte change
# ---------------------------------------------------------------------------
def test_snapshot_pins_parse_against_concurrent_byte_change(tmp_path: Path) -> None:
    p = tmp_path / "package.json"
    p.write_text(json.dumps({"name": "A"}))
    memo = ParsedManifestMemo()

    class _Probe:
        name = "stub"
        declared_inputs = ["package.json"]

    snap_a = compute_input_snapshot(_Probe(), tmp_path)
    adapter_a = make_parsed_manifest_adapter(snap_a, memo)
    parsed_a = adapter_a(p)
    assert parsed_a is not None and parsed_a["name"] == "A"

    # Overwrite bytes mid-gather — do NOT recompute snapshot.
    p.write_text(json.dumps({"name": "BBBBBBBB"}))  # different bytes, different size

    parsed_a_again = adapter_a(p)
    assert parsed_a_again is parsed_a  # IDENTITY preserved (Gap 1 closed)

    # Separately: a fresh snapshot + adapter sees the new bytes.
    snap_b = compute_input_snapshot(_Probe(), tmp_path)
    adapter_b = make_parsed_manifest_adapter(snap_b, memo)
    parsed_b = adapter_b(p)
    assert parsed_b is not None and parsed_b["name"] == "BBBBBBBB"
    assert parsed_b is not parsed_a


# ---------------------------------------------------------------------------
# AC-17 signature pin: `_make_probe_context` accepts the two kw-only params.
# ---------------------------------------------------------------------------
def test_make_probe_context_signature_has_input_snapshot_kwarg() -> None:
    sig = inspect.signature(_make_probe_context)
    assert "input_snapshot" in sig.parameters
    assert "parsed_manifest" in sig.parameters
    # Both should be keyword-only (defaulted to preserve existing call sites).
    is_kw_only = sig.parameters["input_snapshot"].kind == inspect.Parameter.KEYWORD_ONLY
    pm_kw_only = sig.parameters["parsed_manifest"].kind == inspect.Parameter.KEYWORD_ONLY
    assert is_kw_only and pm_kw_only


pytestmark = pytest.mark.filterwarnings("ignore::ResourceWarning")
