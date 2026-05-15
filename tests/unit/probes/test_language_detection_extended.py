"""Red tests for S2-01 — ``LanguageDetectionProbe`` extension.

Ten tests pinning AC-1..AC-12 from
``docs/phases/01-context-gather-layer-a-node/stories/S2-01-language-detection-extension.md``.

Helpers (``_run_probe``, ``_phase0_baseline_keys``, ``_envelope_with_language_stack``,
``_minimal_envelope_with``) are defined inline at the top of the file — no
conftest dependency (matches the Phase 0 ``test_language_detection_probe.py``
idiom).
"""

from __future__ import annotations

import asyncio
import os
from logging import getLogger
from pathlib import Path
from typing import Any

import pytest

from codegenie.errors import SchemaValidationError
from codegenie.probes.base import ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.schema.validator import validate

# ---------- helpers ----------------------------------------------------------


def _snapshot(root: Path) -> RepoSnapshot:
    return RepoSnapshot(root=root, git_commit=None, detected_languages={}, config={})


def _ctx(root: Path, **overrides: Any) -> ProbeContext:
    base: dict[str, Any] = dict(
        cache_dir=root / ".cache",
        output_dir=root / ".out",
        workspace=root / ".ws",
        logger=getLogger("test"),
        config={},
    )
    base.update(overrides)
    return ProbeContext(**base)


def _run_probe(root: Path, *, ctx_overrides: dict[str, Any] | None = None) -> ProbeOutput:
    from codegenie.probes.language_detection import LanguageDetectionProbe

    probe = LanguageDetectionProbe()
    overrides = ctx_overrides or {}
    return asyncio.run(probe.run(_snapshot(root), _ctx(root, **overrides)))


def _phase0_baseline_keys(_tmp_path: Path) -> list[str]:
    """Phase 0 shipped ``counts`` + ``primary`` only — sorted for stable compare."""
    return ["counts", "primary"]


def _envelope_with_language_stack(slice_overrides: dict[str, Any]) -> dict[str, Any]:
    base_slice: dict[str, Any] = {
        "counts": {},
        "primary": None,
        "framework_hints": [],
        "monorepo": None,
    }
    base_slice.update(slice_overrides)
    return {
        "schema_version": "0.1.0",
        "generated_at": "2026-05-14T00:00:00Z",
        "repo": {"root": "/x", "git_commit": None},
        "probes": {"language_detection": {"language_stack": base_slice}},
    }


def _minimal_envelope_with(*, probe_block: str, extras: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "0.1.0",
        "generated_at": "2026-05-14T00:00:00Z",
        "repo": {"root": "/x", "git_commit": None},
        "probes": {probe_block: extras},
    }


# ---------- T-1 — framework hints positive AND negative ---------------------


def test_framework_hints_detected_from_deps_and_devdeps(tmp_path: Path) -> None:
    """AC-2 — seed-dict intersection across deps + devDeps; non-seed deps omitted."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text("export {}")
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"express": "^4.0.0", "lodash": "^4.0.0"},'
        ' "devDependencies": {"fastify": "^4.0.0"}}'
    )
    out = _run_probe(tmp_path)
    hints = out.schema_slice["language_stack"]["framework_hints"]
    assert hints == ["express", "fastify"]
    assert "lodash" not in hints


# ---------- T-2 — monorepo detection + precedence + union markers ----------


def test_monorepo_detected_via_turbo_marker(tmp_path: Path) -> None:
    """AC-3 + AC-4 — turbo beats the workspaces fallback; markers is sorted union."""
    (tmp_path / "package.json").write_text('{"workspaces": ["packages/*"]}')
    (tmp_path / "turbo.json").write_text('{"$schema": "https://turbo.build/schema.json"}')
    out = _run_probe(tmp_path)
    monorepo = out.schema_slice["language_stack"]["monorepo"]
    assert monorepo is not None
    assert monorepo["tool"] == "turbo"
    assert monorepo["markers"] == ["package.json", "turbo.json"]


# ---------- T-3 — Phase 0 fields byte-stable when no package.json ---------


def test_no_package_json_leaves_phase0_fields_byte_stable(tmp_path: Path) -> None:
    """AC-8 + AC-11 — absent package.json keeps Phase 0 keys byte-stable and confidence high."""
    (tmp_path / "a.go").write_text("package main")
    out = _run_probe(tmp_path)
    stack = out.schema_slice["language_stack"]
    assert stack["framework_hints"] == []
    assert stack["monorepo"] is None
    assert "counts" in stack
    assert "primary" in stack
    assert out.errors == []
    assert out.confidence == "high"
    # Phase 0 key-set regression — extra keys would fail this.
    assert sorted(
        k for k in stack.keys() if k not in {"framework_hints", "monorepo"}
    ) == _phase0_baseline_keys(tmp_path)


# ---------- T-4 — ADR-0004 extra-field rejection ---------------------------


def test_sub_schema_rejects_extra_field_under_language_detection() -> None:
    """AC-9 — slice additionalProperties:false rejects rogue keys at the expected pointer."""
    envelope = _envelope_with_language_stack({"rogue_field": "x"})
    with pytest.raises(SchemaValidationError) as excinfo:
        validate(envelope)
    msg = str(excinfo.value)
    # The error message names the violating slice path (jsonschema's
    # json_path uses dotted form: `$.probes.language_detection.language_stack`).
    assert "probes.language_detection.language_stack" in msg
    assert "rogue_field" in msg


# ---------- T-5 — ADR-0007 pattern on BOTH warnings[] and errors[] --------


@pytest.mark.parametrize(
    "field,bad_id,good_id",
    [
        ("warnings", "This Helm chart looks production-ready", "package_json.size_cap_exceeded"),
        ("warnings", "CamelCase.id", "package_json.symlink_refused"),
        ("errors", "missing_dot", "package_json.malformed"),
        ("errors", "trailing.", "package_json.size_cap_exceeded"),
    ],
)
def test_warning_and_error_id_pattern_enforced(field: str, bad_id: str, good_id: str) -> None:
    """AC-10 — ADR-0007 pattern applies to both warnings[] and errors[] in the slice schema."""
    bad_env = _envelope_with_language_stack({field: [bad_id]})
    good_env = _envelope_with_language_stack({field: [good_id]})
    with pytest.raises(SchemaValidationError):
        validate(bad_env)
    validate(good_env)  # passes


# ---------- T-6 — size-cap → confidence=medium + errors[] ------------------


def test_oversized_package_json_demotes_confidence_via_errors(tmp_path: Path) -> None:
    """AC-11 — SizeCapExceeded → confidence=medium; typed ID lands in ProbeOutput.errors."""
    big = '{"x": "' + ("A" * (6 * 1024 * 1024)) + '"}'
    (tmp_path / "package.json").write_text(big)
    out = _run_probe(tmp_path)
    assert out.confidence == "medium"
    assert "package_json.size_cap_exceeded" in out.errors
    assert out.schema_slice["language_stack"]["framework_hints"] == []
    assert out.schema_slice["language_stack"]["monorepo"] is None


# ---------- T-7 — symlink-refused → confidence=low + errors[] -------------


def test_symlink_package_json_refused_demotes_to_low(tmp_path: Path) -> None:
    """AC-11 — out-of-repo symlink hits O_NOFOLLOW; confidence=low; hints don't leak."""
    outside = tmp_path.parent / f"outside-{tmp_path.name}.json"
    outside.write_text('{"dependencies": {"express": "^4.0.0"}}')
    try:
        (tmp_path / "package.json").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("filesystem does not support symlinks")
    out = _run_probe(tmp_path)
    assert out.confidence == "low"
    assert "package_json.symlink_refused" in out.errors
    assert out.schema_slice["language_stack"]["framework_hints"] == []
    outside.unlink(missing_ok=True)


# ---------- T-8 — malformed JSON → confidence=medium + errors[] ----------


def test_malformed_package_json_demotes_to_medium(tmp_path: Path) -> None:
    """AC-11 — MalformedJSONError yields confidence=medium and the typed ID lands in errors[]."""
    (tmp_path / "package.json").write_text('{"dependencies": {"express": "^4.0.0"')  # truncated
    out = _run_probe(tmp_path)
    assert out.confidence == "medium"
    assert "package_json.malformed" in out.errors
    assert out.schema_slice["language_stack"]["framework_hints"] == []


# ---------- T-9 — memo seam (called when present; falls back when None) --


def test_memo_consumed_when_available_and_fallback_when_none(tmp_path: Path) -> None:
    """AC-1 — ctx.parsed_manifest is invoked when provided; falls back to safe_json when None."""
    (tmp_path / "package.json").write_text('{"dependencies": {"express": "^4.0.0"}}')

    # Case A — memo provided; probe must call it (load-bearing for S2-04 warm path).
    calls: list[Path] = []

    def memo(path: Path) -> dict[str, Any]:
        calls.append(path)
        import json

        return json.loads((tmp_path / "package.json").read_text())

    out_a = _run_probe(tmp_path, ctx_overrides={"parsed_manifest": memo})
    assert len(calls) == 1
    assert calls[0] == (tmp_path / "package.json")
    assert out_a.schema_slice["language_stack"]["framework_hints"] == ["express"]

    # Case B — memo None; probe falls back to safe_json.load (edge case 12).
    out_b = _run_probe(tmp_path, ctx_overrides={"parsed_manifest": None})
    assert out_b.schema_slice["language_stack"]["framework_hints"] == ["express"]


# ---------- T-10 — determinism property: sort + dedup -------------------


@pytest.mark.parametrize(
    "dep_order",
    [
        [("next", "^14"), ("express", "^4"), ("fastify", "^4")],
        [("fastify", "^4"), ("next", "^14"), ("express", "^4")],
        [("express", "^4"), ("next", "^14"), ("fastify", "^4")],
    ],
)
def test_framework_hints_deterministic_sort_and_dedup(
    tmp_path: Path, dep_order: list[tuple[str, str]]
) -> None:
    """AC-2 — output sorted + deduped across deps/devDeps regardless of input order."""
    import json

    deps = dict(dep_order)
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": deps, "devDependencies": {"express": "^4"}})
    )
    hints = _run_probe(tmp_path).schema_slice["language_stack"]["framework_hints"]
    assert hints == ["express", "fastify", "next"]


# ---------- T-bonus — workspaces shape acceptance ------------------------


@pytest.mark.parametrize(
    "ws_value,expected_hit",
    [
        ('["packages/*"]', True),
        ('{"packages": ["a"]}', True),
        ("null", False),
        ("[]", False),
        ("{}", False),
        ("false", False),
    ],
)
def test_workspaces_field_shape_acceptance(
    tmp_path: Path, ws_value: str, expected_hit: bool
) -> None:
    """AC-5 — workspaces truthy (list/object) triggers; null/empty/false treated as absent."""
    (tmp_path / "package.json").write_text(f'{{"workspaces": {ws_value}}}')
    out = _run_probe(tmp_path)
    monorepo = out.schema_slice["language_stack"]["monorepo"]
    if expected_hit:
        assert monorepo is not None
        assert monorepo["tool"] == "workspaces"
        assert monorepo["markers"] == ["package.json"]
    else:
        assert monorepo is None


# ---------- T-bonus2 — multi-monorepo precedence ------------------------


def test_multi_monorepo_precedence_pnpm_beats_turbo(tmp_path: Path) -> None:
    """AC-3 — pnpm-workspace.yaml > turbo > nx > lerna > workspaces (precedence chain)."""
    (tmp_path / "package.json").write_text('{"workspaces": ["a"]}')
    (tmp_path / "pnpm-workspace.yaml").write_text("packages:\n  - a\n")
    (tmp_path / "turbo.json").write_text("{}")
    (tmp_path / "nx.json").write_text("{}")
    (tmp_path / "lerna.json").write_text("{}")
    out = _run_probe(tmp_path)
    monorepo = out.schema_slice["language_stack"]["monorepo"]
    assert monorepo is not None
    assert monorepo["tool"] == "pnpm-workspaces"
    assert monorepo["markers"] == sorted(
        ["package.json", "pnpm-workspace.yaml", "turbo.json", "nx.json", "lerna.json"]
    )


# ---------- T-12 — S5-01 AC-12 retrofit: DepthCapExceeded → low confidence
# ---------- + typed error_id on ProbeOutput.errors -------------------------


def test_deeply_nested_package_json_demotes_to_low_via_depth_cap(tmp_path: Path) -> None:
    """S5-01 AC-12 — a depth-bombed package.json fires :class:`DepthCapExceeded`
    inside ``safe_json.load``; the probe catches it, demotes confidence to
    ``low``, and lands ``package_json.depth_cap_exceeded`` on ``ProbeOutput.errors``.

    The retrofit is two-line additive — without it, the exception escapes the
    catch-tuple and the run() method blows up at the coordinator boundary
    (or worse, silently produces an empty ``errors`` list with the
    walk-error fallback). Closed-world equality on ``errors`` is the kill.
    """
    # Build a deeply-nested JSON in memory: ``{"a": {"a": {"a": ...}}}`` to
    # depth > 64 (the safe_json default). Under 5 MB on disk.
    depth = 200
    payload = "1"
    for _ in range(depth):
        payload = '{"a": ' + payload + "}"
    (tmp_path / "package.json").write_text(payload)

    out = _run_probe(tmp_path)
    assert out.confidence == "low", out
    assert out.errors == ["package_json.depth_cap_exceeded"], out.errors
    # Slice still emits — primary is None, hints empty (failed pkg.json read).
    assert out.schema_slice["language_stack"]["framework_hints"] == []
    assert out.schema_slice["language_stack"]["monorepo"] is None


# Silence imported-but-unused lint for `os` if Black/ruff complains.
_ = os
