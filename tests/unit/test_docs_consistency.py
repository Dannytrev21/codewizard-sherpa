from __future__ import annotations

from pathlib import Path

from codegenie.docs_consistency import collect_docs_consistency_issues

ROOT = Path(__file__).resolve().parents[2]


def test_repo_docs_are_consistent() -> None:
    assert collect_docs_consistency_issues(ROOT) == []


def test_invalid_adr_status_is_reported(tmp_path: Path) -> None:
    _write_adr(tmp_path, "0001-bad.md", "**Status:** Maybe\n")

    assert collect_docs_consistency_issues(tmp_path) == [
        f"{tmp_path / 'docs/production/adrs/0001-bad.md'}: invalid ADR status 'Maybe'"
    ]


def test_provisional_adr_requires_review_trigger(tmp_path: Path) -> None:
    _write_adr(tmp_path, "0001-provisional.md", "**Status:** Provisional Accepted\n")

    assert collect_docs_consistency_issues(tmp_path) == [
        f"{tmp_path / 'docs/production/adrs/0001-provisional.md'}: "
        "provisional ADR missing review trigger"
    ]


def test_supersession_requires_reciprocal_links(tmp_path: Path) -> None:
    _write_adr(tmp_path, "0001-old.md", "**Status:** Superseded by ADR-0002\n")
    _write_adr(tmp_path, "0002-new.md", "**Status:** Accepted\n")

    assert collect_docs_consistency_issues(tmp_path) == [
        f"{tmp_path / 'docs/production/adrs/0001-old.md'}: "
        "successor ADR-0002 lacks reciprocal supersedes link"
    ]


def test_stale_canonical_claims_are_reported(tmp_path: Path) -> None:
    _write_adr(tmp_path, "0001-ok.md", "**Status:** Accepted\n")
    _write_text(
        tmp_path / "docs/production/design.md",
        "Phase 1 target: migrate Node.js services to Chainguard distroless containers.\n",
    )
    _write_text(
        tmp_path / "docs/index.md",
        "Phases 3–7 — Designed; implementation pending plugin-architecture redesign\n",
    )
    _write_text(
        tmp_path / "docs/roadmap.md",
        "hits RAG, not LLM\nbench_score.mean ≥ tier_threshold[bronze]\n",
    )

    assert collect_docs_consistency_issues(tmp_path) == [
        "docs/production/design.md: stale claim still present: "
        "Phase 1 target: migrate Node.js services to Chainguard distroless containers.",
        "docs/index.md: stale claim still present: "
        "Phases 3–7 — Designed; implementation pending plugin-architecture redesign",
        "docs/roadmap.md: stale claim still present: hits RAG, not LLM",
        "docs/roadmap.md: stale claim still present: bench_score.mean ≥ tier_threshold[bronze]",
    ]


def _write_adr(root: Path, filename: str, body: str) -> None:
    _write_text(root / "docs" / "production" / "adrs" / filename, body)
    _write_text(root / "docs" / "production" / "design.md", "")
    _write_text(root / "docs" / "index.md", "")
    _write_text(root / "docs" / "roadmap.md", "")


def _write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
