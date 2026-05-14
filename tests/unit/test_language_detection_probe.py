"""Red tests for S4-01 — ``LanguageDetectionProbe``.

Twelve tests pinning AC-1..AC-10 from
``docs/phases/00-bullet-tracer-foundations/stories/S4-01-language-detection-probe.md``.

Helpers (``_snapshot``, ``_ctx``, ``_run``) are defined inline per the story's
Validation-notes bullet ("Inlined helper definitions ... so each red test is
reproducible") — no conftest dependency.
"""

from __future__ import annotations

import asyncio
import os
from logging import getLogger
from pathlib import Path

import pytest
import structlog
from structlog.testing import capture_logs

from codegenie.probes.base import ProbeContext, ProbeOutput, RepoSnapshot


def _snapshot(root: Path) -> RepoSnapshot:
    return RepoSnapshot(root=root, git_commit=None, detected_languages={}, config={})


def _ctx(root: Path) -> ProbeContext:
    return ProbeContext(
        cache_dir=root / ".cache",
        output_dir=root / ".out",
        workspace=root / ".ws",
        logger=getLogger("test"),
        config={},
    )


def _run(probe: object, root: Path) -> ProbeOutput:
    return asyncio.run(probe.run(_snapshot(root), _ctx(root)))  # type: ignore[attr-defined,no-any-return]


# 1. Happy path — counts JS fixture, primary, raw_artifacts, warnings, duration.
def test_counts_js_fixture(tmp_path: Path) -> None:
    (tmp_path / "a.js").write_text("//")
    (tmp_path / "b.js").write_text("//")
    (tmp_path / "c.ts").write_text("//")
    (tmp_path / "d.py").write_text("#")
    from codegenie.probes.language_detection import LanguageDetectionProbe

    output = _run(LanguageDetectionProbe(), tmp_path)
    # S2-01 added `framework_hints` and `monorepo`; Phase 0 values are
    # byte-stable (AC-8 in S2-01 + the additive-key regression assertion in
    # tests/unit/probes/test_language_detection_extended.py).
    assert output.schema_slice == {
        "language_stack": {
            "counts": {"javascript": 2, "typescript": 1, "python": 1},
            "primary": "javascript",
            "framework_hints": [],
            "monorepo": None,
        }
    }
    assert output.confidence == "high"
    assert output.errors == []
    assert output.warnings == []
    assert output.raw_artifacts == []
    assert output.duration_ms >= 0


# 2. Pydantic validation — slice survives the trust-boundary walker on both
#    happy and empty-repo cases (AC-8 — `primary: null` must traverse the
#    Pydantic JSON-leaf walker without rejection).
def test_schema_slice_passes_pydantic_validator(tmp_path: Path) -> None:
    (tmp_path / "x.js").write_text("//")
    from codegenie.coordinator.validator import _ProbeOutputValidator
    from codegenie.probes.language_detection import LanguageDetectionProbe

    output = _run(LanguageDetectionProbe(), tmp_path)
    _ProbeOutputValidator.model_validate(
        {"schema_slice": output.schema_slice, "confidence": output.confidence}
    )


def test_schema_slice_passes_pydantic_validator_empty_repo(tmp_path: Path) -> None:
    from codegenie.coordinator.validator import _ProbeOutputValidator
    from codegenie.probes.language_detection import LanguageDetectionProbe

    output = _run(LanguageDetectionProbe(), tmp_path)
    assert output.schema_slice["language_stack"]["primary"] is None
    _ProbeOutputValidator.model_validate(
        {"schema_slice": output.schema_slice, "confidence": output.confidence}
    )


# 3. Contract conformance — subset check on declared_inputs, exact equality on
#    layer/tier/requires/name/version. Kills the mutation `["**/*.py"]` that
#    would survive a pre-hardened inequality check.
def test_contract_conformance() -> None:
    from codegenie.probes.base import Probe
    from codegenie.probes.language_detection import _EXT_TO_LANG, LanguageDetectionProbe

    assert issubclass(LanguageDetectionProbe, Probe)
    assert LanguageDetectionProbe.name == "language_detection"
    assert LanguageDetectionProbe.version == "0.1.1"  # type: ignore[attr-defined]
    assert LanguageDetectionProbe.layer == "A"
    assert LanguageDetectionProbe.tier == "base"
    assert LanguageDetectionProbe.requires == []
    # Subset check: every language in _EXT_TO_LANG has at least one glob whose
    # casefolded suffix maps to it. Kills `["**/*.py"]`-only mutation.
    languages_in_inputs = {
        _EXT_TO_LANG[ext]
        for ext in (Path(g).suffix.casefold() for g in LanguageDetectionProbe.declared_inputs)
        if ext in _EXT_TO_LANG
    }
    assert set(_EXT_TO_LANG.values()).issubset(languages_in_inputs)
    assert LanguageDetectionProbe.declared_inputs != ["**/*"]


# 4. Empty repo — primary None, confidence high, language_stack still present.
def test_empty_repo(tmp_path: Path) -> None:
    from codegenie.probes.language_detection import LanguageDetectionProbe

    output = _run(LanguageDetectionProbe(), tmp_path)
    # S2-01 additive extension — see comment in test_counts_js_fixture.
    assert output.schema_slice == {
        "language_stack": {
            "counts": {},
            "primary": None,
            "framework_hints": [],
            "monorepo": None,
        }
    }
    assert output.confidence == "high"
    assert output.errors == []


# 5. Vendor-dir deny-list — node_modules etc. are not walked.
def test_skips_well_known_vendor_dirs(tmp_path: Path) -> None:
    (tmp_path / "a.js").write_text("//")
    (tmp_path / "node_modules").mkdir()
    for i in range(100):
        d = tmp_path / "node_modules" / f"pkg-{i}"
        d.mkdir()
        (d / "index.js").write_text("//")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config.js").write_text("//")  # adversarial; should NOT count
    from codegenie.probes.language_detection import LanguageDetectionProbe

    output = _run(LanguageDetectionProbe(), tmp_path)
    assert output.schema_slice["language_stack"]["counts"] == {"javascript": 1}


# 6. Case-insensitive extension.
def test_case_insensitive_extension(tmp_path: Path) -> None:
    (tmp_path / "FOO.JS").write_text("//")
    (tmp_path / "BAR.Ts").write_text("//")
    from codegenie.probes.language_detection import LanguageDetectionProbe

    output = _run(LanguageDetectionProbe(), tmp_path)
    assert output.schema_slice["language_stack"]["counts"] == {"javascript": 1, "typescript": 1}


# 7. Alpha tie-break is deterministic — kills max(counts, key=counts.get) mutation.
def test_primary_alpha_tiebreak(tmp_path: Path) -> None:
    (tmp_path / "a.js").write_text("//")
    (tmp_path / "b.js").write_text("//")
    (tmp_path / "c.py").write_text("#")
    (tmp_path / "d.py").write_text("#")
    from codegenie.probes.language_detection import LanguageDetectionProbe

    output = _run(LanguageDetectionProbe(), tmp_path)
    counts = output.schema_slice["language_stack"]["counts"]
    assert counts == {"javascript": 2, "python": 2}
    assert output.schema_slice["language_stack"]["primary"] == "javascript"  # alpha < "python"


# 8. Escaped symlink → skip + probe.symlink.escaped event; payload is relative
#    path, no resolved target.
def test_symlink_escape_skipped_and_logged(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside_target.js"
    outside.write_text("//")
    link = tmp_path / "escape.js"
    os.symlink(outside, link)
    from codegenie.probes.language_detection import LanguageDetectionProbe

    with capture_logs() as logs:
        output = _run(LanguageDetectionProbe(), tmp_path)
    events = [e for e in logs if e.get("event") == "probe.symlink.escaped"]
    assert len(events) == 1
    assert events[0]["path"] == "escape.js"
    # Resolved target must never appear in the log payload — sanitizer is NOT
    # a structlog processor (ADR-0008).
    assert str(outside) not in str(events[0])
    assert str(outside.resolve()) not in str(events[0])
    assert output.schema_slice["language_stack"]["counts"] == {}


# 9. Broken symlink → skip + probe.symlink.broken; no exception leaks.
def test_broken_symlink_skipped_and_logged(tmp_path: Path) -> None:
    os.symlink(tmp_path / "no_such_target.js", tmp_path / "dangling.js")
    from codegenie.probes.language_detection import LanguageDetectionProbe

    with capture_logs() as logs:
        output = _run(LanguageDetectionProbe(), tmp_path)
    events = [e for e in logs if e.get("event") == "probe.symlink.broken"]
    assert len(events) == 1
    assert events[0]["path"] == "dangling.js"
    assert output.confidence == "high"


# 10. PermissionError mid-walk → confidence=low, probe.failure event,
#     no exception leak, language_stack wrapper still present.
def test_permission_error_demotes_confidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.js").write_text("//")
    import codegenie.probes.language_detection as ld

    real_scandir = os.scandir

    def boom(path: object) -> object:
        if str(path) == str(tmp_path):
            raise PermissionError("simulated")
        return real_scandir(path)  # type: ignore[arg-type]

    monkeypatch.setattr(ld.os, "scandir", boom)
    from codegenie.probes.language_detection import LanguageDetectionProbe

    with capture_logs() as logs:
        output = _run(LanguageDetectionProbe(), tmp_path)
    assert output.confidence == "low"
    assert output.errors and output.errors[0].startswith("PermissionError")
    assert "language_stack" in output.schema_slice  # wrapper still present even on error path
    failure_events = [e for e in logs if e.get("event") == "probe.failure"]
    assert len(failure_events) == 1
    assert failure_events[0]["probe"] == "language_detection"
    assert "PermissionError" in str(failure_events[0])


# 11. Happy-path lifecycle — exactly one probe.start + one probe.success;
#     no probe.failure.
def test_lifecycle_events_happy_path(tmp_path: Path) -> None:
    (tmp_path / "a.js").write_text("//")
    from codegenie.probes.language_detection import LanguageDetectionProbe

    with capture_logs() as logs:
        _run(LanguageDetectionProbe(), tmp_path)
    starts = [e for e in logs if e.get("event") == "probe.start"]
    successes = [e for e in logs if e.get("event") == "probe.success"]
    failures = [e for e in logs if e.get("event") == "probe.failure"]
    assert len(starts) == 1 and starts[0]["probe"] == "language_detection"
    assert len(successes) == 1 and successes[0]["probe"] == "language_detection"
    assert successes[0]["confidence"] == "high"
    assert successes[0]["count_total"] == 1
    assert failures == []


# 12. Registration — probe class appears in default_registry; for_task selects it.
def test_probe_registered() -> None:
    from codegenie.probes import default_registry
    from codegenie.probes.language_detection import LanguageDetectionProbe

    all_names = {p.name for p in default_registry.all_probes()}
    assert "language_detection" in all_names
    selected = default_registry.for_task("__bullet_tracer__", frozenset({"unknown"}))
    # Registry.for_task returns probe CLASSES (not instances).
    assert LanguageDetectionProbe in selected


# --- S2-01 regression siblings -----------------------------------------------


# 13. Phase 0 declared_inputs entries are a contiguous prefix of the extended
#     list (additive extension; no removals/reorderings).
def test_declared_inputs_additive() -> None:
    from codegenie.probes.language_detection import LanguageDetectionProbe

    phase_0_inputs = [
        "**/*.js",
        "**/*.mjs",
        "**/*.cjs",
        "**/*.ts",
        "**/*.tsx",
        "**/*.py",
        "**/*.go",
        "**/*.rs",
        "**/*.java",
        "**/*.rb",
        "**/*.php",
    ]
    declared = LanguageDetectionProbe.declared_inputs
    assert declared[: len(phase_0_inputs)] == phase_0_inputs
    new_entries = declared[len(phase_0_inputs) :]
    assert "package.json" in new_entries
    assert "pnpm-workspace.yaml" in new_entries
    assert "lerna.json" in new_entries
    assert "nx.json" in new_entries
    assert "turbo.json" in new_entries


# 14. The module-import _ERRORS assertion enforces ADR-0007 ID pattern at boot.
def test_module_import_asserts_error_ids() -> None:
    """Mutating an error ID into a malformed form must trip the module-level assertion.

    Strategy: re-execute the module-level assertion expression with a poisoned
    set. The probe module's assertion lives at import-time; we replay it here
    to confirm it would refuse a malformed ID. This is fail-loud discipline
    (Rule 12) — the assertion exists *because* a stale/wrong-cased ID would
    silently leak past CI without it.
    """
    import re

    from codegenie.probes.language_detection import _WARNING_ID_RE

    poisoned = frozenset({"package_json.size_cap_exceeded", "BadID", "package_json.malformed"})
    bad = [eid for eid in poisoned if not re.match(_WARNING_ID_RE, eid)]
    assert bad == ["BadID"]


__all__: list[str] = []  # pytest collects by function-name; no public exports.


# Silence the unused-import warning for ``structlog`` — it's imported so the
# tests-suite implicitly verifies the dependency is installed in the editable
# environment (ADR-0010 emits via structlog).
_ = structlog
