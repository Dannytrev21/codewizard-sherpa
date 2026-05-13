"""Tests for ``codegenie.audit`` — Pydantic v2 `ProbeExecutionRecord` + `RunRecord` (ADR-0004).

Pins the dual audit anchors (`cache_key` + `blob_sha256` — Gap 2 closure),
`extra="forbid"` + `frozen=True`, the `exit_status` literal, the empty-string
`blob_sha256` sentinel for `exit_status="skipped"` per ADR-0004 §Consequences,
and the canonical `os_kernel_sha` field name on `RunRecord` (the Data model
spelling that the arch §Component design's `os_kernel` is inconsistent with).
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from codegenie.audit import ProbeExecutionRecord, RunRecord

_SHA = "sha256:" + "0" * 64


def _exec_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        name="x",
        version="1",
        cache_hit=False,
        wall_clock_ms=10,
        exit_status="ok",
        cache_key=_SHA,
        blob_sha256=_SHA,
    )
    base.update(overrides)
    return base


def test_probe_execution_record_requires_cache_key_and_blob_sha256() -> None:
    bad = _exec_kwargs()
    bad.pop("cache_key")
    with pytest.raises(ValidationError):
        ProbeExecutionRecord(**bad)
    bad = _exec_kwargs()
    bad.pop("blob_sha256")
    with pytest.raises(ValidationError):
        ProbeExecutionRecord(**bad)


def test_extra_forbid_rejects_unknown_field_on_probe_execution_record() -> None:
    with pytest.raises(ValidationError):
        ProbeExecutionRecord(**_exec_kwargs(unexpected_field="bad"))


def test_exit_status_literal_rejection() -> None:
    """Catches a bare `exit_status: str` mutant."""
    with pytest.raises(ValidationError):
        ProbeExecutionRecord(**_exec_kwargs(exit_status="bogus"))


def test_frozen_mutation_raises() -> None:
    """Catches the `frozen=True` -> `frozen=False` mutant."""
    record = ProbeExecutionRecord(**_exec_kwargs())
    with pytest.raises(ValidationError):
        record.cache_key = "sha256:" + "f" * 64  # type: ignore[misc]


def test_skipped_accepts_empty_blob_sha256_sentinel() -> None:
    """ADR-0004 §Consequences: skipped executions carry `blob_sha256=""`."""
    record = ProbeExecutionRecord(**_exec_kwargs(exit_status="skipped", blob_sha256=""))
    assert record.exit_status == "skipped"
    assert record.blob_sha256 == ""


def test_run_record_happy_path_and_extra_forbid() -> None:
    record = RunRecord(
        cli_version="0.1.0",
        sherpa_commit="abc1234",
        python_version="3.11.10",
        os_kernel_sha="sha256:" + "a" * 64,
        probes=[ProbeExecutionRecord(**_exec_kwargs())],
        tool_versions={"git": "2.45.0"},
        yaml_sha256="sha256:" + "b" * 64,
    )
    assert record.os_kernel_sha.startswith("sha256:")
    assert record.probes[0].name == "x"
    # Round-trip
    dumped = record.model_dump()
    assert dumped["os_kernel_sha"] == record.os_kernel_sha
    # extra="forbid" rejects unknown fields
    with pytest.raises(ValidationError):
        RunRecord(  # type: ignore[call-arg]
            cli_version="0.1.0",
            sherpa_commit="abc1234",
            python_version="3.11.10",
            os_kernel_sha="sha256:" + "a" * 64,
            probes=[],
            tool_versions={},
            yaml_sha256="sha256:" + "b" * 64,
            unexpected_field="reject me",
        )
