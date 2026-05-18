"""S6-08 — unit tests for ``TestCoverageMappingProbe`` (Layer G #5).

The TDD plan ACs (3, 5, 6, 7, 18, 19, 21, 22) are exercised here; the
Layer-G architectural invariants (no shared base, no subprocess, no
platform detection, ABC attribute pinning) are extended in
``test_scanner_loc_ceiling.py`` by adding the module to
``SCANNER_MODULES``. The freshness-registration + Open/Closed promise
sit in their own files (``tests/unit/indices/test_phase2_freshness_registrations.py``,
``tests/integration/probes/test_rule_pack_drift_marks_stale.py``).

Test-naming gotcha: the file is ``test_test_coverage_mapping.py`` (one
``test_`` prefix from the pytest collection convention, one from the
module under test); pytest collects it cleanly.
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
from pathlib import Path
from typing import cast

import hypothesis.strategies as st
import pytest
from hypothesis import HealthCheck, given, settings

from codegenie.probes._shared.scanner_outcome import (
    ScannerFailed,
    ScannerRan,
    ScannerSkipped,
)
from codegenie.probes.base import ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.layer_g import test_coverage_mapping as tcm
from codegenie.probes.registry import default_registry


def _snapshot(root: Path) -> RepoSnapshot:
    root.mkdir(parents=True, exist_ok=True)
    return RepoSnapshot(root=root, git_commit=None, detected_languages={}, config={})


def _ctx(tmp_path: Path) -> ProbeContext:
    return ProbeContext(
        cache_dir=tmp_path / ".cache",
        output_dir=tmp_path / ".out",
        workspace=tmp_path / ".work",
        logger=logging.getLogger("tcm-test"),
        config={},
    )


def _run(repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
    return asyncio.run(tcm.TestCoverageMappingProbe().run(repo, ctx))


def _slice_of(output: ProbeOutput) -> tcm.TestCoverageSlice:
    return tcm.TestCoverageSlice.model_validate(output.schema_slice["test_coverage_mapping"])


# ---------------------------------------------------------------------------
# AC-6 — missing artifact path
# ---------------------------------------------------------------------------


def test_no_coverage_artifact_is_upstream_unavailable_not_failed(tmp_path: Path) -> None:
    """AC-6. Dominant path in production repos. Mutation caught: any
    code path that raises past the probe boundary on this case; any
    reflexive widening of the closed ScannerSkipped.reason literal set
    would type-check-fail under mypy --strict."""
    output = _run(_snapshot(tmp_path / "repo"), _ctx(tmp_path))
    slice_ = _slice_of(output)
    assert isinstance(slice_.outcome, ScannerSkipped)
    assert slice_.outcome.reason == "upstream_unavailable"
    assert slice_.format is None
    assert output.confidence == "low"


# ---------------------------------------------------------------------------
# AC-5, AC-21 — lcov + Istanbul actual record shapes (not just counts)
# ---------------------------------------------------------------------------


def test_lcov_parses_into_specific_coverage_records(tmp_path: Path) -> None:
    """AC-5. Pins the actual CoverageRecord shape — a stub that returns
    ScannerRan(()) plus files_seen=1 after seeing one SF: line without
    parsing DA: rows would pass a thin counts-only test."""
    cov = tmp_path / "repo" / "coverage" / "lcov.info"
    cov.parent.mkdir(parents=True)
    cov.write_text("TN:\nSF:src/payments/processor.ts\nDA:1,5\nDA:2,5\nDA:3,0\nend_of_record\n")
    output = _run(_snapshot(tmp_path / "repo"), _ctx(tmp_path))
    slice_ = _slice_of(output)
    assert isinstance(slice_.outcome, ScannerRan)
    assert slice_.format == "lcov"
    assert slice_.files_seen == 1
    assert slice_.findings_detail == (
        tcm.CoverageRecord(
            test_file=None,
            source_file="src/payments/processor.ts",
            lines_covered=(1, 2),  # line 3 had DA:3,0 → excluded.
        ),
    )


def test_istanbul_parses_into_specific_coverage_records(tmp_path: Path) -> None:
    """AC-5. Mutation caught: confusing lcov layout with Istanbul JSON
    layout — different smart constructor; also catches a no-op parser
    returning ScannerRan(()) plus format='istanbul'."""
    cov = tmp_path / "repo" / "coverage" / "coverage-final.json"
    cov.parent.mkdir(parents=True)
    cov.write_text(
        json.dumps(
            {
                "src/payments/processor.ts": {
                    "path": "src/payments/processor.ts",
                    "statementMap": {
                        "0": {"start": {"line": 1}},
                        "1": {"start": {"line": 2}},
                    },
                    "s": {"0": 5, "1": 0},
                }
            }
        )
    )
    output = _run(_snapshot(tmp_path / "repo"), _ctx(tmp_path))
    slice_ = _slice_of(output)
    assert isinstance(slice_.outcome, ScannerRan)
    assert slice_.format == "istanbul"
    assert slice_.files_seen == 1
    assert slice_.findings_detail == (
        tcm.CoverageRecord(
            test_file=None,
            source_file="src/payments/processor.ts",
            lines_covered=(1,),  # statement 0 had 5 hits; statement 1 had 0.
        ),
    )


# ---------------------------------------------------------------------------
# AC-7 — failure shapes (parse error / oversized)
# ---------------------------------------------------------------------------


def test_truncated_lcov_yields_scanner_failed_with_diagnostic(tmp_path: Path) -> None:
    """AC-7. Pins exit_code=0, reason=None (closed sum not widened),
    and a substring of the diagnostic. A parser that returns
    ScannerFailed for EVERY input (no actual parsing) would pass an
    isinstance-only check; this test will not."""
    cov = tmp_path / "repo" / "coverage" / "lcov.info"
    cov.parent.mkdir(parents=True)
    cov.write_text("TN:\nSF:src/payments/processor.ts\nDA:1,")  # truncated mid-record
    output = _run(_snapshot(tmp_path / "repo"), _ctx(tmp_path))
    slice_ = _slice_of(output)
    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.exit_code == 0
    assert slice_.outcome.reason is None
    diag = slice_.outcome.stderr_tail.lower()
    assert "truncated" in diag or "parse" in diag


def test_oversized_coverage_yields_scanner_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-7. Monkeypatch the cap rather than write 50 MB to disk."""
    cov = tmp_path / "repo" / "coverage" / "lcov.info"
    cov.parent.mkdir(parents=True)
    cov.write_bytes(b"TN:\nSF:foo\nend_of_record\n" + b"X" * 1024)
    monkeypatch.setattr(tcm, "_MAX_BYTES", 8)
    output = _run(_snapshot(tmp_path / "repo"), _ctx(tmp_path))
    slice_ = _slice_of(output)
    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.exit_code == 0
    assert slice_.outcome.reason is None
    assert "oversized" in slice_.outcome.stderr_tail.lower()


def test_malformed_istanbul_yields_scanner_failed(tmp_path: Path) -> None:
    """AC-7. Istanbul JSON that does not match the expected per-file
    layout → ScannerFailed with a parse-error diagnostic."""
    cov = tmp_path / "repo" / "coverage" / "coverage-final.json"
    cov.parent.mkdir(parents=True)
    cov.write_text(json.dumps({"src/a.ts": "not-an-object"}))
    output = _run(_snapshot(tmp_path / "repo"), _ctx(tmp_path))
    slice_ = _slice_of(output)
    assert isinstance(slice_.outcome, ScannerFailed)
    assert slice_.outcome.reason is None
    assert "parse" in slice_.outcome.stderr_tail.lower()


# ---------------------------------------------------------------------------
# AC-18 — empty-coverage edge case (well-formed, zero records)
# ---------------------------------------------------------------------------


def test_empty_lcov_yields_scanner_ran_zero_records(tmp_path: Path) -> None:
    """AC-18. ScannerRan with empty findings tuple, NOT ScannerSkipped
    (artifact IS present) and NOT ScannerFailed (parses cleanly)."""
    cov = tmp_path / "repo" / "coverage" / "lcov.info"
    cov.parent.mkdir(parents=True)
    cov.write_text("TN:\n")
    output = _run(_snapshot(tmp_path / "repo"), _ctx(tmp_path))
    slice_ = _slice_of(output)
    assert isinstance(slice_.outcome, ScannerRan)
    assert slice_.findings_detail == ()
    assert slice_.files_seen == 0
    assert slice_.format == "lcov"
    assert output.confidence == "low"


def test_empty_istanbul_yields_scanner_ran_zero_records(tmp_path: Path) -> None:
    """AC-18. Empty Istanbul JSON ({}) → ScannerRan(()), files_seen=0."""
    cov = tmp_path / "repo" / "coverage" / "coverage-final.json"
    cov.parent.mkdir(parents=True)
    cov.write_text("{}")
    output = _run(_snapshot(tmp_path / "repo"), _ctx(tmp_path))
    slice_ = _slice_of(output)
    assert isinstance(slice_.outcome, ScannerRan)
    assert slice_.findings_detail == ()
    assert slice_.files_seen == 0
    assert slice_.format == "istanbul"


# ---------------------------------------------------------------------------
# AC-19 — deterministic precedence: lcov wins
# ---------------------------------------------------------------------------


def test_lcov_wins_when_both_artifacts_present(tmp_path: Path) -> None:
    """AC-19. Pins precedence; mutation caught: a future contributor
    reordering the lcov-vs-istanbul ternary silently changes behavior."""
    cov_dir = tmp_path / "repo" / "coverage"
    cov_dir.mkdir(parents=True)
    (cov_dir / "lcov.info").write_text("TN:\nSF:src/a.ts\nDA:1,1\nend_of_record\n")
    (cov_dir / "coverage-final.json").write_text(
        json.dumps(
            {
                "src/b.ts": {
                    "path": "src/b.ts",
                    "statementMap": {"0": {"start": {"line": 99}}},
                    "s": {"0": 1},
                }
            }
        )
    )
    output = _run(_snapshot(tmp_path / "repo"), _ctx(tmp_path))
    slice_ = _slice_of(output)
    assert slice_.format == "lcov"
    assert isinstance(slice_.outcome, ScannerRan)
    assert {r.source_file for r in slice_.findings_detail} == {"src/a.ts"}


# ---------------------------------------------------------------------------
# AC-21 — CoverageRecord field set is frozen
# ---------------------------------------------------------------------------


def test_coverage_record_fields_are_frozen() -> None:
    """AC-21. No per-line attribution leaks into Phase 2's slice; Phase
    3's TestInventoryAdapter projects against this raw evidence."""
    assert frozenset(tcm.CoverageRecord.model_fields.keys()) == frozenset(
        {"test_file", "source_file", "lines_covered"}
    )


# ---------------------------------------------------------------------------
# AC-22 — Probe ABC contract (only `async def run(self, repo, ctx)`)
# ---------------------------------------------------------------------------


def test_probe_run_is_async_two_arg_and_no_private_run() -> None:
    """AC-22. Mutation caught: a contributor adding a sync `_run` 'for
    testing' silently bypasses the coordinator's await dispatch."""
    source = Path(cast(str, tcm.__file__)).read_text()
    tree = ast.parse(source)
    cls = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "TestCoverageMappingProbe"
    )
    methods = {
        n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "run" in methods, "run() must be defined on the probe"
    assert isinstance(methods["run"], ast.AsyncFunctionDef), "run must be async"
    args = methods["run"].args.args
    assert [a.arg for a in args] == ["self", "repo", "ctx"], "exactly (self, repo, ctx)"
    assert "_run" not in methods, "no private _run shim — coordinator dispatch is the only path"
    assert "run_sync" not in methods, "no synchronous shim"


# ---------------------------------------------------------------------------
# AC-5 — architectural: consume kernels, do NOT re-implement
# ---------------------------------------------------------------------------


def test_no_inline_size_cap_or_lcov_parser() -> None:
    """AC-5. The file consumes `open_capped` (transitively via
    `_lcov_scanner.scan_records` and `safe_json.load`) and
    `_lcov_scanner.scan_records`; it does NOT re-implement them.
    Mutation caught: copying lcov state-machine code back inline would
    break the rule-of-three reuse precedent."""
    source = Path(cast(str, tcm.__file__)).read_text()
    tree = ast.parse(source)
    import_from: list[str] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module is not None:
            for name in n.names:
                import_from.append(f"{n.module}.{name.name}")
    assert any(i == "codegenie.probes._lcov_scanner.scan_records" for i in import_from), (
        "must import scan_records from the shared kernel"
    )
    assert any(i.startswith("codegenie.parsers.safe_json") for i in import_from), (
        "must import safe_json"
    )
    plain_imports = [
        alias.name for n in ast.walk(tree) if isinstance(n, ast.Import) for alias in n.names
    ]
    assert "re" not in plain_imports


# ---------------------------------------------------------------------------
# AC-3 — registry registration shape
# ---------------------------------------------------------------------------


def test_registry_entry_heaviness_is_medium() -> None:
    """AC-3. Bumping to 'heavy' would cost the coordinator a runs_last
    slot the Layer G shape budgets for."""
    entry = next(
        e
        for e in default_registry._entries  # noqa: SLF001 — sibling Layer D precedent
        if e.cls.name == "test_coverage_mapping"
    )
    assert entry.heaviness == "medium"


def test_declared_inputs_pinned() -> None:
    """AC-3. declared_inputs is load-bearing for the content-addressed
    cache key (default cache_strategy='content'); pinning it ensures a
    future contributor cannot silently empty the list and disable caching."""
    assert tcm.TestCoverageMappingProbe.declared_inputs == [
        "coverage/lcov.info",
        "coverage/coverage-final.json",
    ]


# ---------------------------------------------------------------------------
# Determinism ratchet
# ---------------------------------------------------------------------------


def test_two_consecutive_gathers_are_byte_identical(tmp_path: Path) -> None:
    """Determinism ratchet (Phase 1 precedent). Mutation caught: dict
    iteration order leakage; non-deterministic sort over findings;
    timestamp escape into the slice."""
    cov = tmp_path / "repo" / "coverage" / "lcov.info"
    cov.parent.mkdir(parents=True)
    cov.write_text("TN:\nSF:a.ts\nDA:1,1\nend_of_record\nSF:b.ts\nDA:1,1\nend_of_record\n")
    out1 = _run(_snapshot(tmp_path / "repo"), _ctx(tmp_path))
    out2 = _run(_snapshot(tmp_path / "repo"), _ctx(tmp_path))
    assert json.dumps(out1.schema_slice, sort_keys=True) == json.dumps(
        out2.schema_slice, sort_keys=True
    )


# ---------------------------------------------------------------------------
# Property — unknown lcov prefixes silently dropped
# ---------------------------------------------------------------------------


@given(
    extras=st.lists(
        st.sampled_from(
            [
                "BRF:1\n",
                "BRH:1\n",
                "\n",
                "  \n",
                "FN:1,foo\n",
                "FNDA:1,foo\n",
                "FNF:1\n",
                "FNH:1\n",
                "LF:3\n",
                "LH:2\n",
            ]
        ),
        max_size=20,
    ),
)
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_unknown_lcov_prefixes_silently_dropped(extras: list[str], tmp_path: Path) -> None:
    """`_lcov_scanner`'s documented contract: unknown lcov prefixes are
    silently dropped. The new probe inherits this from the shared
    kernel."""
    body = "TN:\nSF:src/a.ts\n" + "".join(extras) + "DA:1,1\nDA:2,0\nend_of_record\n"
    cov = tmp_path / "repo" / "coverage" / "lcov.info"
    cov.parent.mkdir(parents=True, exist_ok=True)
    cov.write_text(body)
    output = _run(_snapshot(tmp_path / "repo"), _ctx(tmp_path))
    slice_ = _slice_of(output)
    assert isinstance(slice_.outcome, ScannerRan)
    assert slice_.files_seen == 1
    assert {r.source_file for r in slice_.findings_detail} == {"src/a.ts"}
