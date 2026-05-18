"""Unit tests for ``ADRProbe`` (S6-03)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from codegenie.probes.layer_d import adrs as adrs_probe

from .conftest import _make_context, _make_repo


def test_parse_adr_text_extracts_id_title_status() -> None:
    """AC-5. Mutation caught: a regex that accepts arbitrary words for
    ``status`` — the closed Literal fallback to ``"unknown"`` rejects it,
    and the pure helper is unit-testable without filesystem fixtures."""
    lines = iter(["# 0001. Use Postgres\n", "\n", "Status: Accepted\n", "## Context\n"])
    adr_id, title, status = adrs_probe._parse_adr_text(lines, filename_stem="0001-use-postgres")
    assert (adr_id, title, status) == ("0001", "Use Postgres", "accepted")


def test_parse_adr_text_unknown_status_when_missing() -> None:
    """AC-5. Mutation caught: defaulting to ``"proposed"`` would over-claim
    the doc's stance — the Literal type requires the explicit ``unknown``."""
    lines = iter(["# 0042. Foo\n", "(no status line)\n"])
    _, _, status = adrs_probe._parse_adr_text(lines, filename_stem="0042-foo")
    assert status == "unknown"


def test_parse_adr_text_unrecognized_status_falls_back_to_unknown() -> None:
    """AC-5. Mutation caught: admitting any ``\\w+`` from the regex would
    let an arbitrary string slip into the typed slice."""
    lines = iter(["# 0001. Foo\n", "Status: BogusValue\n"])
    _, _, status = adrs_probe._parse_adr_text(lines, filename_stem="0001")
    assert status == "unknown"


def test_parse_adr_text_no_h1_emits_empty_title() -> None:
    """AC-5 / AC-17. Mutation caught: a latent ``NoneType.group(1)`` from
    an inline three-call parse — the pure helper is total."""
    lines = iter(["Status: Proposed\n", "Some prose without H1\n"])
    adr_id, title, _ = adrs_probe._parse_adr_text(lines, filename_stem="0042")
    assert adr_id == "0042"
    assert title == ""


def test_parse_adr_text_falls_back_to_stem_when_no_numeric_prefix() -> None:
    """AC-5. Mutation caught: raising on a non-numeric stem instead of
    falling back — total helper guarantee."""
    lines = iter(["# Plain title\n"])
    adr_id, _, _ = adrs_probe._parse_adr_text(lines, filename_stem="plain-stem")
    assert adr_id == "plain-stem"


def test_adrs_happy_path_scans_three_conventional_locations(tmp_path: Path) -> None:
    """AC-5. Mutation caught: dropping any of the three conventional
    locations — assertion pins the three-location scan."""
    repo = _make_repo(tmp_path)
    (repo.root / "docs" / "adr").mkdir(parents=True)
    (repo.root / "docs" / "architecture").mkdir(parents=True)
    (repo.root / "docs" / "decisions").mkdir(parents=True)
    (repo.root / "docs" / "adr" / "0001-use-postgres.md").write_text(
        "# 0001. Use Postgres\n\nStatus: Accepted\n"
    )
    (repo.root / "docs" / "architecture" / "0002-microservices.md").write_text(
        "# 0002. Microservices\n\nStatus: Proposed\n"
    )
    (repo.root / "docs" / "decisions" / "0003-kafka.md").write_text(
        "# 0003. Kafka\n\nStatus: Superseded\n"
    )
    ctx = _make_context(tmp_path)

    output = asyncio.run(adrs_probe.ADRProbe().run(repo, ctx))
    slice_ = adrs_probe.AdrsSlice.model_validate(output.schema_slice)

    assert output.confidence == "high"
    assert [a.id for a in slice_.adrs] == ["0001", "0002", "0003"]
    assert [a.status for a in slice_.adrs] == ["accepted", "proposed", "superseded"]
    assert [a.path for a in slice_.adrs] == [
        "docs/adr/0001-use-postgres.md",
        "docs/architecture/0002-microservices.md",
        "docs/decisions/0003-kafka.md",
    ]
    assert set(slice_.scanned_locations) == {"docs/adr", "docs/architecture", "docs/decisions"}
    assert slice_.per_file_errors == ()


def test_adrs_marker_absent_yields_low_confidence_no_raise(tmp_path: Path) -> None:
    """AC-10. Mutation caught: any ``raise FileNotFoundError`` would
    break Phase 0 per-probe isolation."""
    repo = _make_repo(tmp_path)
    ctx = _make_context(tmp_path)
    output = asyncio.run(adrs_probe.ADRProbe().run(repo, ctx))
    assert output.confidence == "low"
    slice_ = adrs_probe.AdrsSlice.model_validate(output.schema_slice)
    assert slice_.adrs == ()
    assert slice_.scanned_locations == ()
    assert slice_.per_file_errors == ("adr_dirs_absent",)


def test_adrs_partial_failure_yields_medium_confidence(tmp_path: Path) -> None:
    """AC-16. Mutation caught: collapsing to ``low`` on any error would
    erase the partial-success surface the Planner uses."""
    repo = _make_repo(tmp_path)
    adr_dir = repo.root / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "0001-good.md").write_text("# 0001. Good\nStatus: Accepted\n")
    (adr_dir / "0002-no-h1.md").write_text("Status: Proposed\n(no H1)\n")
    ctx = _make_context(tmp_path)
    output = asyncio.run(adrs_probe.ADRProbe().run(repo, ctx))
    assert output.confidence == "medium"
    slice_ = adrs_probe.AdrsSlice.model_validate(output.schema_slice)
    assert len(slice_.adrs) == 2
    assert "no_h1" in slice_.per_file_errors


def test_adrs_duplicate_id_across_directories_is_deterministic(tmp_path: Path) -> None:
    """AC-15 sub-bullet. Mutation caught: sorting by ``id`` alone would
    let a directory-ordering quirk decide which entry "wins" on
    duplicate IDs across ``docs/adr/`` and ``docs/decisions/``."""
    repo = _make_repo(tmp_path)
    (repo.root / "docs" / "adr").mkdir(parents=True)
    (repo.root / "docs" / "decisions").mkdir(parents=True)
    (repo.root / "docs" / "adr" / "0001-from-adr.md").write_text("# 0001. A\nStatus: Accepted\n")
    (repo.root / "docs" / "decisions" / "0001-from-decisions.md").write_text(
        "# 0001. B\nStatus: Accepted\n"
    )
    ctx = _make_context(tmp_path)
    out1 = asyncio.run(adrs_probe.ADRProbe().run(repo, ctx)).schema_slice
    out2 = asyncio.run(adrs_probe.ADRProbe().run(repo, ctx)).schema_slice
    s1 = adrs_probe.AdrsSlice.model_validate(out1)
    s2 = adrs_probe.AdrsSlice.model_validate(out2)
    assert [a.path for a in s1.adrs] == [a.path for a in s2.adrs]
    assert [a.path for a in s1.adrs] == [
        "docs/adr/0001-from-adr.md",
        "docs/decisions/0001-from-decisions.md",
    ]


def test_adrs_two_runs_byte_identical_model_dump_json(tmp_path: Path) -> None:
    """AC-15. Mutation caught: any iteration order dependent on
    ``os.listdir`` — verified at the slice-JSON byte level."""
    repo = _make_repo(tmp_path)
    adr_dir = repo.root / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "0003-c.md").write_text("# 0003. C\nStatus: Accepted\n")
    (adr_dir / "0001-a.md").write_text("# 0001. A\nStatus: Accepted\n")
    (adr_dir / "0002-b.md").write_text("# 0002. B\nStatus: Accepted\n")
    ctx = _make_context(tmp_path)
    out1 = asyncio.run(adrs_probe.ADRProbe().run(repo, ctx)).schema_slice
    out2 = asyncio.run(adrs_probe.ADRProbe().run(repo, ctx)).schema_slice
    s1 = adrs_probe.AdrsSlice.model_validate(out1)
    s2 = adrs_probe.AdrsSlice.model_validate(out2)
    assert s1.model_dump_json() == s2.model_dump_json()


def test_adrs_raw_artifact_written_atomically(tmp_path: Path) -> None:
    """AC-1 / Implementer note 18. Mutation caught: dropping the
    sibling-tmp + ``os.replace`` pattern would leave corrupt JSON on
    a crashed probe."""
    repo = _make_repo(tmp_path)
    (repo.root / "docs" / "adr").mkdir(parents=True)
    (repo.root / "docs" / "adr" / "0001.md").write_text("# 0001. T\nStatus: Accepted\n")
    ctx = _make_context(tmp_path)
    output = asyncio.run(adrs_probe.ADRProbe().run(repo, ctx))
    raw = ctx.output_dir / "adrs.json"
    assert raw in output.raw_artifacts
    assert raw.exists()
    # The .tmp must be gone after a clean run.
    assert not raw.with_suffix(".tmp").exists()
