"""S5-05 — ADR-0010 contract test: non-Node repo envelope shape.

A Go-only repo produces an envelope where ``language_stack`` is
populated and the three Node-only probes (``node_build_system``,
``node_manifest``, ``test_inventory``) are ABSENT under ``probes``
(ADR-0010 absence-is-the-contract for language-filtered probes).

``ci`` and ``deployment`` declare ``applies_to_languages = ["*"]`` and
therefore RUN on every repo — ADR-0010 permits both shapes
(present-with-empty OR absent) for ``"*"``-applicability probes; the
S5-04 ``non_node_go`` fixture has no CI/deployment markers, so each
probe ran-and-produced-empty.
"""

from __future__ import annotations

import json
from pathlib import Path

from codegenie.schema.validator import validate as validate_envelope
from tests.integration.probes.conftest import (
    _copy_tree,
    _invoke_gather,
    _load_envelope,
    assert_only_language_stack,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures"
_NODE_ONLY_PROBES = ("node_build_system", "node_manifest", "test_inventory")


def test_non_node_go_envelope_shape(tmp_path: Path) -> None:
    """AC-NN-1..4 + AC-NN-7 — Go-only repo absence + slice content + schema validity."""
    repo = _copy_tree(FIXTURE_ROOT / "non_node_go", tmp_path / "repo")

    result = _invoke_gather(repo)
    assert result.exit_code == 0, result.output

    envelope = _load_envelope(repo)

    # AC-NN-3 + AC-NN-4 — three Node-only probes absent; ci/deployment may
    # be present-but-empty (ADR-0010).
    assert_only_language_stack(envelope)

    # AC-NN-2 — primary slice content.
    ls = envelope["probes"]["language_detection"]["language_stack"]
    assert ls["primary"] == "go", ls
    assert ls["counts"].get("go", 0) >= 2, ls
    assert ls["monorepo"] is None, ls

    # AC-NN-4 — if ci/deployment are present, their inner slices are empty
    # (no markers in the fixture).
    probes = envelope["probes"]
    if "ci" in probes:
        ci_inner = probes["ci"].get("ci", {})
        assert ci_inner.get("workflow_files", []) == [], ci_inner
        assert ci_inner.get("provider") is None, ci_inner
    if "deployment" in probes:
        dp_inner = probes["deployment"].get("deployment", {})
        assert dp_inner.get("type") == "none", dp_inner

    # AC-NN-7 — envelope validates via the production seam (proves
    # ADR-0010: a Go-only envelope is schema-valid even without the
    # Node-only slices).
    validate_envelope(envelope)


def test_non_node_go_audit_records_skipped_for_node_only(tmp_path: Path) -> None:
    """AC-NN-5 — audit run-record records ``exit_status == "skipped"`` for
    every Node-only probe, with the empty-string sentinels that
    :class:`codegenie.audit.ProbeExecutionRecord` documents.

    Asserting on the three signals (``exit_status``, ``cache_key``,
    ``blob_sha256``) together kills the primitive-obsession class of
    mutants — a serializer drift that emits ``"skip"`` or flips
    ``cache_hit`` to ``True`` is caught by the cross-field consistency
    check.
    """
    repo = _copy_tree(FIXTURE_ROOT / "non_node_go", tmp_path / "repo")
    result = _invoke_gather(repo)
    assert result.exit_code == 0, result.output

    runs_dir = repo / ".codegenie" / "context" / "runs"
    run_files = sorted(runs_dir.glob("*.json"))
    assert run_files, f"no run records under {runs_dir}"
    record = json.loads(run_files[-1].read_text())
    by_name = {p["name"]: p for p in record["probes"]}

    for probe in _NODE_ONLY_PROBES:
        row = by_name.get(probe)
        assert row is not None, f"{probe} missing from run-record; got={sorted(by_name)}"
        assert row["exit_status"] == "skipped", row
        assert row["cache_hit"] is False, row
        assert row["cache_key"] == "", row
        assert row["blob_sha256"] == "", row


def test_non_node_go_registry_filter_couples_to_detected_languages(
    tmp_path: Path,
) -> None:
    """AC-NN-6 — the set of envelope probe keys equals the runnable set
    for ``detected_languages = {"go"}``.

    Cross-checks the prelude-pass + ``applies()`` filter against the
    Phase-1 probe inventory. Renames the ``primary`` language (e.g., the
    fixture flipping to JavaScript via a renamed source file) would
    change the runnable set; this test catches a misaligned fixture or
    a regressed filter.
    """
    repo = _copy_tree(FIXTURE_ROOT / "non_node_go", tmp_path / "repo")
    result = _invoke_gather(repo)
    assert result.exit_code == 0, result.output

    envelope = _load_envelope(repo)
    actual = set(envelope["probes"].keys())

    # The three Node-only probes are filter-absent; the universal probes
    # (``applies_to_languages = ["*"]``) ran and produced (possibly empty)
    # slices: ``language_detection`` / ``ci`` / ``deployment`` and (Phase 2
    # S4-01) ``index_health`` — the load-bearing freshness probe. Phase 2
    # S5-03 added four Layer C marker probes (dockerfile + entrypoint +
    # shell_usage + certificate) which are also universal and emit a typed
    # ``confidence=unavailable`` slice when the marker / sibling slice is
    # absent. Phase 2 S5-04 added ``sbom`` + ``cve`` which are likewise
    # universal — on a non-Node repo with no upstream runtime-trace slice
    # they emit ``ScannerSkipped(reason="upstream_unavailable")``. Phase 2
    # S6-05 added ``ownership`` (Layer E CODEOWNERS parser) — universal,
    # emits ``OwnershipSlice(source_path=None, entries=())`` with
    # ``errors=["codeowners_absent"]`` when no CODEOWNERS file is present;
    # the schema slice still lands in the envelope (a Planner-actionable
    # low-information observation, not a probe crash).
    expected = {
        "language_detection",
        "ci",
        "deployment",
        "index_health",
        "dockerfile",
        "entrypoint",
        "shell_usage",
        "certificate",
        "sbom",
        "cve",
        "ownership",
        "gitleaks",  # Phase 2 S6-07 — Layer G secret scanner; universal.
    }
    assert actual == expected, (
        f"envelope probe-keys diverged from expected runnable set; "
        f"actual={sorted(actual)}, expected={sorted(expected)}"
    )
